import asyncio
import datetime
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramConflictError

from ai_analyst import generate_osint_summary
from handlers import profile_handlers, check_handlers, watchlist_handlers, settings_handlers, stats_handlers, referral_handlers
import database as db
import templates

logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера для aiogram 3.x
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID") else 0
PUBLIC_ALERT_DELAY_SECONDS = int(os.getenv("PUBLIC_ALERT_DELAY_SECONDS", "1200"))
# Язык публичного канала (канал один на всех, персональный i18n тут не применим)
PUBLIC_CHANNEL_LANGUAGE = os.getenv("PUBLIC_CHANNEL_LANGUAGE", "en")
# Telegra.ph гайды — отдельная ссылка на каждый язык, для Instant View в Telegram.
# Замените на реальные опубликованные страницы перед продакшн-деплоем.
TELEGRAPH_GUIDE_URL_EN = os.getenv("TELEGRAPH_GUIDE_URL_EN", "https://telegra.ph/Dormant-Wallet-Tracker-Guide-EN")
TELEGRAPH_GUIDE_URL_RU = os.getenv("TELEGRAPH_GUIDE_URL_RU", "https://telegra.ph/Dormant-Wallet-Tracker-Guide-RU")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()


def _guide_url(lang: str) -> str:
    return TELEGRAPH_GUIDE_URL_RU if lang == "ru" else TELEGRAPH_GUIDE_URL_EN


async def _send_main_menu(message_or_callback_message: types.Message, user_id: int):
    """Рендерит главное меню (Step 4 онбординга). 2x2 сетка — единственная точка
    входа во все остальные экраны (Профиль/Оплата, Watchlist, Настройки, Проверка)."""
    lang = db.get_user_language(user_id)
    await message_or_callback_message.answer(
        templates.get_start_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_start_keyboard(lang)
    )


