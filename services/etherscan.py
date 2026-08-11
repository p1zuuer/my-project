"""
Модульный сервис для запросов к Etherscan API.

Ключевые принципы (по итогам аудита бага "0.0 ETH для непустых кошельков"):
- Баланс и история транзакций запрашиваются РАЗДЕЛЬНО, каждый со своим таймаутом
  и обработкой ошибок — падение одного запроса не должно затирать другой.
- Любая ошибка (сеть, таймаут, HTTP-статус, NOTOK от Etherscan, невалидный JSON)
  возвращает None, а НЕ 0 / 0.0 — вызывающий код обязан явно отличать
  "данные не получены" от "баланс действительно нулевой".
- Ни одно исключение отсюда не должно "утекать" наружу необработанным —
  иначе caller (check_handlers.cmd_check) зависает на "Загрузка..." навсегда.
"""
import os
import time
import asyncio
import logging
import datetime
import aiohttp

logger = logging.getLogger(__name__)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
# Etherscan V2: единый мультичейн-эндпоинт, требует явный chainid в каждом запросе.
# V1-эндпоинт (https://api.etherscan.io/api) устаревает — переезжаем на V2.
BASE_URL = "https://api.etherscan.io/v2/api"
CHAIN_ID = 1  # Ethereum mainnet

# Требуется по спецификации — некоторые хостинги (в т.ч. Render) без User-Agent
# иногда получают более агрессивный rate-limit / блокировку от Etherscan.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

if not ETHERSCAN_API_KEY:
    logger.warning(
        "ETHERSCAN_API_KEY не задан в окружении — все запросы к Etherscan "
        "будут немедленно возвращать None без обращения к сети."
    )


async def fetch_eth_balance(address: str, timeout_seconds: int = 6):
    """
    Возвращает баланс кошелька в ETH (float) или None при ЛЮБОЙ проблеме:
    отсутствии ключа, таймауте, HTTP-ошибке, NOTOK/Invalid API Key, или
    нечисловом result. Никогда не бросает исключение наружу.
    """
    if not ETHERSCAN_API_KEY:
        return None

    params = {
        "chainid": CHAIN_ID,
        "module": "account",
        "action": "balance",
        "address": address,
        "tag": "latest",
        "apikey": ETHERSCAN_API_KEY,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(BASE_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Etherscan balance: HTTP {resp.status} для {address}")
                    return None
                data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        logger.warning(f"Etherscan balance: таймаут ({timeout_seconds}s) для {address}")
        return None
    except aiohttp.ClientError as e:
        logger.warning(f"Etherscan balance: сетевая ошибка для {address}: {e}")
        return None
    except Exception as e:
        logger.error(f"Etherscan balance: неожиданная ошибка для {address}: {e}")
        return None

    status = data.get("status")
    message = data.get("message", "")
    result = data.get("result")

    # Etherscan сигнализирует ошибку через status="0" (NOTOK) — в т.ч. невалидный
    # ключ, превышение лимита запросов и т.д. Раньше это не проверялось явно,
    # и код пытался парсить result как число даже когда там была строка ошибки
    # (например "Invalid API Key" или "Max rate limit reached") — что либо падало
    # с исключением (зависание хендлера), либо, если исключение проглатывалось
    # где-то выше, приводило к тихому 0.0 ETH.
    if status != "1":
        logger.warning(f"Etherscan balance: NOTOK для {address}: message={message!r} result={result!r}")
        return None

    try:
        # result — строка Wei (может быть очень большим числом), конвертируем в ETH.
        return float(result) / 1e18
    except (TypeError, ValueError):
        logger.error(f"Etherscan balance: не удалось распарсить result={result!r} для {address}")
        return None


async def fetch_tx_history(address: str, timeout_seconds: int = 6):
    """
    Возвращает список последних транзакций (до 5, offset=5&sort=desc) или None
    при ошибке API/сети/таймауте. Пустой список [] — валидный ответ "транзакций
    нет", а НЕ ошибка, и должен обрабатываться отдельно от None.
    """
    if not ETHERSCAN_API_KEY:
        return None

    params = {
        "chainid": CHAIN_ID,
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
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
            async with session.get(BASE_URL, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Etherscan txlist: HTTP {resp.status} для {address}")
                    return None
                data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        logger.warning(f"Etherscan txlist: таймаут ({timeout_seconds}s) для {address}")
        return None
    except aiohttp.ClientError as e:
        logger.warning(f"Etherscan txlist: сетевая ошибка для {address}: {e}")
        return None
    except Exception as e:
        logger.error(f"Etherscan txlist: неожиданная ошибка для {address}: {e}")
        return None

    status = data.get("status")
    message = data.get("message", "")
    result = data.get("result")

    if status == "1" and isinstance(result, list):
        return result
    if status == "0" and message == "No transactions found":
        return []  # валидный пустой ответ, не ошибка

    logger.warning(f"Etherscan txlist: NOTOK для {address}: message={message!r}")
    return None


def format_last_active(timestamp: int) -> str:
    """Человекочитаемая давность последней активности: 'Xd ago' или 'YYYY-MM-DD' для дат старше 30 дней."""
    if not timestamp:
        return "—"
    now = time.time()
    days = max(0, int((now - timestamp) / 86400))
    if days <= 30:
        return f"{days}d ago"
    dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d")