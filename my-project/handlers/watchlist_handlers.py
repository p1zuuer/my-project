"""
Личный watchlist пользователя — теперь полностью интерактивный:
/watchlist рендерит КАЖДЫЙ отслеживаемый кошелек отдельным сообщением со
своей инлайн-клавиатурой управления (Метка / Порог алертов / История /
Удалить), т.к. Telegram допускает только одну клавиатуру на сообщение —
собрать N кошельков с их собственными кнопками в одно сообщение невозможно.

Все callback_data-строки используют полный адрес (42 символа) — с самым
длинным префиксом (`wl_delok_` + адрес = 51 байт) укладываются в лимит
Telegram на callback_data (64 байта) с запасом.
"""
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
import database as db
import templates


async def cmd_track(message: Message):
    """Добавляет личный кошелек в watchlist (/track 0xADDRESS)."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    args = message.text.split()
    if len(args) < 2:
        await message.answer(templates.t(lang, "track_usage"), parse_mode=ParseMode.HTML)
        return

    address = args[1].strip()
    if not address.startswith("0x") or len(address) != 42:
        await message.answer(templates.t(lang, "track_invalid"), parse_mode=ParseMode.HTML)
        return

    is_vip_status = db.is_vip(user_id)
    success, reason = db.add_tracked_wallet(user_id, address, is_vip_status)

    if success:
        await message.answer(templates.get_track_success_text(address.lower(), lang), parse_mode=ParseMode.HTML)
    elif reason == "limit_reached":
        await message.answer(templates.get_track_limit_text(is_vip_status, lang), parse_mode=ParseMode.HTML)
    elif reason == "already_tracked":
        await message.answer(templates.t(lang, "track_already"), parse_mode=ParseMode.HTML)
    else:
        await message.answer(templates.t(lang, "track_error"), parse_mode=ParseMode.HTML)


async def cmd_watchlist(message: Message):
    """
    '📁 Мой Watchlist' — заголовок со счетчиком, затем каждый кошелек своей
    интерактивной карточкой (Row 1: Метка/Порог, Row 2: История/Удалить).
    """
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    tracked = db.list_tracked_wallets(user_id)
    is_vip_status = db.is_vip(user_id)

    summary = templates.get_watchlist_summary_text(tracked, is_vip_status, lang)
    await message.answer(summary, parse_mode=ParseMode.HTML)

    for address, label, threshold_eth in tracked:
        card_text = templates.get_wallet_card_text(address, label, threshold_eth, lang)
        card_keyboard = templates.get_wallet_card_keyboard(address, lang)
        await message.answer(card_text, parse_mode=ParseMode.HTML, reply_markup=card_keyboard,
                              disable_web_page_preview=True)


def _extract_address(callback_data: str, prefix: str) -> str:
    """Достает адрес из callback_data вида '<prefix><address>' или
    '<prefix><address>_<suffix>' (используется для порогов, например wl_thr_0x..._50)."""
    rest = callback_data[len(prefix):]
    # Адрес всегда ровно 42 символа (0x + 40 hex) в начале остатка строки.
    return rest[:42]


async def process_wallet_back_callback(callback: CallbackQuery):
    """Кнопка '◀ Назад' из подменю/истории/удаления — возвращает к карточке кошелька."""
    address = _extract_address(callback.data, "wl_back_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    row = db.get_tracked_wallet_for_owner(user_id, address)
    await callback.answer()
    if not row:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    addr, label, threshold_eth, _monitor_type = row
    await callback.message.edit_text(
        templates.get_wallet_card_text(addr, label, threshold_eth, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_wallet_card_keyboard(addr, lang)
    )


async def process_wallet_label_callback(callback: CallbackQuery, pending_state: dict):
    """Кнопка '✏️ Метка' — переводит пользователя в режим ожидания следующего
    текстового сообщения как новой метки. pending_state — общий модульный
    словарь user_id -> {"action": ..., "address": ...}, зарегистрированный в bot.py,
    проверяемый ДО автодетекта 0x-адресов в обычных текстовых сообщениях."""
    address = _extract_address(callback.data, "wl_lbl_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    row = db.get_tracked_wallet_for_owner(user_id, address)
    await callback.answer()
    if not row:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    pending_state[user_id] = {"action": "awaiting_wallet_label", "address": address}
    await callback.message.answer(templates.t(lang, "qa_label_waiting"), parse_mode=ParseMode.HTML)


async def receive_wallet_label_text(message: Message, address: str):
    """Обрабатывает текст метки, присланный после нажатия '✏️ Метка' (вызывается из bot.py,
    когда pending_state показывает 'awaiting_wallet_label')."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    label = message.text.strip()[:100]  # разумный лимит длины метки

    updated = db.update_wallet_label(user_id, address, label)
    if not updated:
        await message.answer(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    await message.answer(templates.t(lang, "qa_label_saved"), parse_mode=ParseMode.HTML)
    row = db.get_tracked_wallet_for_owner(user_id, address)
    if row:
        addr, new_label, threshold_eth, _ = row
        await message.answer(
            templates.get_wallet_card_text(addr, new_label, threshold_eth, lang),
            parse_mode=ParseMode.HTML,
            reply_markup=templates.get_wallet_card_keyboard(addr, lang)
        )


async def receive_new_wallet_label_text(message: Message, address: str):
    """
    Обрабатывает текст метки, присланный после '✍️ Добавить метку' на карточке
    автодетекта — в отличие от receive_wallet_label_text, здесь кошелек еще
    НЕ добавлен в watchlist, поэтому вызывается add_tracked_wallet с меткой
    сразу, а не update_wallet_label по уже существующей записи.
    """
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    label = message.text.strip()[:100]

    is_vip_status = db.is_vip(user_id)
    success, reason = db.add_tracked_wallet(user_id, address, is_vip_status, label=label)

    if success:
        await message.answer(templates.get_track_success_text(address, lang), parse_mode=ParseMode.HTML)
    elif reason == "limit_reached":
        await message.answer(templates.get_track_limit_text(is_vip_status, lang), parse_mode=ParseMode.HTML)
    elif reason == "already_tracked":
        await message.answer(templates.t(lang, "track_already"), parse_mode=ParseMode.HTML)
    else:
        await message.answer(templates.t(lang, "track_error"), parse_mode=ParseMode.HTML)


async def process_wallet_threshold_menu_callback(callback: CallbackQuery):
    """Кнопка '🔔 Порог алертов' — открывает подменю выбора порога."""
    address = _extract_address(callback.data, "wl_thr_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    row = db.get_tracked_wallet_for_owner(user_id, address)
    await callback.answer()
    if not row:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    addr, label, threshold_eth, _monitor_type = row
    await callback.message.edit_text(
        templates.get_threshold_submenu_text(addr, label, threshold_eth, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_threshold_submenu_keyboard(addr, lang)
    )


async def process_wallet_threshold_set_callback(callback: CallbackQuery):
    """Выбор конкретного значения порога (⚡️1 / 🚀5 / 💎10 / 🐋50 ETH)."""
    # callback.data выглядит как 'wl_thr_0xADDRESS_50'
    data = callback.data
    address = _extract_address(data, "wl_thr_")
    suffix = data[len("wl_thr_") + 42:]  # '_50' -> '50'
    try:
        threshold_value = float(suffix.lstrip("_"))
    except ValueError:
        await callback.answer("⚠️")
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    updated = db.update_wallet_threshold(user_id, address, threshold_value)
    if not updated:
        await callback.answer()
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    await callback.answer(templates.t(lang, "wl_threshold_saved").format(threshold=f"{threshold_value:.0f}"))
    row = db.get_tracked_wallet_for_owner(user_id, address)
    addr, label, new_threshold, _ = row
    await callback.message.edit_text(
        templates.get_wallet_card_text(addr, label, new_threshold, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_wallet_card_keyboard(addr, lang)
    )


async def process_wallet_history_callback(callback: CallbackQuery):
    """Кнопка '📊 История' — показывает последние сработавшие сигналы по кошельку."""
    address = _extract_address(callback.data, "wl_his_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    row = db.get_tracked_wallet_for_owner(user_id, address)
    await callback.answer()
    if not row:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    addr, label, _threshold_eth, _monitor_type = row
    history = db.get_wallet_signal_history(addr, limit=5)
    await callback.message.edit_text(
        templates.get_history_text(addr, label, history, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_history_keyboard(addr, lang)
    )


async def process_wallet_delete_prompt_callback(callback: CallbackQuery):
    """Кнопка '🗑 Удалить' — показывает подтверждение перед реальным удалением."""
    address = _extract_address(callback.data, "wl_del_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    row = db.get_tracked_wallet_for_owner(user_id, address)
    await callback.answer()
    if not row:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)
        return

    addr, label, _threshold_eth, _monitor_type = row
    await callback.message.edit_text(
        templates.get_delete_confirm_text(addr, label, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_delete_confirm_keyboard(addr, lang)
    )


async def process_wallet_delete_confirm_callback(callback: CallbackQuery):
    """Подтвержденное удаление — мягкое (is_active=FALSE), обратимо через /track заново."""
    address = _extract_address(callback.data, "wl_delok_")
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    deleted = db.deactivate_tracked_wallet(user_id, address)
    await callback.answer()
    if deleted:
        await callback.message.edit_text(templates.t(lang, "wl_deleted"), parse_mode=ParseMode.HTML)
    else:
        await callback.message.edit_text(templates.t(lang, "wl_not_found"), parse_mode=ParseMode.HTML)