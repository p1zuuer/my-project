import time
import aiohttp
import logging
from aiogram.types import Message
from aiogram.enums import ParseMode
import database as db
import templates

logger = logging.getLogger(__name__)

# Кэш цены ETH с временем жизни 5 минут (300 секунд)
_ETH_PRICE_CACHE = {
    "price": 2600.0,
    "timestamp": 0.0
}


async def get_eth_price_usd() -> float:
    """Получает текущую цену ETH в USD с кэшированием на 5 минут."""
    global _ETH_PRICE_CACHE
    current_time = time.time()

    if current_time - _ETH_PRICE_CACHE["timestamp"] < 300:
        return _ETH_PRICE_CACHE["price"]

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data["ethereum"]["usd"])
                    _ETH_PRICE_CACHE["price"] = price
                    _ETH_PRICE_CACHE["timestamp"] = current_time
                    return price
    except Exception as e:
        logger.warning(f"Не удалось получить цену ETH с CoinGecko: {e}. Используем кэш/дефолт.")

    return _ETH_PRICE_CACHE["price"]


async def cmd_stats(message: Message, user_id: int = None):
    """
    Обработчик команды /stats.

    Принимает необязательный user_id по тому же паттерну, что и
    cmd_watchlist/cmd_settings/cmd_invite (см. их комментарии) — /stats
    показывает сеть в целом, а не персональные данные, так что до сих пор
    это не проявлялось как видимый баг, но callback.message.from_user все
    равно был бы ID бота, а не открывшего экран пользователя, если бы язык
    интерфейса когда-либо стал персональным для этого экрана.
    """
    user_id = user_id if user_id is not None else message.from_user.id
    lang = db.get_user_language(user_id)
    summary = db.get_stats_summary()
    eth_price = await get_eth_price_usd()
    text = templates.get_stats_text(summary, eth_price, lang)
    await message.answer(text, parse_mode=ParseMode.HTML)