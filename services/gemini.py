"""
Модульный сервис для запросов к Gemini API — на базе SDK `google-genai`.

Единственная задача: НИКОГДА не бросать исключение наружу. Любая ошибка
(отсутствие ключа, таймаут, пустой ответ, исключение SDK) возвращает
безопасный fallback-текст вместо падения хендлера.
"""
import os
import time
import asyncio
import logging
from google import genai

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip("'\" ")
GEMINI_MODEL = "gemini-2.5-flash"
GENERATE_TIMEOUT_SECONDS = 7.0

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

if not client:
    logger.warning("GEMINI_API_KEY не задан — Gemini отключен, все вызовы вернут fallback.")

# ==========================================================================
# Бюджетная защита (найденный приоритет: checker.py теперь обрабатывает
# кошельки параллельно — см. checker.ETHERSCAN_CONCURRENCY — а значит и
# Gemini-вызовы (радар-комментарии x2 языка + OSINT-саммари + /check) могут
# "всплеснуть" одновременно сильнее, чем при последовательной обработке.
# Раньше здесь не было НИКАКОГО потолка расходов: вирусный момент или кто-то,
# спамящий /check в обход cooldown другим способом, мог привести к
# непредсказуемому счету за Gemini. Теперь — два независимых ограничителя:
#   1. GEMINI_CONCURRENCY — не больше N одновременных запросов к Gemini.
#   2. GEMINI_DAILY_BUDGET — жесткий потолок вызовов в сутки (UTC), после
#      которого _generate() сразу возвращает None (уходит в уже
#      существующий fallback-текст) БЕЗ обращения к API.
# Оба настраиваются через env — по умолчанию консервативны для старта.
# ==========================================================================
GEMINI_CONCURRENCY = int(os.getenv("GEMINI_CONCURRENCY", "3"))
GEMINI_DAILY_BUDGET = int(os.getenv("GEMINI_DAILY_BUDGET", "1500"))

_gemini_semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY)
_budget_lock = asyncio.Lock()
_budget_state = {"day": None, "count": 0}


async def _budget_available() -> bool:
    """Проверяет и инкрементирует дневной счетчик вызовов Gemini атомарно
    (asyncio.Lock — защита от гонки при параллельных вызовах). Счетчик
    сбрасывается на новые UTC-сутки. Возвращает False, если бюджет на
    сегодня исчерпан — вызывающий код должен уйти в fallback, не дергая API.
    """
    today = time.strftime("%Y-%m-%d", time.gmtime())
    async with _budget_lock:
        if _budget_state["day"] != today:
            _budget_state["day"] = today
            _budget_state["count"] = 0
        if _budget_state["count"] >= GEMINI_DAILY_BUDGET:
            return False
        _budget_state["count"] += 1
        return True


def get_gemini_usage_today() -> dict:
    """Текущее состояние дневного бюджета — для /stats или админ-диагностики."""
    return {
        "date": _budget_state["day"],
        "used": _budget_state["count"],
        "limit": GEMINI_DAILY_BUDGET,
    }


OSINT_SYSTEM_PROMPT = {
    "ru": (
        "Ты — ведущий аналитик элитной OSINT-разведки Web3 (уровня Arkham/Nansen). "
        "Твоя задача — по сырым ончейн-данным выдвинуть ОДНУ хлёсткую, интригующую "
        "гипотезу о личности владельца кошелька (150-250 символов, без звёздочек/маркдауна). "
        "Отвечай ТОЛЬКО на русском языке."
    ),
    "en": (
        "You are a lead analyst at an elite Web3 OSINT intelligence desk (Arkham/Nansen tier). "
        "Your job is to propose ONE punchy, intriguing hypothesis about the wallet owner's "
        "identity based on raw on-chain data (150-250 characters, no asterisks/markdown). "
        "Respond ONLY in English."
    ),
}

FALLBACK_AI_UNAVAILABLE_RU = "🤖 AI-анализ временно недоступен."
FALLBACK_AI_UNAVAILABLE_EN = "🤖 AI analysis is temporarily unavailable."


