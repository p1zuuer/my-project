import aiohttp
import os
import logging
import asyncio
import database as db

logger = logging.getLogger(__name__)

CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
CRYPTO_BOT_URL = "https://pay.crypt.bot/api/"

async def create_crypto_invoice(user_id: int, amount_usd: float = 5.0):
    if not CRYPTO_BOT_TOKEN:
        logger.error("CryptoBot не инициализирован: отсутствует CRYPTO_BOT_TOKEN")
        return None
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    data = {
        "asset": "USDT",
        "amount": str(amount_usd),
        "description": "VIP Subscription (30 days)",
        "payload": str(user_id)
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{CRYPTO_BOT_URL}createInvoice", headers=headers, json=data) as resp:
                res = await resp.json()
                if res.get("ok"):
                    return res["result"]["bot_invoice_url"]
                else:
                    logger.error(f"CryptoBot error: {res}")
                    return None
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса в CryptoBot для пользователя {user_id}: {e}")
        return None

async def get_paid_invoices():
    if not CRYPTO_BOT_TOKEN:
        return []
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    params = {"status": "paid"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CRYPTO_BOT_URL}getInvoices", headers=headers, params=params) as resp:
                res = await resp.json()
                if res.get("ok"):
                    return res["result"]["items"]
                return []
    except Exception as e:
        logger.error(f"Ошибка при получении оплаченных инвойсов: {e}")
        return []

async def check_invoices(bot):
    """Фоновая задача для проверки оплаченных счетов через CryptoBot API."""
    if not CRYPTO_BOT_TOKEN:
        logger.warning("CryptoBot токен не настроен, фоновая проверка инвойсов отключена.")
        return
    
    while True:
        try:
            items = await get_paid_invoices()
            for invoice in items:
                payload = invoice.get("payload")
                if payload:
                    try:
                        user_id = int(payload)
                        invoice_id = str(invoice.get("invoice_id"))
                        
                        if not db.is_invoice_processed(invoice_id):
                            db.mark_invoice_processed(invoice_id)
                            db.add_vip_user(user_id, "", days=30)

                            # Аффилиат-комиссия за оплату через CryptoBot (та же логика, что и Stars).
                            referrer_id = db.get_referrer_for_user(user_id)
                            if referrer_id:
                                paid_amount = float(invoice.get("amount", 5.0))
                                db.record_affiliate_commission(
                                    referrer_id, user_id, amount_usd=paid_amount, source="cryptobot"
                                )

                            await bot.send_message(
                                chat_id=user_id,
                                text="🎉 VIP-статус успешно активирован на 30 дней через CryptoBot!",
                                parse_mode="HTML"
                            )
                            logger.info(f"CryptoBot инвойс {invoice_id} успешно обработан для пользователя {user_id}.")
                    except ValueError:
                        pass
        except Exception as e:
            logger.error(f"Ошибка в check_invoices: {e}")
            
        await asyncio.sleep(30)