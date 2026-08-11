import asyncio
import datetime
import logging
import os
import sys
from typing import Optional
import aiohttp
from dotenv import load_dotenv

import database as db
from services import radar
from bot import (
    send_vip_alerts, schedule_public_alert, send_personal_tracked_alert,
    send_radar_vip_alerts, schedule_radar_public_alert, send_personal_radar_alert,
)

load_dotenv()

# Настройка кодировки UTF-8 для консоли Windows
if sys.platform == "win32":
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"

# Порог в днях, после которого кошелек считается "спящим" (детектор пробуждения)
DORMANT_THRESHOLD_DAYS = 365

# Радар крупных переводов работает в том же цикле — 60-90с достаточно для
# своевременного сигнала и укладывается в квоту Etherscan при десятках
# адресов в watchlist. Выбрано среднее значение диапазона.
MAIN_LOOP_INTERVAL_SECONDS = 75

# Отслеживание фоновых тасок для надежной отправки сообщений в публичный канал
_background_tasks = set()


async def get_recent_transactions(session: aiohttp.ClientSession, address: str,
                                   _retry: bool = True) -> Optional[list]:
    """
    Получает до 5 последних транзакций кошелька — ОДИН запрос, используемый
    ОБЕИМИ системами (детектор пробуждения смотрит только на [0], радар
    сканирует весь список на предмет крупных сумм). Раньше offset был равен 2
    (хватало только для дормант-детектора); теперь 5, чтобы радар не терял
    сигналы при нескольких крупных транзакциях за один цикл.

    НАЙДЕННЫЙ БАГ (наблюдаемость): при ошибке логировался только data["message"] —
    а это ВСЕГДА буквально строка "NOTOK" у Etherscan при status="0", независимо
    от реальной причины. Настоящая причина (rate limit, неверный ключ, плохие
    параметры) лежит в data["result"], который раньше не логировался вообще —
    из логов было невозможно понять, ЧТО именно пошло не так. Теперь логируется
    result, и вдобавок ошибки, похожие на rate limit, получают один retry с
    паузой вместо немедленного отказа (см. _retry) — самолечение внутри одного
    цикла вместо ожидания следующего 75-секундного прохода.
    """
    params = {
        "chainid": 1,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 5,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }
    try:
        async with session.get(ETHERSCAN_BASE_URL, params=params) as response:
            if response.status == 429:
                logging.warning(f"Etherscan 429 (rate limit, HTTP-уровень) для {address}")
                if _retry:
                    await asyncio.sleep(1.5)
                    return await get_recent_transactions(session, address, _retry=False)
                return None
            data = await response.json()
            status = data.get("status")
            message = data.get("message")
            result = data.get("result")

            if status == "1":
                if result:
                    return result
                logging.warning(f"Etherscan API: статус '1' для {address}, но result пуст")
                return []
            elif status == "0" and message == "No transactions found":
                return []
            else:
                # result здесь — строка с реальной причиной (например
                # "Max rate limit reached", "Invalid API Key",
                # "Missing/Invalid API Key" и т.д.) — именно ее не хватало в
                # логах раньше.
                logging.error(
                    f"Etherscan API ошибка для {address}: status={status}, "
                    f"message={message}, result={result!r}"
                )
                if _retry and isinstance(result, str) and "rate limit" in result.lower():
                    await asyncio.sleep(1.5)
                    return await get_recent_transactions(session, address, _retry=False)
                return None
    except Exception as e:
        logging.error(f"Ошибка при запросе транзакций для {address}: {e}")
        return None


