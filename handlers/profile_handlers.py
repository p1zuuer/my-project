"""
Централизованный экран "👤 Профиль и Оплата".

Раньше покупка VIP была размазана по двум отдельным кнопкам на карточке
профиля (Stars напрямую и CryptoBot напрямую) — теперь это один пункт
"💳 Пополнить баланс", который открывает единое подменю с обоими способами
оплаты. Это устраняет дублирование входных точек в одну и ту же покупку
и делает профиль единственным местом, где происходит все, что касается
статуса подписки, оплаты и заработка (реферальная программа).
"""
import os
import logging
import datetime
from aiogram.types import Message, CallbackQuery, LabeledPrice
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
import templates
from handlers import referral_handlers
from services import payments

logger = logging.getLogger(__name__)

ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else 0

# Примеры для /recent — демонстрационные, не выдаются за реальные текущие
# события, служат для показа формата алерта и качества AI-анализа до оплаты.
_RECENT_EXAMPLES = [
    {
        "label": "Early 2015 Miner Wallet",
        "address": "0x1a2b3c4d5e6f7890abcdef1234567890abcdef12",
        "dormant_days": 3285,
        "dormant_years": 9.0,
        "amount_eth": 420.69,
        "tx_hash": "0xexampletxhash1111111111111111111111111111111111111111111111",
        "ai_summary_en": (
            "Coins minted back when ETH traded under $1 — this wallet has been silent since "
            "the DAO fork. A move this size after nine years of silence usually means one thing: "
            "someone finally decided it's time to cash out."
        ),
        "ai_summary_ru": (
            "Монеты добыты, когда ETH стоил меньше доллара — кошелек молчал с момента форка DAO. "
            "Движение такого размера после девяти лет тишины обычно значит одно: "
            "владелец наконец решил зафиксировать прибыль."
        ),
    },
    {
        "label": "Mt. Gox-era Deposit Address",
        "address": "0xfeedface00000000000000000000000000dead1",
        "dormant_days": 1460,
        "dormant_years": 4.0,
        "amount_eth": 150.0,
        "tx_hash": "0xexampletxhash2222222222222222222222222222222222222222222222",
        "ai_summary_en": (
            "Pattern matches a legacy exchange cold-storage cluster. A four-year-old wallet moving "
            "150 ETH in one transaction is consistent with either an OTC settlement or "
            "consolidation ahead of a larger distribution."
        ),
        "ai_summary_ru": (
            "Паттерн соответствует старому кластеру холодного хранения биржи. Кошелек, "
            "молчавший 4 года, разом двинул 150 ETH — похоже на OTC-расчет либо "
            "консолидацию перед более крупным распределением."
        ),
    },
]


def _get_vip_status(user_id: int):
    """Хелпер: возвращает (is_vip: bool, expire_date_str: str|None)."""
    is_vip_status = db.is_vip(user_id)
    expire_date = None
    if is_vip_status:
        active_vips = db.get_active_vips()
        for v_id, _, exp in active_vips:
            if v_id == user_id:
                expire_date = datetime.datetime.fromtimestamp(
                    exp, tz=datetime.timezone.utc
                ).strftime('%Y-%m-%d %H:%M:%S UTC')
                break
    return is_vip_status, expire_date


# ==========================================================================
# 👤 Профиль
# ==========================================================================

async def show_profile(message: Message, user_id: int):
    """Единая точка рендера карточки профиля — используется и командой, и кнопкой."""
    lang = db.get_user_language(user_id)
    is_vip_status, expire_date = _get_vip_status(user_id)
    balance = db.get_affiliate_balance(user_id)

    text = templates.get_profile_text(user_id, is_vip_status, expire_date, lang, balance)
    keyboard = templates.get_profile_keyboard(is_vip_status, lang)
    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def cmd_profile(message: Message):
    await show_profile(message, message.from_user.id)


async def process_open_profile_callback(callback: CallbackQuery):
    await callback.answer()
    await show_profile(callback.message, callback.from_user.id)


