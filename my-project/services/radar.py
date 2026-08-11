"""
Радар крупных переводов — вторая, независимая от детектора "пробуждения
спящих китов" система обнаружения. Работает на ЛЮБЫХ адресах из watchlist
с monitor_type IN ('radar', 'both'), включая постоянно активные (биржевые
hot wallets, известные трейдеры) — в отличие от дормант-детектора, здесь не
важно, спал ли кошелек: важен только размер перевода.

checker.py вызывает analyze_transactions() с уже полученным (одним и тем же
API-запросом, что и для дормант-проверки) списком последних транзакций —
радар НЕ делает собственных запросов к Etherscan, чтобы не удваивать нагрузку
на квоту за один и тот же адрес в одном цикле.
"""
import logging
from services import gemini

logger = logging.getLogger(__name__)

# Порог по умолчанию, если по каким-то причинам не удалось прочитать
# alert_threshold_eth конкретного кошелька (например, ошибка БД) — раньше
# было единственным глобальным порогом, теперь только fallback-значение.
DEFAULT_THRESHOLD_ETH = 10.0


def find_new_significant_transactions(address: str, txs: list, last_seen_tx_hash: str,
                                       threshold_eth: float = DEFAULT_THRESHOLD_ETH) -> list:
    """
    Из списка последних транзакций (отсортированного по убыванию времени,
    как возвращает Etherscan с sort=desc) отбирает НОВЫЕ (не встречавшиеся
    в прошлом цикле) транзакции с value >= threshold_eth (персональный порог
    ЭТОГО конкретного кошелька из watchlist.alert_threshold_eth).

    Возвращает список в ХРОНОЛОГИЧЕСКОМ порядке (старые -> новые), чтобы при
    восстановлении после паузы (например, рестарт бота) сигналы отправлялись
    в правильном порядке, а не задом наперед.
    """
    if not txs:
        return []

    significant = []
    for tx in txs:
        tx_hash = tx.get("hash")
        if tx_hash == last_seen_tx_hash:
            # Дошли до последней уже обработанной транзакции — все, что
            # дальше в списке (более старое), уже было проверено раньше.
            break
        try:
            value_eth = int(tx.get("value", 0)) / 10**18
        except (TypeError, ValueError):
            continue
        if value_eth >= threshold_eth:
            significant.append(tx)

    significant.reverse()  # в хронологический порядок
    return significant


async def generate_market_impact_commentary(label: str, address: str, value_eth: str, direction: str) -> str:
    """
    2-предложенческий контекст рыночного влияния через Gemini
    (gemini-2.5-flash, см. services/gemini.py). Никогда не бросает
    исключение — при сбое Gemini возвращает нейтральный fallback, чтобы
    сигнал радара все равно был отправлен с реальными ончейн-данными.
    """
    fallback = (
        f"Крупный перевод {value_eth} ETH от адреса {label or address[:10]}. "
        "Требуется дополнительный анализ контекста."
    )

    prompt = (
        f"Кошелек с меткой '{label or 'Unknown'}' ({address}) только что {direction} "
        f"{value_eth} ETH. Дай ДВА предложения профессионального рыночного контекста: "
        "что может означать это движение (например, подготовка к продаже, "
        "перевод на биржу, OTC-сделка, ребалансировка портфеля), без финансовых "
        "советов, в стиле Web3-аналитика, без маркдауна и звездочек."
    )

    text = await gemini.generate_raw(prompt, timeout_seconds=7.0)
    if not text:
        return fallback
    return text.replace("*", "").strip()


async def analyze_transactions(address: str, label: str, txs: list,
                                threshold_eth: float = DEFAULT_THRESHOLD_ETH) -> list:
    """
    Главная точка входа радара для одного адреса за один цикл проверки.
    threshold_eth — персональный порог ЭТОГО кошелька (watchlist.alert_threshold_eth),
    передается из checker.py вместо использования единого глобального значения.
    Возвращает список готовых alert_payload dict (может быть пустым, может
    содержать несколько сигналов, если пропущено несколько крупных
    транзакций за один цикл — например, после паузы бота).
    """
    last_seen = None
    is_first_run = False
    try:
        import database as db
        last_seen = db.get_radar_last_seen(address)
        is_first_run = last_seen is None
    except Exception as e:
        logger.error(f"Radar: ошибка чтения radar_seen для {address}: {e}")

    if is_first_run:
        # Первое знакомство радара с этим адресом: как и дормант-детектор,
        # молча запоминаем текущее состояние БЕЗ алертов — иначе на старте
        # мониторинга случился бы "залповый" пересказ уже произошедших в
        # прошлом крупных транзакций, что выглядело бы как ложная тревога.
        if txs:
            try:
                import database as db
                db.upsert_radar_last_seen(address, txs[0].get("hash"))
                logger.info(f"Radar: инициализация состояния для {address} ({label})")
            except Exception as e:
                logger.error(f"Radar: ошибка инициализации radar_seen для {address}: {e}")
        return []

    new_significant = find_new_significant_transactions(address, txs, last_seen, threshold_eth)
    if not new_significant:
        # Даже без сигналов обновляем radar_seen на самую свежую транзакцию,
        # чтобы состояние не "застревало" из-за мелких переводов ниже порога.
        if txs:
            try:
                import database as db
                db.upsert_radar_last_seen(address, txs[0].get("hash"))
            except Exception as e:
                logger.error(f"Radar: ошибка записи radar_seen для {address}: {e}")
        return []

    signals = []
    for tx in new_significant:
        try:
            value_eth = round(int(tx.get("value", 0)) / 10**18, 4)
        except (TypeError, ValueError):
            continue

        direction = "получил" if tx.get("to", "").lower() == address.lower() else "отправил"
        commentary = await generate_market_impact_commentary(label, address, f"{value_eth:.2f}", direction)

        signal = {
            "label": label,
            "address": address,
            "tx_hash": tx.get("hash"),
            "amount_eth": value_eth,
            "direction": direction,
            "ai_commentary": commentary,
        }
        signals.append(signal)

        # Записываем в историю сигналов сразу (не в конце функции), чтобы
        # частичный сбой на более поздней транзакции того же цикла не стер
        # уже готовые записи истории для более ранних сигналов.
        try:
            import database as db
            db.record_radar_signal(address, signal["tx_hash"], value_eth, direction)
        except Exception as e:
            logger.error(f"Radar: ошибка записи истории сигнала для {address}: {e}")

    # Обновляем radar_seen на самую новую (последнюю в хронологическом
    # порядке) обработанную транзакцию из ПОЛНОГО списка txs — не только из
    # значимых, чтобы мелкие переводы тоже "проматывали" состояние и не
    # заставляли радар пересканировать их на каждом цикле.
    if txs:
        try:
            import database as db
            db.upsert_radar_last_seen(address, txs[0].get("hash"))
        except Exception as e:
            logger.error(f"Radar: ошибка записи radar_seen для {address}: {e}")

    return signals