async def _run_dormant_check(address: str, label: str, source: str, added_by, txs: list):
    """Детектор пробуждения спящих китов — логика не изменилась, только вынесена в отдельную функцию."""
    latest_tx = txs[0]
    latest_hash = latest_tx.get("hash")
    latest_timestamp = int(latest_tx.get("timeStamp", 0))

    cached_wallet = db.get_wallet(address)

    if not cached_wallet:
        db.upsert_wallet(address, label, latest_hash, latest_timestamp)
        tx_date = datetime.datetime.fromtimestamp(latest_timestamp, tz=datetime.timezone.utc)
        logging.info(f"💾 [ИНИЦИАЛИЗАЦИЯ] {label} ({address[:8]}...) | последняя Tx: {tx_date.strftime('%Y-%m-%d')}")
        return

    _, _, prev_hash, prev_timestamp = cached_wallet

    if latest_hash != prev_hash:
        dormant_seconds = latest_timestamp - prev_timestamp
        dormant_days = dormant_seconds // 86400
        value_eth = int(latest_tx.get("value", 0)) / 10**18

        if dormant_days >= DORMANT_THRESHOLD_DAYS:
            if db.save_alert(address, latest_hash, dormant_days, value_eth):
                alert_payload = {
                    "label": label,
                    "address": address,
                    "dormant_days": dormant_days,
                    "amount_eth": value_eth,
                    "tx_hash": latest_hash,
                }
                logging.warning(
                    f"\n🔥 [WALLET AWAKENED] {label} | {address} | "
                    f"{dormant_days}d dormant | {value_eth:.4f} ETH | source={source}\n"
                )
                try:
                    if source == "user" and added_by:
                        await send_personal_tracked_alert(added_by, alert_payload)
                    else:
                        await send_vip_alerts(alert_payload)
                        task = await schedule_public_alert(alert_payload)
                        if task:
                            _background_tasks.add(task)
                            task.add_done_callback(_background_tasks.discard)
                except Exception as alert_err:
                    logging.error(f"Ошибка при отправке дормант-алертов для {address}: {alert_err}")
        else:
            logging.info(f"ℹ️ [Обычная активность] {label}: пауза была {dormant_days} дней")

        db.upsert_wallet(address, label, latest_hash, latest_timestamp)


async def _run_radar_check(address: str, label: str, source: str, added_by, txs: list, threshold_eth: float):
    """Радар крупных переводов — работает НЕЗАВИСИМО от состояния дормант-детектора."""
    try:
        signals = await radar.analyze_transactions(address, label, txs, threshold_eth)
    except Exception as e:
        logging.error(f"Radar: ошибка анализа {address}: {e}")
        return

    for signal in signals:
        logging.warning(
            f"\n⚡ [RADAR SIGNAL] {signal['label']} | {signal['address']} | "
            f"{signal['amount_eth']:.4f} ETH {signal['direction']} | source={source}\n"
        )
        try:
            if source == "user" and added_by:
                await send_personal_radar_alert(added_by, signal)
            else:
                await send_radar_vip_alerts(signal)
                task = await schedule_radar_public_alert(signal)
                if task:
                    _background_tasks.add(task)
                    task.add_done_callback(_background_tasks.discard)
        except Exception as alert_err:
            logging.error(f"Radar: ошибка отправки сигнала для {address}: {alert_err}")


async def process_wallet(session: aiohttp.ClientSession, address: str, label: str,
                          source: str, added_by, monitor_type: str, alert_threshold_eth: float):
    """
    Обрабатывает один адрес из watchlist — ОДИН запрос к Etherscan обслуживает
    обе независимые системы обнаружения:
      monitor_type='dormant' -> только детектор пробуждения
      monitor_type='radar'   -> только радар крупных переводов
      monitor_type='both'    -> обе системы (типично для пользовательских /track)
    alert_threshold_eth — персональный порог радара ЭТОГО кошелька
    (watchlist.alert_threshold_eth), настраиваемый через /watchlist -> 🔔 Порог алертов.
    """
    address = address.lower()

    txs = await get_recent_transactions(session, address)
    if txs is None:
        logging.warning(f"Ошибка API для {address}")
        return
    if not txs:
        logging.info(f"У кошелька {address} нет транзакций (пустой кошелек).")
        return

    if monitor_type in ("dormant", "both"):
        await _run_dormant_check(address, label, source, added_by, txs)

    if monitor_type in ("radar", "both"):
        await _run_radar_check(address, label, source, added_by, txs, alert_threshold_eth)