# ==========================================================================
# 💳 Пополнить баланс — единое подменю (Stars + CryptoPay), без дублей
# ==========================================================================

async def process_open_payment_menu_callback(callback: CallbackQuery):
    """Кнопка '💳 Пополнить баланс' на карточке профиля — открывает единый выбор способа оплаты."""
    await callback.answer()
    lang = db.get_user_language(callback.from_user.id)
    await callback.message.answer(
        templates.get_payment_menu_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_payment_menu_keyboard(lang)
    )


async def cmd_buy(message: Message):
    """Команда /buy — то же единое подменю оплаты, что и кнопка на профиле."""
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        templates.get_payment_menu_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_payment_menu_keyboard(lang)
    )


async def process_pay_stars_callback(callback: CallbackQuery, bot):
    """Выбор 'Telegram Stars' в подменю оплаты — отправляет инвойс Stars."""
    await callback.answer()
    await send_stars_invoice(callback.message, bot)


async def send_stars_invoice(message: Message, bot):
    """Отправляет инвойс для оплаты Telegram Stars."""
    if not bot:
        return
    prices = [LabeledPrice(label="VIP Подписка (30 дней)", amount=250)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="VIP-доступ к мониторингу кошельков",
        description="Мгновенные алерты о пробуждении спящих китов (30 дней доступа)",
        payload="vip_subscription_30_days",
        currency="XTR",
        prices=prices,
        start_parameter="vip-subscription"
    )


async def process_pre_checkout_query(pre_checkout_query, bot):
    """Подтверждение готовности к платежу (Stars)."""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


async def process_successful_payment(message: Message):
    """Обработка успешного платежа Stars за VIP-подписку."""
    payment = message.successful_payment
    user_id = message.from_user.id
    username = message.from_user.username or ""

    logger.info(
        f"Успешная транзакция Telegram Stars! Пользователь {user_id} (@{username}) "
        f"оплатил {payment.total_amount} {payment.currency}. Payload: {payment.invoice_payload}"
    )

    if payment.invoice_payload == "vip_subscription_30_days":
        db.add_vip_user(user_id, username, days=30)
        _, expire_date = _get_vip_status(user_id)

        referrer_id = db.get_referrer_for_user(user_id)
        if referrer_id:
            db.record_affiliate_commission(referrer_id, user_id, amount_usd=5.0, source="stars")

        await message.answer(
            f"🎉 <b>Оплата прошла успешно! Спасибо за покупку!</b>\n\n"
            f"⭐ Вам добавлен VIP-доступ на 30 дней.\n"
            f"📅 Подписка активна до: <b>{expire_date}</b>",
            parse_mode=ParseMode.HTML
        )


async def process_pay_cryptobot_callback(callback: CallbackQuery):
    """Выбор 'CryptoPay' в подменю оплаты — создает инвойс CryptoBot."""
    await callback.answer()
    user_id = callback.from_user.id

    pay_url = await payments.create_crypto_invoice(user_id, amount_usd=5.0)
    if pay_url:
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 Оплатить $5 в CryptoBot", url=pay_url)
        await callback.message.answer(
            "Нажмите кнопку ниже для оплаты VIP-подписки через CryptoBot:",
            reply_markup=builder.as_markup()
        )
    else:
        await callback.message.answer(
            "❌ Ошибка при создании счета. Попробуйте позже или проверьте CRYPTO_BOT_TOKEN."
        )


# ==========================================================================
# 🎁 Приглашения и заработок (часть экрана Профиль/Оплата)
# ==========================================================================

async def cmd_invite(message: Message, bot):
    bot_user = await bot.get_me() if bot else None
    bot_username = bot_user.username if bot_user else "NulladressAIBot"
    await referral_handlers.cmd_invite(message, bot_username)