# ==========================================================================
# /start + строгий пошаговый онбординг
# ==========================================================================
#
# Step 1: выбор языка (только кнопки, без главного меню)          -> onboard_lang_en/ru
# Step 2: юридический дисклеймер на выбранном языке                -> accept_terms
# Step 3: гайд (Telegra.ph, Instant View) на выбранном языке        -> open_main_menu
# Step 4: главное меню (2x2: Check / Watchlist / Profile+Pay / Settings)
#
# Повторный /start у пользователя с terms_accepted=True сразу ведет в Step 4.

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start: реферал -> проверка онбординга -> Step 1 или Step 4."""
    await referral_handlers.handle_start_referral(message)
    user_id = message.from_user.id

    if db.get_terms_accepted(user_id):
        await _send_main_menu(message, user_id)
        return

    await message.answer(
        templates.get_onboarding_language_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_onboarding_language_keyboard()
    )


@dp.callback_query(lambda c: c.data in ("onboard_lang_en", "onboard_lang_ru"))
async def process_onboarding_language_callback(callback_query: types.CallbackQuery):
    """Step 1 -> Step 2: сохраняет язык, показывает юридический дисклеймер на этом языке."""
    lang = "ru" if callback_query.data == "onboard_lang_ru" else "en"
    user_id = callback_query.from_user.id
    db.set_user_language(user_id, lang)

    await callback_query.answer()
    await callback_query.message.edit_text(
        templates.get_legal_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_legal_keyboard(lang)
    )


@dp.callback_query(lambda c: c.data == "accept_terms")
async def process_accept_terms_callback(callback_query: types.CallbackQuery):
    """Step 2 -> Step 3: отмечает принятие условий, показывает гайд (Telegra.ph)."""
    user_id = callback_query.from_user.id
    lang = db.get_user_language(user_id)
    db.set_terms_accepted(user_id, True)

    await callback_query.answer()
    await callback_query.message.edit_text(
        templates.get_guide_text(lang, guide_url=_guide_url(lang)),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_guide_keyboard(lang),
        disable_web_page_preview=False
    )


@dp.callback_query(lambda c: c.data == "open_main_menu")
async def process_open_main_menu_callback(callback_query: types.CallbackQuery):
    """Step 3 -> Step 4: открывает главное меню."""
    await callback_query.answer()
    await _send_main_menu(callback_query.message, callback_query.from_user.id)


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    lang = db.get_user_language(message.from_user.id)
    await message.answer(templates.get_help_text(lang), parse_mode=ParseMode.HTML)


# ==========================================================================
# 👤 Профиль и Оплата (handlers/profile_handlers.py)
# ==========================================================================

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    await profile_handlers.cmd_profile(message)


@dp.callback_query(lambda c: c.data == "open_profile")
async def process_open_profile_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_open_profile_callback(callback_query)


@dp.callback_query(lambda c: c.data == "open_payment_menu")
async def process_open_payment_menu_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_open_payment_menu_callback(callback_query)


@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    await profile_handlers.cmd_buy(message)


@dp.callback_query(lambda c: c.data == "pay_stars")
async def process_pay_stars_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_pay_stars_callback(callback_query, bot)


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    await profile_handlers.process_pre_checkout_query(pre_checkout_query, bot)


@dp.message(lambda message: message.successful_payment is not None)
async def process_successful_payment(message: types.Message):
    await profile_handlers.process_successful_payment(message)


@dp.callback_query(lambda c: c.data == "pay_cryptobot")
async def process_pay_cryptobot_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_pay_cryptobot_callback(callback_query)


@dp.message(Command("invite"))
async def cmd_invite(message: types.Message):
    await profile_handlers.cmd_invite(message, bot)


@dp.callback_query(lambda c: c.data == "open_invite")
async def process_open_invite_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_open_invite_callback(callback_query, bot)


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    await profile_handlers.cmd_balance(message)


@dp.callback_query(lambda c: c.data == "open_balance")
async def process_open_balance_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_open_balance_callback(callback_query)


@dp.callback_query(lambda c: c.data == "request_withdraw")
async def process_request_withdraw_callback(callback_query: types.CallbackQuery):
    await profile_handlers.process_request_withdraw_callback(callback_query)


@dp.message(Command("recent"))
async def cmd_recent(message: types.Message):
    await profile_handlers.cmd_recent(message)


@dp.message(Command("payouts"))
async def cmd_payouts(message: types.Message):
    await profile_handlers.cmd_payouts(message)


@dp.message(Command("pay"))
async def cmd_pay(message: types.Message):
    await profile_handlers.cmd_pay(message, bot)


@dp.message(Command("grant_vip"))
async def cmd_grant_vip(message: types.Message):
    await profile_handlers.cmd_grant_vip(message)


# ==========================================================================
# ⚙️ Настройки — фильтры алертов + язык (handlers/settings_handlers.py)
# ==========================================================================

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    await settings_handlers.cmd_settings(message)


@dp.callback_query(lambda c: c.data == "open_settings")
async def process_open_settings_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await settings_handlers.cmd_settings(callback_query.message, user_id=callback_query.from_user.id)


@dp.callback_query(
    lambda c: c.data and (
        c.data.startswith("set_dormant_")
        or c.data == "set_amount_cycle"
        or c.data == "toggle_notify"
    )
)
async def process_settings_callback(callback_query: types.CallbackQuery):
    await settings_handlers.process_settings_callback(callback_query)


@dp.message(Command("language"))
async def cmd_language(message: types.Message):
    await settings_handlers.cmd_language(message)


@dp.callback_query(lambda c: c.data == "open_language")
async def process_open_language_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await settings_handlers.open_language(callback_query.message, callback_query.from_user.id)


@dp.callback_query(lambda c: c.data in ("set_lang_en", "set_lang_ru"))
async def process_set_language_callback(callback_query: types.CallbackQuery):
    await settings_handlers.process_set_language_callback(callback_query)


# ==========================================================================
# 📊 /stats — сохранен как прямая команда (не на главном экране, но доступен)
# ==========================================================================

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await stats_handlers.cmd_stats(message)


# ==========================================================================
# 🔍 Проверить кошелек (handlers/check_handlers.py)
# ==========================================================================

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    await check_handlers.cmd_check(message)


@dp.callback_query(lambda c: c.data == "prompt_check_wallet")
async def process_prompt_check_wallet_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    lang = db.get_user_language(callback_query.from_user.id)
    await callback_query.message.answer(templates.get_check_wallet_prompt(lang))


@dp.callback_query(lambda c: c.data.startswith("qa_ai_"))
async def process_qa_ai_callback(callback_query: types.CallbackQuery):
    """Кнопка '🔍 Быстрый AI-Анализ' с карточки автодетекта адреса."""
    await check_handlers.process_quick_ai_callback(callback_query)


# ==========================================================================
# Ожидание текстового ввода (метка кошелька) — простой in-memory pending-state,
# без aiogram FSM. Регистрация ЭТОГО хендлера ДОЛЖНА идти раньше автодетекта
# 0x-адресов ниже: aiogram проверяет message-хендлеры в порядке регистрации,
# и здесь порядок в файле — это порядок приоритета.
# ==========================================================================

_pending_actions: dict = {}  # user_id -> {"action": str, "address": str}


@dp.message(lambda m: m.from_user.id in _pending_actions)
async def process_pending_text_input(message: types.Message):
    """Перехватывает следующее текстовое сообщение пользователя, если он
    находится в состоянии ожидания ввода метки (после ✏️ Метка или ✍️ Добавить метку)."""
    pending = _pending_actions.pop(message.from_user.id)
    action = pending["action"]
    address = pending["address"]

    if action == "awaiting_wallet_label":
        await watchlist_handlers.receive_wallet_label_text(message, address)
    elif action == "awaiting_new_wallet_label":
        await watchlist_handlers.receive_new_wallet_label_text(message, address)


@dp.message(
    lambda message: message.text
    and message.text.strip().startswith("0x")
    and len(message.text.strip()) == 42
)
async def process_wallet_auto_detect(message: types.Message):
    """
    Автоматический перехват Ethereum-адресов, отправленных строкой в чат.
    Раньше сразу запускал полную проверку (/check) — теперь показывает
    легкую карточку быстрых действий, а полный AI-анализ выполняется только
    по явному нажатию кнопки, чтобы не тратить Etherscan/Gemini квоту и не
    упираться в rate limit на каждое случайно вставленное сообщение с адресом.
    """
    address = message.text.strip().lower()
    lang = db.get_user_language(message.from_user.id)
    await message.answer(
        templates.get_quick_address_card_text(address, lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_quick_address_card_keyboard(address, lang)
    )


# ==========================================================================
# ➕ Добавить в Watchlist (из карточки автодетекта)
# ==========================================================================

@dp.callback_query(lambda c: c.data.startswith("qa_add_"))
async def process_qa_add_callback(callback_query: types.CallbackQuery):
    """➕ Добавить в Watchlist — предлагает указать метку или сохранить с дефолтной."""
    address = callback_query.data[len("qa_add_"):]
    lang = db.get_user_language(callback_query.from_user.id)
    await callback_query.answer()
    await callback_query.message.answer(
        templates.get_label_prompt_text(lang),
        parse_mode=ParseMode.HTML,
        reply_markup=templates.get_label_prompt_keyboard(address, lang)
    )


@dp.callback_query(lambda c: c.data.startswith("qa_skip_"))
async def process_qa_skip_label_callback(callback_query: types.CallbackQuery):
    """⚡ Сохранить без метки — сразу добавляет кошелек с настройками по умолчанию."""
    address = callback_query.data[len("qa_skip_"):]
    user_id = callback_query.from_user.id
    lang = db.get_user_language(user_id)

    is_vip_status = db.is_vip(user_id)
    success, reason = db.add_tracked_wallet(user_id, address, is_vip_status)

    await callback_query.answer()
    if success:
        await callback_query.message.edit_text(
            templates.get_track_success_text(address, lang), parse_mode=ParseMode.HTML
        )
    elif reason == "limit_reached":
        await callback_query.message.edit_text(
            templates.get_track_limit_text(is_vip_status, lang), parse_mode=ParseMode.HTML
        )
    elif reason == "already_tracked":
        await callback_query.message.edit_text(templates.t(lang, "track_already"), parse_mode=ParseMode.HTML)
    else:
        await callback_query.message.edit_text(templates.t(lang, "track_error"), parse_mode=ParseMode.HTML)


@dp.callback_query(lambda c: c.data.startswith("qa_lbl_"))
async def process_qa_write_label_callback(callback_query: types.CallbackQuery):
    """✍️ Добавить метку — переводит в режим ожидания текста, дальше см. process_pending_text_input."""
    address = callback_query.data[len("qa_lbl_"):]
    user_id = callback_query.from_user.id
    lang = db.get_user_language(user_id)

    _pending_actions[user_id] = {"action": "awaiting_new_wallet_label", "address": address}
    await callback_query.answer()
    await callback_query.message.answer(templates.t(lang, "qa_label_waiting"), parse_mode=ParseMode.HTML)


# ==========================================================================
# 📁 Мой Watchlist (handlers/watchlist_handlers.py) — интерактивное управление
# ==========================================================================

@dp.message(Command("track"))
async def cmd_track(message: types.Message):
    await watchlist_handlers.cmd_track(message)


@dp.message(Command("watchlist"))
async def cmd_watchlist(message: types.Message):
    await watchlist_handlers.cmd_watchlist(message)


@dp.callback_query(lambda c: c.data == "open_watchlist")
async def process_open_watchlist_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await watchlist_handlers.cmd_watchlist(callback_query.message, user_id=callback_query.from_user.id)


@dp.callback_query(lambda c: c.data == "open_stats")
async def process_open_stats_callback(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await stats_handlers.cmd_stats(callback_query.message, user_id=callback_query.from_user.id)


@dp.callback_query(lambda c: c.data.startswith("wl_lbl_"))
async def process_wl_label_callback(callback_query: types.CallbackQuery):
    """✏️ Метка — переводит в режим ожидания текста для существующего кошелька."""
    await watchlist_handlers.process_wallet_label_callback(callback_query, _pending_actions)


@dp.callback_query(
    lambda c: c.data.startswith("wl_thr_")
    and len(c.data) == len("wl_thr_") + 42
)
async def process_wl_threshold_menu_callback(callback_query: types.CallbackQuery):
    """🔔 Порог алертов — открывает подменю выбора значения."""
    await watchlist_handlers.process_wallet_threshold_menu_callback(callback_query)


@dp.callback_query(
    lambda c: c.data.startswith("wl_thr_")
    and len(c.data) > len("wl_thr_") + 42
)
async def process_wl_threshold_set_callback(callback_query: types.CallbackQuery):
    """Выбор конкретного значения порога (⚡️1 / 🚀5 / 💎10 / 🐋50 ETH)."""
    await watchlist_handlers.process_wallet_threshold_set_callback(callback_query)


@dp.callback_query(lambda c: c.data.startswith("wl_his_"))
async def process_wl_history_callback(callback_query: types.CallbackQuery):
    """📊 История — последние сработавшие сигналы по кошельку."""
    await watchlist_handlers.process_wallet_history_callback(callback_query)


@dp.callback_query(lambda c: c.data.startswith("wl_del_") and not c.data.startswith("wl_delok_"))
async def process_wl_delete_prompt_callback(callback_query: types.CallbackQuery):
    """🗑 Удалить — показывает подтверждение перед удалением."""
    await watchlist_handlers.process_wallet_delete_prompt_callback(callback_query)


@dp.callback_query(lambda c: c.data.startswith("wl_delok_"))
async def process_wl_delete_confirm_callback(callback_query: types.CallbackQuery):
    """Подтвержденное удаление кошелька из watchlist."""
    await watchlist_handlers.process_wallet_delete_confirm_callback(callback_query)


@dp.callback_query(lambda c: c.data.startswith("wl_back_"))
async def process_wl_back_callback(callback_query: types.CallbackQuery):
    """◀ Назад — возврат к карточке кошелька из подменю/истории/удаления."""
    await watchlist_handlers.process_wallet_back_callback(callback_query)


# ==========================================================================
# Алерты (VIP мгновенные + публичные отложенные + личный /track)
# ==========================================================================

async def send_vip_alerts(alert_data: dict):
    """Отправляет алерт МГНОВЕННО всем активным VIP-пользователям с учетом их фильтров."""
    if not bot:
        logger.error("Telegram Bot не инициализирован!")
        return

    active_vips = db.get_active_vips()
    if not active_vips:
        logger.info("Нет активных VIP-пользователей для мгновенной рассылки.")
        return

    label = alert_data.get("label", "Unknown")
    address = alert_data.get("address", "")
    dormant_days = alert_data.get("dormant_days", 0)
    dormant_years = round(dormant_days / 365.25, 1)
    amount_eth = alert_data.get("amount_eth", 0.0)
    tx_hash = alert_data.get("tx_hash", "")

    # Найденный баг: раньше ai_summary генерировался ОДИН раз здесь (всегда
    # на русском) и переиспользовался для ВСЕХ VIP независимо от их
    # language_code — англоязычные VIP получали русский AI-текст внутри
    # английского шаблона. Теперь генерируем максимум 2 версии (ru/en) и
    # кэшируем по языку, лениво — не по одному вызову Gemini на пользователя.
    ai_summary_by_lang = {}

    for user_id, _, _ in active_vips:
        user_settings = db.get_user_settings(user_id)
        if not user_settings.get("notify_enabled", True):
            continue
        if dormant_years < user_settings.get("min_dormant_years", 3):
            continue
        if amount_eth < user_settings.get("min_amount_eth", 10.0):
            continue

        user_lang = user_settings.get("language_code", "en")
        if user_lang not in ai_summary_by_lang:
            ai_summary_by_lang[user_lang] = await generate_osint_summary(alert_data, lang=user_lang)
        ai_summary = ai_summary_by_lang[user_lang]

        text = templates.vip_dm_alert(
            label, address, dormant_days, dormant_years, amount_eth, ai_summary, tx_hash, user_lang
        )

        try:
            await bot.send_message(
                chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"VIP алерт успешно отправлен пользователю {user_id}")
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limit для {user_id}. Ожидание {e.retry_after}с...")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(
                    chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except Exception as retry_err:
                logger.error(f"Повторная ошибка при отправке {user_id}: {retry_err}")
        except TelegramForbiddenError:
            logger.warning(f"Пользователь {user_id} заблокировал бота. Пропускаем.")
        except Exception as e:
            logger.error(f"Ошибка при отправке VIP алерта {user_id}: {e}")


async def schedule_public_alert(alert_data: dict, delay_seconds: int = None):
    """Создает фоновую задачу, которая ждет delay_seconds, затем постит в канал."""
    if delay_seconds is None:
        delay_seconds = PUBLIC_ALERT_DELAY_SECONDS

    async def _delayed_task():
        try:
            logger.info(
                f"Отложенная задача публичного алерта для {alert_data.get('address')} "
                f"на {delay_seconds} секунд."
            )
            await asyncio.sleep(delay_seconds)

            if not bot or not CHANNEL_ID:
                logger.error("Telegram Bot Token или Channel ID не настроены!")
                return

            label = alert_data.get("label", "Unknown")
            address = alert_data.get("address", "")
            dormant_days = alert_data.get("dormant_days", 0)
            dormant_years = round(dormant_days / 365.25, 1)
            amount_eth = alert_data.get("amount_eth", 0.0)
            tx_hash = alert_data.get("tx_hash", "")

            ai_summary = await generate_osint_summary(alert_data, lang=PUBLIC_CHANNEL_LANGUAGE)
            text = templates.public_channel_alert(
                label, address, dormant_days, dormant_years, amount_eth, ai_summary, tx_hash,
                PUBLIC_CHANNEL_LANGUAGE
            )

            try:
                await bot.send_message(
                    chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info(f"Публичный алерт отправлен в канал {CHANNEL_ID}")
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limit в канале. Ожидание {e.retry_after}с...")
                await asyncio.sleep(e.retry_after)
                await bot.send_message(
                    chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
            except Exception as channel_err:
                logger.error(f"Ошибка при отправке в канал: {channel_err}")
        except Exception as e:
            logger.error(f"Ошибка в отложенной задаче публичного алерта: {e}")

    return asyncio.create_task(_delayed_task())


async def send_alert(alert_data: dict):
    """Совместимость со старым вызовом: мгновенный VIP + отложенный публичный."""
    await send_vip_alerts(alert_data)
    await schedule_public_alert(alert_data)


async def send_personal_tracked_alert(user_id: int, alert_data: dict):
    """Мгновенный личный алерт для пользователя, который лично отслеживает этот адрес через /track."""
    if not bot:
        logger.error("Telegram Bot не инициализирован!")
        return

    label = alert_data.get("label", "Unknown")
    address = alert_data.get("address", "")
    dormant_days = alert_data.get("dormant_days", 0)
    dormant_years = round(dormant_days / 365.25, 1)
    amount_eth = alert_data.get("amount_eth", 0.0)
    tx_hash = alert_data.get("tx_hash", "")

    lang = db.get_user_language(user_id)
    ai_summary = await generate_osint_summary(alert_data, lang=lang)
    text = templates.tracked_wallet_alert(
        label, address, dormant_days, dormant_years, amount_eth, ai_summary, tx_hash, lang
    )

    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True)
        logger.info(f"Личный /track алерт отправлен пользователю {user_id} по адресу {address}")
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=True)
        except Exception as retry_err:
            logger.error(f"Повторная ошибка личного алерта {user_id}: {retry_err}")
    except TelegramForbiddenError:
        logger.warning(f"Пользователь {user_id} заблокировал бота. /track алерт пропущен.")
    except Exception as e:
        logger.error(f"Ошибка при отправке личного /track алерта {user_id}: {e}")


# ==========================================================================
# Радар крупных переводов (services/radar.py) — три пути доставки сигнала:
# VIP мгновенно + публичный канал с задержкой (seed-адреса из радар-листа),
# либо личный мгновенный сигнал (пользовательские /track адреса).
# ==========================================================================

async def send_radar_vip_alerts(signal: dict):
    """Мгновенная рассылка радар-сигнала всем активным VIP (с учетом их фильтров по сумме)."""
    if not bot:
        logger.error("Telegram Bot не инициализирован!")
        return

    active_vips = db.get_active_vips()
    if not active_vips:
        return

    label = signal["label"]
    address = signal["address"]
    amount_eth = signal["amount_eth"]
    direction = signal["direction"]
    tx_hash = signal["tx_hash"]

    for user_id, _, _ in active_vips:
        user_settings = db.get_user_settings(user_id)
        if not user_settings.get("notify_enabled", True):
            continue
        if amount_eth < user_settings.get("min_amount_eth", 10.0):
            continue

        user_lang = user_settings.get("language_code", "en")
        # Найденный баг: раньше здесь всегда бралось signal["ai_commentary"]
        # (жестко зашитый русский вариант) — англоязычные VIP получали
        # русский рыночный комментарий. Теперь выбираем нужную языковую
        # версию, сгенерированную заранее в radar.analyze_transactions().
        ai_commentary = signal.get(f"ai_commentary_{user_lang}") or signal.get("ai_commentary") or ""
        text = templates.radar_vip_alert(label, address, amount_eth, direction, ai_commentary, tx_hash, user_lang)

        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=True)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
            except Exception as retry_err:
                logger.error(f"Radar: повторная ошибка VIP-рассылки {user_id}: {retry_err}")
        except TelegramForbiddenError:
            logger.warning(f"Radar: пользователь {user_id} заблокировал бота.")
        except Exception as e:
            logger.error(f"Radar: ошибка VIP-рассылки {user_id}: {e}")


async def schedule_radar_public_alert(signal: dict, delay_seconds: int = None):
    """Отложенная публикация радар-сигнала в публичный канал (та же задержка, что и для дормант-алертов)."""
    if delay_seconds is None:
        delay_seconds = PUBLIC_ALERT_DELAY_SECONDS

    async def _delayed_task():
        try:
            await asyncio.sleep(delay_seconds)
            if not bot or not CHANNEL_ID:
                logger.error("Telegram Bot Token или Channel ID не настроены!")
                return

            ai_commentary = signal.get(f"ai_commentary_{PUBLIC_CHANNEL_LANGUAGE}") or signal.get("ai_commentary") or ""
            text = templates.radar_public_alert(
                signal["label"], signal["address"], signal["amount_eth"], signal["direction"],
                ai_commentary, signal["tx_hash"], PUBLIC_CHANNEL_LANGUAGE
            )
            try:
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after)
                await bot.send_message(chat_id=CHANNEL_ID, text=text, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
            except Exception as channel_err:
                logger.error(f"Radar: ошибка публикации в канал: {channel_err}")
        except Exception as e:
            logger.error(f"Radar: ошибка в отложенной задаче: {e}")

    return asyncio.create_task(_delayed_task())


async def send_personal_radar_alert(user_id: int, signal: dict):
    """Мгновенный личный радар-сигнал по адресу, который пользователь отслеживает через /track."""
    if not bot:
        logger.error("Telegram Bot не инициализирован!")
        return

    lang = db.get_user_language(user_id)
    ai_commentary = signal.get(f"ai_commentary_{lang}") or signal.get("ai_commentary") or ""
    text = templates.radar_tracked_alert(
        signal["label"], signal["address"], signal["amount_eth"], signal["direction"],
        ai_commentary, signal["tx_hash"], lang
    )

    try:
        await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML,
                                    disable_web_page_preview=True)
        except Exception as retry_err:
            logger.error(f"Radar: повторная ошибка личного сигнала {user_id}: {retry_err}")
    except TelegramForbiddenError:
        logger.warning(f"Radar: пользователь {user_id} заблокировал бота.")
    except Exception as e:
        logger.error(f"Radar: ошибка личного сигнала {user_id}: {e}")


# ==========================================================================
# Health check + main
# ==========================================================================

async def handle_health_check(request):
    return web.Response(text="200 OK", status=200)


async def start_web_server():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get("/", handle_health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check веб-сервер aiohttp запущен на порту {port}")


async def main():
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не найден в .env!")
        return

    logger.info("Запуск Telegram-бота и фонового мониторинга кошельков...")
    logger.warning("If TelegramConflictError occurs, ensure no local instances are running alongside Render deployment.")

    db.init_db()

    from checker import main as checker_main
    from services import payments

    web_server_task = asyncio.create_task(start_web_server())
    checker_task = asyncio.create_task(checker_main())

    try:
        cryptopay_task = asyncio.create_task(payments.check_invoices(bot))
    except Exception as e:
        logger.error(f"Не удалось запустить фоновую задачу CryptoBot: {e}")
        cryptopay_task = None

    try:
        await bot.delete_webhook(drop_pending_updates=True)

        retry_count = 0
        max_retries = 3
        while retry_count < max_retries:
            try:
                await dp.start_polling(bot)
                break
            except TelegramConflictError:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                logger.warning("Polling conflict detected. Waiting 7 seconds for lingering connection to close...")
                await asyncio.sleep(7)
    finally:
        checker_task.cancel()
        web_server_task.cancel()
        if cryptopay_task:
            cryptopay_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    import sys
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем.")