async def _generate(prompt: str, timeout_seconds: float = GENERATE_TIMEOUT_SECONDS):
    """
    Единая точка вызова Gemini: синхронный client.models.generate_content()
    выполняется в отдельном потоке через asyncio.to_thread и ограничен
    таймаутом asyncio.wait_for. Возвращает текст ответа или None при любой
    ошибке — никогда не бросает исключение наружу.

    Теперь дополнительно защищена бюджетом (GEMINI_DAILY_BUDGET) и
    параллелизмом (GEMINI_CONCURRENCY, см. комментарий у их определения
    выше) — обе проверки происходят ДО обращения к API, чтобы исчерпанный
    бюджет не стоил дополнительного сетевого вызова.
    """
    if not client:
        return None

    if not await _budget_available():
        logger.warning(
            f"[GEMINI_BUDGET_EXCEEDED] Дневной лимит Gemini-вызовов исчерпан "
            f"({GEMINI_DAILY_BUDGET}/день) — возвращаю fallback без обращения к API."
        )
        return None

    async with _gemini_semaphore:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=GEMINI_MODEL,
                    contents=prompt,
                ),
                timeout=timeout_seconds,
            )
            if response and response.text:
                return response.text.strip()
            logger.warning(f"Gemini вернул пустой response.text (model={GEMINI_MODEL}).")
            return None
        except asyncio.TimeoutError as e:
            logger.error(
                f"[GEMINI_DIAGNOSTIC_ERROR] Failed to generate AI summary: "
                f"{type(e).__name__} - Timeout after {timeout_seconds}s (model={GEMINI_MODEL})",
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"[GEMINI_DIAGNOSTIC_ERROR] Failed to generate AI summary: {type(e).__name__} - {e} "
                f"(model={GEMINI_MODEL})",
                exc_info=True
            )
            return None


async def generate_raw(prompt: str, timeout_seconds: float = GENERATE_TIMEOUT_SECONDS):
    """
    Публичный алиас для _generate() — для использования из других сервисных
    модулей (например services/radar.py), которым нужен произвольный
    Gemini-запрос без привязки к формату OSINT-саммари или /check-анализа.
    Возвращает сырой текст ответа или None при любой ошибке.
    """
    return await _generate(prompt, timeout_seconds)


async def generate_osint_summary(alert_data: dict, lang: str = "ru") -> str:
    """
    Виральное OSINT-саммари для алертов. Всегда возвращает строку, никогда не бросает.

    ВАЖНО (найденный баг — язык AI-текста не совпадал с языком получателя):
    раньше эта функция не принимала lang вообще, промпт и fallback были
    жестко закодированы на русском — из-за этого англоязычные VIP,
    англоязычный публичный канал (PUBLIC_CHANNEL_LANGUAGE=en) и англоязычные
    пользователи /track получали блок "🔍 AI Analysis" на русском внутри
    иначе полностью английского шаблона. Ни i18n symmetry check (сверяет
    только статические ключи templates.py), ни call-graph diff (сверяет
    только наличие функций, не языковую корректность) этого не ловят —
    нужна была ручная проверка каждого места, где генерируется AI-текст.
    """
    lang = lang if lang in OSINT_SYSTEM_PROMPT else "ru"
    label = alert_data.get("label", "Неизвестный кошелек" if lang == "ru" else "Unknown wallet")
    address = alert_data.get("address", "")
    dormant_days = alert_data.get("dormant_days", 0)
    dormant_years = round(dormant_days / 365.25, 1) if dormant_days else 0.0
    amount_eth = alert_data.get("amount_eth", 0.0)

    if lang == "ru":
        fallback_summary = (
            f"🧠 <b>AI OSINT Analysis:</b> Проснулся кошелек <code>{address[:6]}...{address[-4:]}</code> "
            f"с периодом неактивности {dormant_days} дней (~{dormant_years} лет). "
            f"Зафиксировано движение капитала на сумму {amount_eth:.4f} ETH. "
            "Возможна подготовка к OTC-сделке или крупный перевод средств."
        )
        prompt = (
            f"{OSINT_SYSTEM_PROMPT['ru']}\n\n"
            f"Проснулся спящий кошелек! Вот данные:\n"
            f"- Метка кошелька: {label}\n"
            f"- Адрес: {address}\n"
            f"- Период неактивности: {dormant_days} дней (~{dormant_years} лет)\n"
            f"- Сумма транзакции: {amount_eth} ETH\n\n"
            f"Сформулируй ОДНУ хлёсткую, интригующую гипотезу о личности владельца кошелька "
            f"(150-250 символов, без звёздочек/маркдауна)."
        )
    else:
        fallback_summary = (
            f"🧠 <b>AI OSINT Analysis:</b> Dormant wallet <code>{address[:6]}...{address[-4:]}</code> "
            f"just woke up after {dormant_days} days (~{dormant_years} years) of silence. "
            f"Capital movement of {amount_eth:.4f} ETH detected. "
            "Could indicate OTC deal prep or a major fund transfer."
        )
        prompt = (
            f"{OSINT_SYSTEM_PROMPT['en']}\n\n"
            f"A dormant wallet just woke up! Here's the data:\n"
            f"- Wallet label: {label}\n"
            f"- Address: {address}\n"
            f"- Dormant period: {dormant_days} days (~{dormant_years} years)\n"
            f"- Transaction amount: {amount_eth} ETH\n\n"
            f"Propose ONE punchy, intriguing hypothesis about the wallet owner's identity "
            f"(150-250 characters, no asterisks/markdown)."
        )

    text = await _generate(prompt)
    if not text:
        return fallback_summary

    cleaned_text = text.replace("*", "")
    return f"🧠 <b>AI OSINT Analysis:</b>\n{cleaned_text}"


