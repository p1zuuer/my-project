from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
import database as db
import templates


async def cmd_invite(message: Message, bot_username: str):
    """Обработчик команды /invite."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    ref_count = db.count_referrals(user_id)

    text = templates.get_invite_text(user_id, bot_username, ref_count, lang)
    keyboard = templates.get_invite_keyboard(bot_username, user_id, lang)
    await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def cmd_balance(message_or_callback, user_id: int):
    """Показывает баланс аффилиата (pending / paid / total) и кнопку запроса выплаты."""
    lang = db.get_user_language(user_id)
    balance = db.get_affiliate_balance(user_id)
    text = templates.get_balance_text(balance, lang)
    keyboard = templates.get_balance_keyboard(lang)
    await message_or_callback.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def process_withdraw_request(callback: CallbackQuery):
    """Обработчик кнопки '💸 Request payout'."""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    balance = db.get_affiliate_balance(user_id)

    if balance["pending"] <= 0:
        await callback.answer(templates.t(lang, "withdraw_none"), show_alert=True)
        return

    db.request_payout(user_id, balance["pending"])
    await callback.answer()
    await callback.message.answer(
        templates.get_withdraw_requested_text(balance["pending"], lang),
        parse_mode=ParseMode.HTML
    )


async def handle_start_referral(message: Message) -> bool:
    """Обрабатывает аргумент ref_USERID в команде /start. Возвращает True, если реферал был учтен."""
    text = message.text or ""
    parts = text.split()
    if len(parts) < 2:
        return False

    arg = parts[1]
    if not arg.startswith("ref_"):
        return False

    lang = db.get_user_language(message.from_user.id)

    try:
        referrer_id = int(arg.replace("ref_", ""))
        referred_id = int(message.from_user.id)

        # Строгая проверка на саморефералы (дублируется и в database.add_referral —
        # здесь нужна, чтобы вернуть пользователю понятное сообщение, а не тихий отказ).
        if referrer_id == referred_id:
            await message.answer(templates.t(lang, "self_referral_block"))
            return False

        success = db.add_referral(referrer_id, referred_id)
        if success:
            try:
                if message.bot:
                    referrer_lang = db.get_user_language(referrer_id)
                    await message.bot.send_message(
                        chat_id=referrer_id,
                        text="🎉 " + templates.t(referrer_lang, "invite_count") + ": new referral joined!",
                        parse_mode=ParseMode.HTML
                    )
            except Exception:
                pass
            return True
    except Exception:
        pass

    return False