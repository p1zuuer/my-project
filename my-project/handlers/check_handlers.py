import time
import logging
import json
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
import database as db
import templates
import ai_analyst
from services import etherscan

logger = logging.getLogger(__name__)

# Простой in-memory rate limit: 1 проверка на пользователя раз в 10 секунд.
COOLDOWN_SECONDS = 10
_last_check_at = {}


def _is_rate_limited(user_id: int) -> bool:
    now = time.time()
    last = _last_check_at.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        return True
    _last_check_at[user_id] = now
    return False


def _empty_snapshot(address: str) -> dict:
    """Безопасный дефолт снапшота — используется, если получить данные вообще не удалось."""
    return {
        "address": address,
        "balance": 0,
        "balance_ok": False,
        "tx_count": 0,
        "tx_ok": False,
        "last_active_days": 0,
        "label": None,
    }


async def _read_cache(address: str):
    """Читает кэш из БД. Возвращает dict или None. Никогда не бросает исключение."""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT data, extract(epoch from updated_at) FROM address_cache WHERE address = %s",
                    (address,)
                )
                row = cursor.fetchone()
                # PostgreSQL EXTRACT(epoch FROM ...) возвращает numeric, который
                # psycopg2 мапит на decimal.Decimal — прямое вычитание из
                # time.time() (float) падает с TypeError: unsupported operand
                # type(s) for -: 'float' and 'decimal.Decimal'. Явно приводим
                # к float перед арифметикой.
                if row and row[0] and (time.time() - float(row[1]) < 3600):
                    return json.loads(row[0])
    except Exception as e:
        logger.error(f"Ошибка чтения address_cache для {address}: {e}")
    return None


async def _write_cache(address: str, snapshot: dict):
    """Пишет кэш в БД. Никогда не бросает исключение — сбой кэша не должен ронять /check."""
    try:
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO address_cache (address, data, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (address) DO UPDATE SET
                        data = EXCLUDED.data,
                        updated_at = CURRENT_TIMESTAMP
                """, (address, json.dumps(snapshot)))
            conn.commit()
    except Exception as e:
        logger.error(f"Ошибка записи address_cache для {address}: {e}")


async def get_wallet_snapshot(address: str) -> dict:
    """
    Получает снимок данных кошелька: сначала кэш (1ч TTL), иначе Etherscan
    (баланс + история запрашиваются раздельно и независимо друг от друга).
    ГАРАНТИРОВАННО возвращает dict и никогда не бросает исключение наружу —
    это критично, т.к. вызывающий код (cmd_check) не имеет своего try/except
    вокруг этого вызова помимо общего защитного блока.
    """
    address = address.lower()

    cached = await _read_cache(address)
    if cached is not None:
        return cached

    snapshot = _empty_snapshot(address)

    # Баланс и история запрашиваются НЕЗАВИСИМО: падение одного не должно
    # затирать успешно полученный результат другого (баг из TASK 2).
    try:
        balance_val = await etherscan.fetch_eth_balance(address)
        if balance_val is not None:
            snapshot["balance"] = round(balance_val, 4)
            snapshot["balance_ok"] = True
    except Exception as e:
        # Защита в глубину: etherscan.py уже не должен бросать исключения,
        # но если это все же случится, /check все равно не должен зависнуть.
        logger.error(f"Неожиданное исключение при получении баланса для {address}: {e}")

    try:
        txs = await etherscan.fetch_tx_history(address)
        if txs is not None:
            snapshot["tx_count"] = len(txs)
            snapshot["tx_ok"] = True
            if txs:
                last_ts = int(txs[0].get("timeStamp", 0))
                snapshot["last_active_days"] = max(0, int((time.time() - last_ts) / 86400))
    except Exception as e:
        logger.error(f"Неожиданное исключение при получении истории транзакций для {address}: {e}")

    try:
        wallet_info = db.get_wallet(address)
        snapshot["label"] = wallet_info[1] if wallet_info else None
    except Exception as e:
        logger.error(f"Ошибка чтения wallets для {address}: {e}")

    # Кэшируем только если хотя бы баланс успешно получен — иначе временный
    # сбой API "запечется" в кэше на целый час.
    if snapshot["balance_ok"]:
        await _write_cache(address, snapshot)

    return snapshot


async def run_wallet_check(user_id: int, lang: str, address: str, wait_msg):
    """
    Основная логика проверки кошелька — общая для /check и кнопки
    '🔍 Быстрый AI-Анализ' с карточки автодетекта. Принимает уже отправленное
    'wait_msg' (любой объект с .edit_text — Message от message.answer() или
    от callback.message.answer(), интерфейс идентичен) и гарантированно
    редактирует его РОВНО ОДИН РАЗ в конце, что бы ни случилось выше.
    """
    text = templates.t(lang, "check_error_generic")  # безопасный дефолт на случай полного отказа ниже

    try:
        try:
            snapshot = await get_wallet_snapshot(address)
        except Exception as e:
            logger.error(f"get_wallet_snapshot полностью упал для {address}: {e}")
            snapshot = _empty_snapshot(address)

        try:
            ai_analysis = await ai_analyst.generate_wallet_status_analysis(address, snapshot, lang=lang)
        except Exception as e:
            logger.error(f"generate_wallet_status_analysis упал для {address}: {e}")
            ai_analysis = (
                "🤖 AI-анализ временно недоступен." if lang == "ru"
                else "🤖 AI analysis is temporarily unavailable."
            )

        text = templates.get_check_result_text(snapshot, ai_analysis, lang)

    except Exception as e:
        logger.error(f"Непредвиденная ошибка в run_wallet_check для {address}: {e}")
        text = templates.t(lang, "check_error_generic")

    finally:
        try:
            await wait_msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Не удалось отредактировать сообщение для {address}: {e}")


async def cmd_check(message: Message):
    """
    Обработчик команды /check <address>.

    Контракт: `wait_msg.edit_text(...)` ГАРАНТИРОВАННО выполняется ровно один раз
    в конце (см. run_wallet_check) — успешно или с сообщением об ошибке —
    независимо от того, что случилось выше (сбой Etherscan, сбой Gemini,
    сбой БД, таймаут). Именно отсутствие этой гарантии было причиной
    зависания на "🔄 Загрузка...".
    """
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    if _is_rate_limited(user_id):
        await message.answer(templates.t(lang, "check_cooldown"), parse_mode=ParseMode.HTML)
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer(templates.t(lang, "check_usage"), parse_mode=ParseMode.HTML)
        return

    address = args[1].strip()
    if not address.startswith("0x") or len(address) != 42:
        await message.answer(templates.t(lang, "check_invalid"), parse_mode=ParseMode.HTML)
        return

    wait_msg = await message.answer(templates.t(lang, "check_loading"), parse_mode=ParseMode.HTML)
    await run_wallet_check(user_id, lang, address, wait_msg)


async def process_quick_ai_callback(callback: CallbackQuery):
    """Кнопка '🔍 Быстрый AI-Анализ' с карточки автодетекта 0x-адреса."""
    address = callback.data[len("qa_ai_"):]
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    if _is_rate_limited(user_id):
        await callback.answer(templates.t(lang, "check_cooldown"), show_alert=True)
        return

    await callback.answer()
    wait_msg = await callback.message.answer(templates.t(lang, "check_loading"), parse_mode=ParseMode.HTML)
    await run_wallet_check(user_id, lang, address, wait_msg)