async def process_open_invite_callback(callback: CallbackQuery, bot):
    await callback.answer()
    bot_user = await bot.get_me() if bot else None
    bot_username = bot_user.username if bot_user else "NulladressAIBot"
    # См. комментарий в referral_handlers.cmd_invite — callback.message
    # авторства бота, поэтому реальный user_id берем из callback.from_user.
    await referral_handlers.cmd_invite(callback.message, bot_username, user_id=callback.from_user.id)


async def cmd_balance(message: Message):
    await referral_handlers.cmd_balance(message, message.from_user.id)


async def process_open_balance_callback(callback: CallbackQuery):
    await callback.answer()
    await referral_handlers.cmd_balance(callback.message, callback.from_user.id)


async def process_request_withdraw_callback(callback: CallbackQuery):
    await referral_handlers.process_withdraw_request(callback)


async def cmd_recent(message: Message):
    """Показывает 2-3 примерных VIP-алерта — доверие и онбординг до оплаты."""
    lang = db.get_user_language(message.from_user.id)
    await message.answer(templates.get_recent_intro_text(lang), parse_mode=ParseMode.HTML)

    for ex in _RECENT_EXAMPLES:
        ai_summary = ex["ai_summary_ru"] if lang == "ru" else ex["ai_summary_en"]
        text = templates.vip_dm_alert(
            ex["label"], ex["address"], ex["dormant_days"], ex["dormant_years"],
            ex["amount_eth"], ai_summary, ex["tx_hash"], lang
        )
        await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    await message.answer(templates.get_recent_footer_text(lang), parse_mode=ParseMode.HTML)


# ==========================================================================
# Админ: выдача VIP и подтверждение выплат аффилиатам
# ==========================================================================

async def cmd_grant_vip(message: Message):
    """Админ-команда /grant_vip <user_id> <days> для выдачи VIP-доступа."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "⚠️ Использование: <code>/grant_vip &lt;user_id&gt; &lt;days&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_user_id = int(args[1])
        days = int(args[2])
    except ValueError:
        await message.answer("⚠️ Ошибка: user_id и days должны быть числами.")
        return

    db.add_vip_user(target_user_id, "", days)
    await message.answer(
        f"✅ Пользователю <code>{target_user_id}</code> успешно выдан/продлен VIP-доступ на {days} дней.",
        parse_mode=ParseMode.HTML
    )


async def cmd_payouts(message: Message):
    """Админ-команда: список ожидающих выплат аффилиатам."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    pending = db.get_pending_payouts()
    if not pending:
        await message.answer("✅ Нет ожидающих выплат.")
        return

    lines = ["💸 <b>Ожидающие выплаты:</b>\n"]
    for payout_id, user_id, amount_usd, requested_at in pending:
        lines.append(
            f"#{payout_id} — <code>{user_id}</code> — ${amount_usd:.2f} "
            f"(запрошено {requested_at.strftime('%Y-%m-%d')})\n"
            f"Подтвердить: <code>/pay {payout_id}</code>"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_pay(message: Message, bot):
    """Админ-команда /pay <payout_id> — подтверждает ручную выплату аффилиату."""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для выполнения этой команды.")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Использование: <code>/pay &lt;payout_id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    try:
        payout_id = int(args[1])
    except ValueError:
        await message.answer("⚠️ payout_id должен быть числом.")
        return

    pending = db.get_pending_payouts()
    match = next((p for p in pending if p[0] == payout_id), None)
    if not match:
        await message.answer(f"⚠️ Заявка #{payout_id} не найдена среди ожидающих.")
        return

    _, user_id, amount_usd, _ = match
    db.mark_payout_paid(payout_id, user_id, amount_usd)
    await message.answer(f"✅ Заявка #{payout_id} на ${amount_usd:.2f} отмечена как выплаченная.")

    try:
        if bot:
            await bot.send_message(
                chat_id=user_id,
                text=f"💸 Ваша выплата ${amount_usd:.2f} обработана. Спасибо, что рекомендуете нас!",
                parse_mode=ParseMode.HTML
            )
    except Exception:
        pass