from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
import database as db
import templates

# Настройки объединяют VIP-фильтры алертов И язык интерфейса — обе группы
# теперь доступны из одного главного пункта меню "⚙️ Настройки", вместо
# того чтобы язык был отдельной кнопкой на главном экране.


async def cmd_settings(message: Message):
    """Обработчик команды /settings."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)

    if not db.is_vip(user_id):
        await message.answer(
            templates.get_settings_vip_only_text(lang),
            parse_mode=ParseMode.HTML,
            reply_markup=templates.get_settings_vip_only_keyboard(lang)
        )
        return

    settings = db.get_user_settings(user_id)
    await message.answer(
        templates.get_settings_text(settings, lang),
        reply_markup=templates.get_settings_keyboard(settings, lang),
        parse_mode=ParseMode.HTML
    )


async def process_settings_callback(callback: CallbackQuery):
    """Обработчик инлайн-кнопок настроек фильтров."""
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = callback.data

    settings = db.get_user_settings(user_id)

    if data.startswith("set_dormant_"):
        val = int(data.split("_")[2])
        db.update_user_setting(user_id, "min_dormant_years", val)
    elif data == "set_amount_cycle":
        current_amount = settings.get("min_amount_eth", 10.0)
        amounts = [5.0, 10.0, 25.0, 50.0, 100.0]
        try:
            idx = amounts.index(current_amount)
            new_amount = amounts[(idx + 1) % len(amounts)]
        except ValueError:
            new_amount = 10.0
        db.update_user_setting(user_id, "min_amount_eth", new_amount)
    elif data == "toggle_notify":
        current_notify = settings.get("notify_enabled", True)
        db.update_user_setting(user_id, "notify_enabled", not current_notify)

    updated_settings = db.get_user_settings(user_id)
    await callback.message.edit_text(
        templates.get_settings_text(updated_settings, lang),
        reply_markup=templates.get_settings_keyboard(updated_settings, lang),
        parse_mode=ParseMode.HTML
    )
    await callback.answer("✓")


# ==========================================================================
# /language — язык интерфейса (теперь доступен из экрана Настроек)
# ==========================================================================

async def cmd_language(message: Message):
    """Обработчик команды /language — выбор языка интерфейса."""
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        templates.get_language_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_language_keyboard()
    )


async def open_language(message: Message, user_id: int):
    """Общая точка входа для кнопки '🌐 Язык' из экрана Настроек."""
    lang = db.get_user_language(user_id)
    await message.answer(
        templates.get_language_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_language_keyboard()
    )


async def process_set_language_callback(callback: CallbackQuery):
    """Сохраняет выбранный язык и обновляет сообщение."""
    new_lang = "ru" if callback.data == "set_lang_ru" else "en"
    db.set_user_language(callback.from_user.id, new_lang)
    await callback.answer(templates.get_language_saved_text(new_lang))
    await callback.message.edit_text(
        templates.get_language_text(new_lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_language_keyboard()
    )