# Найденный приоритет для роста: старая реализация обрабатывала watchlist
# СТРОГО последовательно (один адрес -> sleep(0.3) -> следующий). При
# небольшом watchlist это незаметно, но при росте до сотен адресов сам цикл
# обработки начинает занимать дольше, чем MAIN_LOOP_INTERVAL_SECONDS (75с) —
# и алерты становятся тем более "устаревшими", чем больше растет watchlist,
# без КАКОГО-ЛИБО предупреждения об этом. Ниже — ограниченная параллельность
# через семафор: несколько кошельков обрабатываются одновременно, но не
# больше ETHERSCAN_CONCURRENCY одновременных запросов — тот же бюджет
# rate-limit'а Etherscan (free-tier ~5 req/s), что и раньше, просто
# используемый параллельно, а не последовательно.
ETHERSCAN_CONCURRENCY = 4
_etherscan_semaphore = asyncio.Semaphore(ETHERSCAN_CONCURRENCY)


async def _process_wallet_throttled(session: aiohttp.ClientSession, address: str, label: str,
                                     source: str, added_by, monitor_type: str, alert_threshold_eth: float,
                                     stagger_seconds: float = 0.0):
    """Оборачивает process_wallet семафором, чтобы не превысить rate limit
    Etherscan при параллельной обработке watchlist. Исключение одного
    кошелька изолировано здесь и не прерывает обработку остальных.

    НАЙДЕННЫЙ БАГ (обнаружен по логам продакшена — интермиттентные
    status=0/NOTOK, разные адреса каждый цикл, самоизлечивающиеся к
    следующему проходу): asyncio.gather() запускает ВСЕ задачи одновременно,
    и до ETHERSCAN_CONCURRENCY из них проходят семафор МГНОВЕННО — то есть
    реальный залповый всплеск из N запросов в один и тот же момент времени
    КАЖДЫЙ цикл, а не размазанная по времени нагрузка. Формально "4 < 5/сек"
    на бумаге, но если Etherscan считает скользящим окном строже — залп
    может пробивать лимит именно из-за одновременности, а не из-за общего
    количества. stagger_seconds размазывает МОМЕНТ ВХОДА в семафор по времени
    внутри батча, оставляя сам семафор как защитный потолок параллельности.
    """
    if stagger_seconds > 0:
        await asyncio.sleep(stagger_seconds)
    async with _etherscan_semaphore:
        try:
            await process_wallet(session, address, label or "Unknown", source, added_by,
                                  monitor_type, alert_threshold_eth)
        except Exception as wallet_err:
            logging.error(f"Ошибка обработки кошелька {address}: {wallet_err}")
        # Небольшая пауза ВНУТРИ семафора — распределяет фактическую частоту
        # запросов по времени в рамках допустимого слота параллельности,
        # вместо одной сплошной паузы между каждым адресом.
        await asyncio.sleep(0.2)


async def main():
    db.init_db()

    async with aiohttp.ClientSession() as session:
        while True:
            # Весь цикл обернут в try/except — сбой БД, сети или одного
            # кошелька не должен убивать фоновый мониторинг навсегда.
            try:
                watchlist = db.get_active_watchlist()
                logging.info(f"--- Проверка watchlist: {len(watchlist)} адресов (concurrency={ETHERSCAN_CONCURRENCY}) ---")

                tasks = [
                    _process_wallet_throttled(
                        session, address, label, source, added_by, monitor_type, alert_threshold_eth,
                        stagger_seconds=(i % ETHERSCAN_CONCURRENCY) * 0.3,
                    )
                    for i, (address, label, source, added_by, monitor_type, alert_threshold_eth) in enumerate(watchlist)
                ]
                if tasks:
                    await asyncio.gather(*tasks)

            except Exception as loop_err:
                logging.error(f"Ошибка в основном цикле мониторинга: {loop_err}")

            logging.info(f"Ожидание {MAIN_LOOP_INTERVAL_SECONDS} секунд...")
            await asyncio.sleep(MAIN_LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Остановлено.")