async def generate_wallet_status_analysis(address: str, snapshot: dict, lang: str = "ru") -> str:
    """
    AI-оценка статуса кошелька для /check. ВСЕГДА возвращает строку — при любой
    ошибке возвращает локализованный "AI-анализ временно недоступен" вместо
    падения, чтобы реальные ончейн-данные (баланс/tx_count) все равно дошли
    до пользователя.

    ВАЖНО (найденный баг, самый опасный из трех похожих): эта функция уже
    принимала lang и использовала его для fallback_text — выглядело как будто
    язык учтен. Но сам ПРОМПТ, отправляемый в Gemini, был жестко закодирован
    на русском независимо от lang, и заголовок успешного ответа "🤖 AI Анализ
    кошелька:" тоже был захардкожен на русском. В итоге англоязычный /check
    (самая частая команда бота) получал русский AI-анализ внутри английского
    сообщения практически всегда, когда Gemini отвечал (не только в fallback-
    случае) — баг маскировался под "уже исправленный", потому что параметр
    lang в сигнатуре был, но не был по-настоящему прокинут до промпта.
    """
    lang = lang if lang in ("ru", "en") else "ru"
    fallback_text = FALLBACK_AI_UNAVAILABLE_RU if lang == "ru" else FALLBACK_AI_UNAVAILABLE_EN

    if lang == "ru":
        prompt = (
            f"Проанализируй статус Ethereum кошелька {address} на основе следующих данных:\n"
            f"- Баланс: {snapshot.get('balance', 0)} ETH\n"
            f"- Всего транзакций: {snapshot.get('tx_count', 0)}\n"
            f"- Последняя активность: {snapshot.get('last_active_days', 'неизвестно')} дней назад\n"
            f"- Метка/Тег: {snapshot.get('label') or 'Неизвестен'}\n\n"
            "Дай краткую профессиональную оценку статуса этого кошелька (до 300 символов, "
            "без маркдауна) в стиле Web3 аналитика. Отвечай ТОЛЬКО на русском языке."
        )
        header = "🤖 <b>AI Анализ кошелька:</b>"
    else:
        prompt = (
            f"Analyze the status of Ethereum wallet {address} based on the following data:\n"
            f"- Balance: {snapshot.get('balance', 0)} ETH\n"
            f"- Total transactions: {snapshot.get('tx_count', 0)}\n"
            f"- Last active: {snapshot.get('last_active_days', 'unknown')} days ago\n"
            f"- Label/Tag: {snapshot.get('label') or 'Unknown'}\n\n"
            "Give a brief professional assessment of this wallet's status (up to 300 characters, "
            "no markdown) in the style of a Web3 analyst. Respond ONLY in English."
        )
        header = "🤖 <b>AI Wallet Analysis:</b>"

    text = await _generate(prompt)
    if not text:
        return fallback_text

    return f"{header}\n{text.replace('*', '')}"