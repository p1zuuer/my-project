"""
Централизованные шаблоны и i18n-система для Dormant Wallet Tracker.
Дизайн: "White & Grey Minimal" (Apple / Vercel style).

ВАЖНО: bot.py вызывает функции ТОЛЬКО через префикс `templates.` —
например `templates.get_start_text(lang)`, а не голое `get_start_text(lang)`.

Все текстовые функции принимают `lang: str` ('en' | 'ru') первым/явным
аргументом. Неизвестный код языка тихо откатывается на 'en' через _t().
"""
import html
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def _esc(text) -> str:
    """Экранирует пользовательский текст (метки кошельков и т.п.) перед вставкой
    в HTML-сообщение Telegram. Без этого метка вида '<b>' или '&' ломает
    parse_mode=HTML с ошибкой 'can't parse entities' — баг, найденный при
    аудите: метки НИКОГДА не должны попадать в HTML-шаблон сырыми."""
    return html.escape(str(text)) if text else ""

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

# Минималистичные монохромные индикаторы статуса
STATUS_DORMANT = "⚪️"
STATUS_ACTIVE = "🔘"
STATUS_VIP = "◽️"
STATUS_FREE = "▫️"


# ==========================================================================
# СЛОВАРЬ ПЕРЕВОДОВ
# ==========================================================================

TRANSLATIONS = {
    "en": {
        "start_title": "Dormant Wallet Tracker",
        "start_body": (
            "Monitoring dormant Ethereum wallets — and the moment they wake up.\n\n"
            "▫️ Free — public channel, 20 min delay\n"
            "◽️ VIP — instant DM alerts, custom filters"
        ),
        "btn_profile": "My Profile",
        "btn_buy_vip": "Get VIP",
        "btn_stats": "Network Stats",
        "btn_language": "🌐 Language",
        "btn_check_wallet": "Check Wallet",
        "btn_alert_filters": "Alert Filters",
        "btn_free_vip": "Free VIP",
        "btn_watchlist": "My Watchlist",
        "btn_profile_payment": "Profile & Payment",
        "btn_top_up": "Top Up Balance",
        "btn_renew_vip": "Renew VIP",
        "payment_menu_title": "Top Up Balance",
        "payment_menu_body": "Choose how you'd like to pay for VIP (30 days):",
        "btn_pay_stars": "Telegram Stars — 250 ⭐",
        "btn_pay_crypto": "CryptoPay (USDT) — $5",
        "btn_back_to_profile": "Back to Profile",
        "check_prompt": (
            "🔍 Send an Ethereum address (0x...) directly into this chat:\n\n"
            "The bot will instantly check the wallet's age, balance, and generate "
            "an AI activity analysis."
        ),

        "profile_title": "Account",
        "profile_id": "Telegram ID",
        "profile_status": "Status",
        "profile_status_vip": f"{STATUS_VIP} VIP — active until",
        "profile_status_free": f"{STATUS_FREE} Free",
        "btn_extend_vip": "Renew VIP · 250 Stars / 30d",
        "btn_get_vip": "Get VIP · $5 / 250 Stars",
        "btn_get_vip_crypto": "Get VIP · $5 / CryptoBot",
        "btn_settings": "Alert filters",
        "btn_invite": "Invite friends",

        "help_title": "How it works",
        "help_body": (
            "/start — welcome dashboard\n"
            "/profile — subscription status\n"
            "/buy — get or renew VIP\n"
            "/settings — alert filters (VIP)\n"
            "/track &lt;address&gt; — add a wallet to your personal alert feed\n"
            "/check &lt;address&gt; — inspect any wallet\n"
            "/recent — see example alerts before you pay\n"
            "/stats — system statistics\n"
            "/invite — referral program &amp; cash earnings\n"
            "/balance — your affiliate balance\n"
            "/language — switch interface language\n\n"
            "▫️ Free: alerts posted to the channel, 20 min delayed. 1 personal /track slot.\n"
            "◽️ VIP: the same alerts instantly, in DM, with custom filters. Up to 10 /track slots.\n\n"
            "ℹ️ This bot reports on-chain activity — it does not give financial advice."
        ),

        "settings_title": "Alert filters",
        "settings_dormant": "Min. dormant period",
        "settings_amount": "Min. transfer amount",
        "settings_notify": "Notifications",
        "settings_on": "On",
        "settings_off": "Off",
        "settings_years": "years",
        "settings_footer": "Tap a value below to change it.",
        "settings_vip_only": "Custom alert filters are a VIP feature.\nGet VIP: /buy",

        "language_title": "Interface language",
        "language_body": "Choose your language:",
        "language_saved": "Language set to English.",

        # ---- Onboarding: Step 2 (legal) & Step 3 (guide) ----
        "onboard_legal_title": "Before you start",
        "onboard_legal_body": (
            "⚠️ <b>Not financial advice.</b>\n"
            "This bot is an analytical tool. It reports on-chain activity — wallet age, balance, "
            "and transaction patterns. Nothing it sends is a recommendation to buy, sell, or hold "
            "any asset. Always do your own research.\n\n"
            "🔒 <b>Privacy.</b>\n"
            "The bot only reads public Ethereum blockchain data (via Etherscan). It does not access "
            "your private keys, funds, or any off-chain personal data beyond your Telegram ID, "
            "language preference, and alert settings, which are stored solely to operate the service."
        ),
        "btn_accept_terms": "✅ Accept & Continue",

        "onboard_guide_title": "Quick guide",
        "onboard_guide_body": (
            "One more thing — a short guide to how alerts, VIP, and /track work is here:\n\n"
            "📖 <a href=\"{guide_url}\">Read the full guide &amp; terms</a>\n\n"
            "You're all set. Tap below to open the main menu."
        ),
        "btn_start_using": "▸ Start Using Bot",

        "alert_public_title": "WALLET AWAKENED",
        "alert_vip_title": "VIP · WALLET AWAKENED",
        "alert_tracked_title": "TRACKED WALLET AWAKENED",
        "alert_label": "Label",
        "alert_wallet": "Wallet",
        "alert_dormant": "Dormant for",
        "alert_amount": "Amount",
        "alert_ai": "AI analysis",
        "alert_link": "View on Etherscan",
        "alert_public_cta": "Get this 20 minutes earlier — /buy",
        "alert_tracked_footer": "This is a personal alert from your /track watchlist.",
        "years_short": "y",
        "days_short": "d",

        # ---- Радар крупных переводов (services/radar.py) ----
        "radar_signal_title": "LARGE TRANSFER SIGNAL",
        "radar_vip_title": "VIP · LARGE TRANSFER SIGNAL",
        "radar_tracked_title": "TRACKED · LARGE TRANSFER",
        "radar_direction_sent": "sent",
        "radar_direction_received": "received",
        "radar_impact": "Market context",
        "radar_public_cta": "Get this instantly — /buy",
        "radar_tracked_footer": "This is a personal signal from your /track watchlist.",

        # ---- /track ----
        "track_usage": "Usage: <code>/track 0xADDRESS</code>",
        "track_invalid": "⚠️ Invalid Ethereum address. It must start with 0x and be 42 characters long.",
        "track_limit_free": (
            "⚪️ Free plan allows tracking <b>1</b> wallet.\n"
            "Upgrade to VIP to track up to <b>10</b> wallets — /buy"
        ),
        "track_limit_vip": "◽️ You've reached the VIP limit of <b>10</b> tracked wallets.",
        "track_already": "This address is already in your tracked list.",
        "track_success": "🔎 <b>Now tracking:</b>\n<code>{address}</code>\n\nYou'll get an instant personal alert the moment it wakes up.",
        "track_error": "❌ Could not add this wallet right now. Please try again later.",
        "track_list_title": "Your tracked wallets",
        "track_list_empty": "You're not tracking any wallets yet. Use <code>/track 0xADDRESS</code> to add one.",

        # ---- Auto-detected 0x address quick-action card ----
        "qa_card_title": "Address detected",
        "qa_card_body": "What would you like to do with this wallet?",
        "btn_qa_analyze": "🔍 Quick AI Analysis",
        "btn_qa_add": "➕ Add to Watchlist",

        # ---- Add-to-watchlist label prompt ----
        "qa_label_prompt": "Send a label for this wallet, or skip to use a default one.",
        "btn_qa_label_skip": "⚡ Save without label",
        "btn_qa_label_write": "✍️ Add a label",
        "qa_label_waiting": "✍️ Send the label as your next message.",
        "qa_label_saved": "✅ Label saved.",

        # ---- Interactive per-wallet management card ----
        "wl_card_threshold": "Alert threshold",
        "btn_wl_label": "✏️ Label",
        "btn_wl_threshold": "🔔 Alert threshold",
        "btn_wl_history": "📊 History",
        "btn_wl_delete": "🗑 Delete",
        "btn_wl_back_list": "◀ Back to Watchlist",
        "btn_wl_back_wallet": "◀ Back",

        # ---- Threshold submenu ----
        "wl_threshold_title": "Alert threshold",
        "wl_threshold_body": "Choose the minimum transfer size that triggers an alert for this wallet:",
        "wl_threshold_saved": "✅ Threshold updated to {threshold} ETH.",

        # ---- History ----
        "wl_history_title": "Signal history",
        "wl_history_empty": "No signals yet for this wallet.",
        "wl_history_dormant": "Dormant wake-up",
        "wl_history_radar": "Large transfer",

        # ---- Delete confirmation ----
        "wl_delete_confirm_title": "Remove this wallet?",
        "wl_delete_confirm_body": "This wallet will stop sending you personal alerts. You can add it again later.",
        "btn_wl_delete_confirm": "🗑 Yes, remove",
        "btn_wl_delete_cancel": "Cancel",
        "wl_deleted": "🗑 Wallet removed from your watchlist.",
        "wl_not_found": "⚠️ This wallet isn't in your watchlist (it may have already been removed).",

        # ---- /check: graceful failures + rate limit ----
        "check_usage": "Usage: <code>/check 0x...</code>",
        "check_invalid": "⚠️ Invalid Ethereum address format. It must start with 0x and be 42 characters.",
        "check_cooldown": "⏳ Please wait a few seconds before checking another wallet.",
        "check_loading": "🔄 Fetching on-chain data and running AI analysis...",
        "check_title": "Wallet check",
        "check_address": "Address",
        "check_label": "Label",
        "check_label_unknown": "Unlabeled",
        "check_balance": "Balance",
        "check_tx_count": "Total transactions",
        "check_last_active": "Last active",
        "check_days_ago": "days ago",
        "check_data_unavailable": "⚠️ Live network node timeout, retrying — data below may be incomplete.",
        "check_error_generic": "❌ Something went wrong while checking this wallet. Please try again in a moment.",

        # ---- /stats ----
        "stats_title": "Network Stats",
        "stats_wallets": "Wallets monitored",
        "stats_alerts": "Alerts triggered (all-time)",
        "stats_vips": "Active VIP members",
        "stats_referrals": "Referrals made",
        "stats_eth_price": "ETH price",

        # ---- /invite + affiliate earnings ----
        "invite_title": "Referral Program",
        "invite_body": "Invite friends and get rewarded — for free, or for cash.",
        "invite_count": "Referrals",
        "invite_link": "Your referral link",
        "invite_share_hint": "Just send this link to a friend.",
        "invite_share_text": "I'm tracking dormant Ethereum whales with this bot — check it out!",
        "btn_share": "📤 Share link",
        "invite_earn_title": "▪️ Earn cash, not just VIP days",
        "invite_earn_body": (
            "When someone you invite buys VIP, you earn <b>20%</b> of what they paid — "
            "in real money, credited to your balance."
        ),
        "invite_balance_pending": "Pending",
        "invite_balance_paid": "Paid out",
        "invite_balance_total": "Total earned",
        "btn_balance": "▪️ My balance",
        "btn_withdraw": "💸 Request payout",
        "withdraw_none": "You have no pending balance to withdraw.",
        "withdraw_requested": "✅ Payout of <b>${amount}</b> requested. We'll process it within 48h.",
        "self_referral_block": "You cannot register yourself as a referral.",

        # ---- /recent (trust & onboarding) ----
        "recent_title": "Recent Whale Awakenings",
        "recent_intro": "Here's exactly what a VIP alert looks like — full AI analysis included.",
        "recent_disclaimer": (
            "ℹ️ This is informational, not financial advice. The bot reports on-chain activity — "
            "what you do with that information is your call."
        ),
        "recent_cta": "Want alerts like this the instant they happen? — /buy",
    },
    "ru": {
        "start_title": "Dormant Wallet Tracker",
        "start_body": (
            "Отслеживаем спящие Ethereum-кошельки — и момент их пробуждения.\n\n"
            "▫️ Free — публичный канал, задержка 20 минут\n"
            "◽️ VIP — мгновенные алерты в личку, гибкие фильтры"
        ),
        "btn_profile": "Мой профиль",
        "btn_buy_vip": "Купить VIP",
        "btn_stats": "Статистика сети",
        "btn_language": "🌐 Язык",
        "btn_check_wallet": "Проверить кошелек",
        "btn_alert_filters": "Фильтры алертов",
        "btn_free_vip": "Бесплатный VIP",
        "btn_watchlist": "Мой Watchlist",
        "btn_profile_payment": "Профиль и Оплата",
        "btn_top_up": "Пополнить баланс",
        "btn_renew_vip": "Продлить VIP",
        "payment_menu_title": "Пополнить баланс",
        "payment_menu_body": "Выберите способ оплаты VIP (30 дней):",
        "btn_pay_stars": "Telegram Stars — 250 ⭐",
        "btn_pay_crypto": "CryptoPay (USDT) — $5",
        "btn_back_to_profile": "Назад в профиль",
        "check_prompt": (
            "🔍 Отправьте Ethereum-адрес (0x...) прямо в этот чат:\n\n"
            "Бот мгновенно проверит возраст кошелька, баланс и сформирует "
            "AI-анализ активности."
        ),

        "profile_title": "Аккаунт",
        "profile_id": "Telegram ID",
        "profile_status": "Статус",
        "profile_status_vip": f"{STATUS_VIP} VIP — активен до",
        "profile_status_free": f"{STATUS_FREE} Free",
        "btn_extend_vip": "Продлить VIP · 250 Stars / 30д",
        "btn_get_vip": "Купить VIP · $5 / 250 Stars",
        "btn_get_vip_crypto": "Купить VIP · $5 / CryptoBot",
        "btn_settings": "Фильтры алертов",
        "btn_invite": "Пригласить друзей",

        "help_title": "Как это работает",
        "help_body": (
            "/start — главный экран\n"
            "/profile — статус подписки\n"
            "/buy — купить или продлить VIP\n"
            "/settings — фильтры алертов (VIP)\n"
            "/track &lt;адрес&gt; — добавить кошелек в личный список алертов\n"
            "/check &lt;адрес&gt; — проверить любой кошелек\n"
            "/recent — примеры алертов до оплаты\n"
            "/stats — статистика системы\n"
            "/invite — реферальная программа и денежные выплаты\n"
            "/balance — ваш баланс аффилиата\n"
            "/language — сменить язык интерфейса\n\n"
            "▫️ Free: алерты в канале с задержкой 20 минут. 1 личный слот /track.\n"
            "◽️ VIP: те же алерты мгновенно, в личку, с гибкими фильтрами. До 10 слотов /track.\n\n"
            "ℹ️ Бот сообщает об ончейн-активности — это не финансовая рекомендация."
        ),

        "settings_title": "Фильтры алертов",
        "settings_dormant": "Мин. срок спячки",
        "settings_amount": "Мин. сумма перевода",
        "settings_notify": "Уведомления",
        "settings_on": "Вкл",
        "settings_off": "Выкл",
        "settings_years": "лет",
        "settings_footer": "Нажмите на значение ниже, чтобы изменить его.",
        "settings_vip_only": "Персональные фильтры — VIP-функция.\nКупить VIP: /buy",

        "language_title": "Язык интерфейса",
        "language_body": "Выберите язык:",
        "language_saved": "Язык переключен на русский.",

        # ---- Онбординг: шаг 2 (юридический) и шаг 3 (гайд) ----
        "onboard_legal_title": "Перед началом работы",
        "onboard_legal_body": (
            "⚠️ <b>Это не финансовая рекомендация.</b>\n"
            "Бот — аналитический инструмент. Он сообщает об ончейн-активности: возраст кошелька, "
            "баланс, паттерны транзакций. Ничего из отправленного не является рекомендацией "
            "покупать, продавать или держать какой-либо актив. Всегда проводите собственное исследование.\n\n"
            "🔒 <b>Конфиденциальность.</b>\n"
            "Бот использует только публичные данные блокчейна Ethereum (через Etherscan). Он не имеет "
            "доступа к вашим приватным ключам, средствам или любым другим личным данным, кроме вашего "
            "Telegram ID, языка интерфейса и настроек алертов, которые хранятся исключительно для работы сервиса."
        ),
        "btn_accept_terms": "✅ Принять и продолжить",

        "onboard_guide_title": "Краткий гайд",
        "onboard_guide_body": (
            "И последнее — короткий гайд о том, как работают алерты, VIP и /track:\n\n"
            "📖 <a href=\"{guide_url}\">Читать гайд и условия использования</a>\n\n"
            "Все готово. Нажмите кнопку ниже, чтобы открыть главное меню."
        ),
        "btn_start_using": "▸ Открыть главное меню",

        "alert_public_title": "КОШЕЛЕК ПРОБУДИЛСЯ",
        "alert_vip_title": "VIP · КОШЕЛЕК ПРОБУДИЛСЯ",
        "alert_tracked_title": "ОТСЛЕЖИВАЕМЫЙ КОШЕЛЕК ПРОБУДИЛСЯ",
        "alert_label": "Метка",
        "alert_wallet": "Кошелек",
        "alert_dormant": "Спал",
        "alert_amount": "Сумма",
        "alert_ai": "AI-анализ",
        "alert_link": "Смотреть на Etherscan",
        "alert_public_cta": "Получайте это на 20 минут раньше — /buy",
        "alert_tracked_footer": "Это личный алерт из вашего списка /track.",
        "years_short": "г",
        "days_short": "д",

        # ---- Радар крупных переводов (services/radar.py) ----
        "radar_signal_title": "СИГНАЛ: КРУПНЫЙ ПЕРЕВОД",
        "radar_vip_title": "VIP · СИГНАЛ: КРУПНЫЙ ПЕРЕВОД",
        "radar_tracked_title": "ОТСЛЕЖИВАЕТСЯ · КРУПНЫЙ ПЕРЕВОД",
        "radar_direction_sent": "отправил",
        "radar_direction_received": "получил",
        "radar_impact": "Рыночный контекст",
        "radar_public_cta": "Получайте это мгновенно — /buy",
        "radar_tracked_footer": "Это личный сигнал из вашего списка /track.",

        # ---- /track ----
        "track_usage": "Использование: <code>/track 0xADDRESS</code>",
        "track_invalid": "⚠️ Неверный формат Ethereum-адреса. Должен начинаться с 0x и содержать 42 символа.",
        "track_limit_free": (
            "⚪️ На Free-тарифе доступен <b>1</b> отслеживаемый кошелек.\n"
            "Оформите VIP, чтобы отслеживать до <b>10</b> кошельков — /buy"
        ),
        "track_limit_vip": "◽️ Достигнут VIP-лимит в <b>10</b> отслеживаемых кошельков.",
        "track_already": "Этот адрес уже в вашем списке отслеживания.",
        "track_success": "🔎 <b>Теперь отслеживается:</b>\n<code>{address}</code>\n\nВы получите личный мгновенный алерт, как только он проснется.",
        "track_error": "❌ Не удалось добавить кошелек. Попробуйте позже.",
        "track_list_title": "Ваши отслеживаемые кошельки",
        "track_list_empty": "Вы пока ничего не отслеживаете. Используйте <code>/track 0xADDRESS</code>, чтобы добавить.",

        # ---- Карточка быстрых действий для обнаруженного адреса ----
        "qa_card_title": "Адрес обнаружен",
        "qa_card_body": "Что вы хотите сделать с этим кошельком?",
        "btn_qa_analyze": "🔍 Быстрый AI-Анализ",
        "btn_qa_add": "➕ Добавить в Watchlist",

        # ---- Запрос метки при добавлении ----
        "qa_label_prompt": "Отправьте метку для этого кошелька, либо пропустите — будет использована метка по умолчанию.",
        "btn_qa_label_skip": "⚡ Сохранить без метки",
        "btn_qa_label_write": "✍️ Добавить метку",
        "qa_label_waiting": "✍️ Отправьте метку следующим сообщением.",
        "qa_label_saved": "✅ Метка сохранена.",

        # ---- Интерактивная карточка управления кошельком ----
        "wl_card_threshold": "Порог алертов",
        "btn_wl_label": "✏️ Метка",
        "btn_wl_threshold": "🔔 Порог алертов",
        "btn_wl_history": "📊 История",
        "btn_wl_delete": "🗑 Удалить",
        "btn_wl_back_list": "◀ Назад к Watchlist",
        "btn_wl_back_wallet": "◀ Назад",

        # ---- Подменю порога алертов ----
        "wl_threshold_title": "Порог алертов",
        "wl_threshold_body": "Выберите минимальный размер перевода, при котором сработает алерт для этого кошелька:",
        "wl_threshold_saved": "✅ Порог обновлен: {threshold} ETH.",

        # ---- История ----
        "wl_history_title": "История сигналов",
        "wl_history_empty": "Пока нет сигналов по этому кошельку.",
        "wl_history_dormant": "Пробуждение",
        "wl_history_radar": "Крупный перевод",

        # ---- Подтверждение удаления ----
        "wl_delete_confirm_title": "Удалить этот кошелек?",
        "wl_delete_confirm_body": "Вы перестанете получать личные алерты по нему. Позже можно добавить снова.",
        "btn_wl_delete_confirm": "🗑 Да, удалить",
        "btn_wl_delete_cancel": "Отмена",
        "wl_deleted": "🗑 Кошелек удален из вашего watchlist.",
        "wl_not_found": "⚠️ Этот кошелек не найден в вашем watchlist (возможно, уже удален).",

        # ---- /check: graceful failures + rate limit ----
        "check_usage": "Использование: <code>/check 0x...</code>",
        "check_invalid": "⚠️ Неверный формат Ethereum-адреса. Должен начинаться с 0x и содержать 42 символа.",
        "check_cooldown": "⏳ Подождите несколько секунд перед следующей проверкой.",
        "check_loading": "🔄 Получаем ончейн-данные и запускаем AI-анализ...",
        "check_title": "Проверка кошелька",
        "check_address": "Адрес",
        "check_label": "Метка",
        "check_label_unknown": "Без метки",
        "check_balance": "Баланс",
        "check_tx_count": "Всего транзакций",
        "check_last_active": "Последняя активность",
        "check_days_ago": "дней назад",
        "check_data_unavailable": "⚠️ Таймаут узла сети, повторная попытка — данные ниже могут быть неполными.",
        "check_error_generic": "❌ Что-то пошло не так при проверке кошелька. Попробуйте еще раз через минуту.",

        # ---- /stats ----
        "stats_title": "Статистика сети",
        "stats_wallets": "Отслеживается кошельков",
        "stats_alerts": "Сработавших алертов (всего)",
        "stats_vips": "Активных VIP",
        "stats_referrals": "Приглашено рефералов",
        "stats_eth_price": "Цена ETH",

        # ---- /invite + affiliate earnings ----
        "invite_title": "Реферальная программа",
        "invite_body": "Приглашайте друзей и получайте награду — бесплатную или денежную.",
        "invite_count": "Рефералов",
        "invite_link": "Ваша реферальная ссылка",
        "invite_share_hint": "Просто отправьте эту ссылку другу.",
        "invite_share_text": "Слежу за пробуждением спящих Ethereum-китов через этого бота — залетай!",
        "btn_share": "📤 Поделиться ссылкой",
        "invite_earn_title": "▪️ Зарабатывайте деньги, а не только VIP-дни",
        "invite_earn_body": (
            "Когда приглашенный вами друг покупает VIP, вы получаете <b>20%</b> от суммы оплаты — "
            "реальными деньгами на баланс."
        ),
        "invite_balance_pending": "В ожидании",
        "invite_balance_paid": "Выплачено",
        "invite_balance_total": "Всего заработано",
        "btn_balance": "▪️ Мой баланс",
        "btn_withdraw": "💸 Запросить выплату",
        "withdraw_none": "У вас нет средств для вывода.",
        "withdraw_requested": "✅ Запрос на выплату <b>${amount}</b> отправлен. Обработаем в течение 48 часов.",
        "self_referral_block": "Нельзя зарегистрировать самого себя как реферала.",

        # ---- /recent (trust & onboarding) ----
        "recent_title": "Недавние пробуждения китов",
        "recent_intro": "Вот как именно выглядит VIP-алерт — с полным AI-анализом.",
        "recent_disclaimer": (
            "ℹ️ Это информация, а не финансовая рекомендация. Бот сообщает об ончейн-активности — "
            "что делать с этой информацией, решаете только вы."
        ),
        "recent_cta": "Хотите получать такие алерты мгновенно? — /buy",
    },
}


def _t(lang: str, key: str) -> str:
    """Достает строку перевода; неизвестный язык или ключ откатывается на 'en'."""
    lang = lang if lang in TRANSLATIONS else "en"
    return TRANSLATIONS[lang].get(key, TRANSLATIONS["en"].get(key, key))


# Публичный алиас для использования из других модулей (check_handlers, stats_handlers,
# referral_handlers) — избегаем внешних обращений к "приватному" _t().
def t(lang: str, key: str) -> str:
    return _t(lang, key)


# ==========================================================================
# /start
# ==========================================================================

def get_start_text(lang: str = "en") -> str:
    return (
        f"🌐 <b>{_t(lang, 'start_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'start_body')}"
    )


def get_start_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Главное меню — 2x3, расширено с исходного 2x2 (было явно намеренным
    ограничением, но §9 брифа сам флагнул это как "worth a UX pass", т.к.
    /stats и /invite существовали, но были нигде не видны на главном экране):

        [ 🔍 Check Wallet ]     [ 📁 My Watchlist ]
        [ 👤 Profile & Payment ] [ ⚙️ Settings ]
        [ 📊 Network Stats ]    [ ◇ Invite Friends ]
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🔍 {_t(lang, 'btn_check_wallet')}", callback_data="prompt_check_wallet"),
            InlineKeyboardButton(text=f"📁 {_t(lang, 'btn_watchlist')}", callback_data="open_watchlist"),
        ],
        [
            InlineKeyboardButton(text=f"👤 {_t(lang, 'btn_profile_payment')}", callback_data="open_profile"),
            InlineKeyboardButton(text=f"⚙️ {_t(lang, 'btn_settings')}", callback_data="open_settings"),
        ],
        [
            InlineKeyboardButton(text=f"📊 {_t(lang, 'btn_stats')}", callback_data="open_stats"),
            InlineKeyboardButton(text=f"◇ {_t(lang, 'btn_invite')}", callback_data="open_invite"),
        ],
    ])


def get_check_wallet_prompt(lang: str = "en") -> str:
    return _t(lang, "check_prompt")


# ==========================================================================
# 📁 Watchlist — список личных отслеживаемых кошельков (/track add)
# ==========================================================================

def get_watchlist_summary_text(tracked: list, is_vip: bool, lang: str = "en") -> str:
    """Заголовочное сообщение /watchlist — счетчик + лимит. Каждый кошелек
    рендерится ОТДЕЛЬНЫМ сообщением со своей собственной интерактивной
    клавиатурой (см. get_wallet_card_text/keyboard), т.к. Telegram
    прикрепляет одну инлайн-клавиатуру к одному сообщению."""
    limit = 10 if is_vip else 1
    if not tracked:
        limit_note = _t(lang, "track_limit_vip") if is_vip else _t(lang, "track_limit_free")
        return (
            f"📁 <b>{_t(lang, 'track_list_title')}</b>\n"
            f"{DIVIDER}\n\n"
            f"{_t(lang, 'track_list_empty')}\n\n"
            f"{limit_note}"
        )
    return (
        f"📁 <b>{_t(lang, 'track_list_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{len(tracked)}/{limit} · <code>/track 0xADDRESS</code>"
    )


def get_wallet_card_text(address: str, label: str, threshold_eth: float, lang: str = "en") -> str:
    """Карточка одного отслеживаемого кошелька с интерактивными кнопками управления."""
    return (
        f"👛 <b>{_esc(label) or address}</b>\n"
        f"{DIVIDER}\n"
        f"├ <code>{address}</code>\n"
        f"└ {_t(lang, 'wl_card_threshold')}: <code>{threshold_eth:.0f} ETH</code>"
    )


def get_wallet_card_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Row 1: [ ✏️ Метка ] [ 🔔 Порог алертов ]
    Row 2: [ 📊 История ] [ 🗑 Удалить ]
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_t(lang, "btn_wl_label"), callback_data=f"wl_lbl_{address}"),
            InlineKeyboardButton(text=_t(lang, "btn_wl_threshold"), callback_data=f"wl_thr_{address}"),
        ],
        [
            InlineKeyboardButton(text=_t(lang, "btn_wl_history"), callback_data=f"wl_his_{address}"),
            InlineKeyboardButton(text=_t(lang, "btn_wl_delete"), callback_data=f"wl_del_{address}"),
        ],
    ])


# ---- 🔔 Порог алертов (подменю) ----

WALLET_THRESHOLD_OPTIONS = [1.0, 5.0, 10.0, 50.0]
_THRESHOLD_ICONS = {1.0: "⚡️", 5.0: "▸", 10.0: "◆", 50.0: "◈"}


def get_threshold_submenu_text(address: str, label: str, current_threshold: float, lang: str = "en") -> str:
    return (
        f"🔔 <b>{_t(lang, 'wl_threshold_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_esc(label) or address}\n"
        f"└ {_t(lang, 'wl_card_threshold')}: <code>{current_threshold:.0f} ETH</code>\n\n"
        f"{_t(lang, 'wl_threshold_body')}"
    )


def get_threshold_submenu_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    row = []
    for val in WALLET_THRESHOLD_OPTIONS:
        icon = _THRESHOLD_ICONS.get(val, "◦")
        row.append(InlineKeyboardButton(
            text=f"{icon} {val:.0f} ETH",
            callback_data=f"wl_thr_{address}_{val:.0f}"
        ))
    return InlineKeyboardMarkup(inline_keyboard=[
        row,
        [InlineKeyboardButton(text=_t(lang, "btn_wl_back_wallet"), callback_data=f"wl_back_{address}")],
    ])


# ---- 📊 История ----

def get_history_text(address: str, label: str, history: list, lang: str = "en") -> str:
    header = f"📊 <b>{_t(lang, 'wl_history_title')}</b>\n{DIVIDER}\n├ {_esc(label) or address}\n"

    if not history:
        return header + f"└ {_t(lang, 'wl_history_empty')}"

    lines = [header.rstrip("\n")]
    for i, (kind, triggered_at, amount_eth, extra) in enumerate(history):
        prefix = "└" if i == len(history) - 1 else "├"
        date_str = triggered_at.strftime("%Y-%m-%d %H:%M") if triggered_at else "—"
        kind_label = _t(lang, "wl_history_dormant") if kind == "dormant" else _t(lang, "wl_history_radar")
        amount_str = f"{amount_eth:.2f} ETH" if amount_eth is not None else "—"
        lines.append(f"{prefix} <code>{date_str}</code> · {kind_label} · {amount_str}")

    return "\n".join(lines)


def get_history_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_wl_back_wallet"), callback_data=f"wl_back_{address}")],
    ])


# ---- 🗑 Удаление ----

def get_delete_confirm_text(address: str, label: str, lang: str = "en") -> str:
    return (
        f"🗑 <b>{_t(lang, 'wl_delete_confirm_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_esc(label) or address}\n"
        f"└ <code>{address}</code>\n\n"
        f"{_t(lang, 'wl_delete_confirm_body')}"
    )


def get_delete_confirm_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_t(lang, "btn_wl_delete_confirm"), callback_data=f"wl_delok_{address}"),
            InlineKeyboardButton(text=_t(lang, "btn_wl_delete_cancel"), callback_data=f"wl_back_{address}"),
        ],
    ])


# ==========================================================================
# Auto-detect: карточка быстрых действий для 0x-адреса, отправленного в чат
# ==========================================================================

def get_quick_address_card_text(address: str, lang: str = "en") -> str:
    return (
        f"👛 <b>{_t(lang, 'qa_card_title')}</b>\n"
        f"{DIVIDER}\n"
        f"└ <code>{address}</code>\n\n"
        f"{_t(lang, 'qa_card_body')}"
    )


def get_quick_address_card_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_t(lang, "btn_qa_analyze"), callback_data=f"qa_ai_{address}"),
            InlineKeyboardButton(text=_t(lang, "btn_qa_add"), callback_data=f"qa_add_{address}"),
        ],
    ])


def get_label_prompt_text(lang: str = "en") -> str:
    return _t(lang, "qa_label_prompt")


def get_label_prompt_keyboard(address: str, lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=_t(lang, "btn_qa_label_write"), callback_data=f"qa_lbl_{address}"),
            InlineKeyboardButton(text=_t(lang, "btn_qa_label_skip"), callback_data=f"qa_skip_{address}"),
        ],
    ])


# ==========================================================================
# 👤 Профиль и Оплата
# ==========================================================================

def get_profile_text(user_id: int, is_vip: bool, expire_date: str = None,
                      lang: str = "en", balance: dict = None) -> str:
    if is_vip:
        status_line = f"{_t(lang, 'profile_status_vip')} <code>{expire_date}</code>"
    else:
        status_line = _t(lang, "profile_status_free")

    lines = [
        f"◽️ <b>{_t(lang, 'profile_title')}</b>",
        DIVIDER,
        f"├ {_t(lang, 'profile_id')}: <code>{user_id}</code>",
    ]

    if balance and balance.get("pending", 0) > 0:
        # Одна строка-тизер баланса аффилиата — полная разбивка доступна
        # отдельно через "◇ Пригласить и заработать", без дублирования здесь.
        lines.append(f"├ {_t(lang, 'profile_status')}: {status_line}")
        lines.append(f"└ {_t(lang, 'invite_balance_pending')}: <code>${balance['pending']:.2f}</code>")
    else:
        lines.append(f"└ {_t(lang, 'profile_status')}: {status_line}")

    return "\n".join(lines)


def get_profile_keyboard(is_vip: bool, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Единая точка входа в оплату — одна кнопка "▫️ Пополнить баланс" вместо двух
    прежних (Stars и CryptoBot отдельно), которые вели к одной и той же покупке
    и дублировали друг друга на карточке профиля.
    """
    top_up_label = _t(lang, "btn_renew_vip") if is_vip else _t(lang, "btn_top_up")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"▫️ {top_up_label}", callback_data="open_payment_menu")],
        [InlineKeyboardButton(text=f"◇ {_t(lang, 'btn_invite')}", callback_data="open_invite")],
    ])


# ==========================================================================
# ▫️ Пополнить баланс — единое подменю оплаты (Stars + CryptoPay)
# ==========================================================================

def get_payment_menu_text(lang: str = "en") -> str:
    return (
        f"▫️ <b>{_t(lang, 'payment_menu_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'payment_menu_body')}"
    )


def get_payment_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐ {_t(lang, 'btn_pay_stars')}", callback_data="pay_stars")],
        [InlineKeyboardButton(text=f"◆ {_t(lang, 'btn_pay_crypto')}", callback_data="pay_cryptobot")],
        [InlineKeyboardButton(text=f"◀ {_t(lang, 'btn_back_to_profile')}", callback_data="open_profile")],
    ])


# ==========================================================================
# /help
# ==========================================================================

def get_help_text(lang: str = "en") -> str:
    return (
        f"⚙️ <b>{_t(lang, 'help_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'help_body')}"
    )


# ==========================================================================
# /settings
# ==========================================================================

def get_settings_vip_only_text(lang: str = "en") -> str:
    return _t(lang, "settings_vip_only")


def get_settings_vip_only_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Free-пользователи не видят фильтры алертов, но Настройки теперь пункт
    ГЛАВНОГО меню — язык интерфейса должен оставаться доступным всем, а не
    только VIP, иначе Free-пользователь теряет способ сменить язык.
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_language"), callback_data="open_language")],
    ])


def get_settings_text(settings: dict, lang: str = "en") -> str:
    min_dormant = settings.get("min_dormant_years", 3)
    min_amount = settings.get("min_amount_eth", 10.0)
    notify_enabled = settings.get("notify_enabled", True)
    notify_str = _t(lang, "settings_on") if notify_enabled else _t(lang, "settings_off")

    return (
        f"⚙️ <b>{_t(lang, 'settings_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'settings_dormant')}: <code>{min_dormant} {_t(lang, 'settings_years')}</code>\n"
        f"├ {_t(lang, 'settings_amount')}: <code>{min_amount} ETH</code>\n"
        f"└ {_t(lang, 'settings_notify')}: <code>{notify_str}</code>\n\n"
        f"{_t(lang, 'settings_footer')}"
    )


def get_settings_keyboard(settings: dict, lang: str = "en") -> InlineKeyboardMarkup:
    min_dormant = settings.get("min_dormant_years", 3)
    min_amount = settings.get("min_amount_eth", 10.0)
    notify_enabled = settings.get("notify_enabled", True)
    notify_text = f"🔘 {_t(lang, 'settings_on')}" if notify_enabled else f"⚪️ {_t(lang, 'settings_off')}"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⚪️ {_t(lang, 'settings_dormant')}: {min_dormant} {_t(lang, 'settings_years')}",
            callback_data=f"set_dormant_{min_dormant % 5 + 1}"
        )],
        [InlineKeyboardButton(
            text=f"⚪️ {_t(lang, 'settings_amount')}: {min_amount} ETH",
            callback_data="set_amount_cycle"
        )],
        [InlineKeyboardButton(text=notify_text, callback_data="toggle_notify")],
        [InlineKeyboardButton(text=_t(lang, "btn_language"), callback_data="open_language")],
    ])


# ==========================================================================
# /language
# ==========================================================================

def get_language_text(lang: str = "en") -> str:
    return (
        f"🌐 <b>{_t(lang, 'language_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'language_body')}"
    )


def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang_en"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru"),
        ]
    ])


def get_language_saved_text(lang: str) -> str:
    return f"🌐 {_t(lang, 'language_saved')}"


# ==========================================================================
# АЛЕРТЫ — Free / VIP (минималистичные сигнальные карточки)
# ==========================================================================

def public_channel_alert(label: str, address: str, dormant_days: int, dormant_years: float,
                          amount_eth: float, ai_summary: str, tx_hash: str, lang: str = "en") -> str:
    y = _t(lang, "years_short")
    d = _t(lang, "days_short")
    return (
        f"⚪️ <b>{_t(lang, 'alert_public_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"├ {_t(lang, 'alert_dormant')}: <code>{dormant_days}{d} (~{dormant_years}{y})</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code>\n\n"
        f"🔍 <b>{_t(lang, 'alert_ai')}</b>\n{ai_summary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>\n\n"
        f"{DIVIDER}\n"
        f"◽️ {_t(lang, 'alert_public_cta')}"
    )


def vip_dm_alert(label: str, address: str, dormant_days: int, dormant_years: float,
                  amount_eth: float, ai_summary: str, tx_hash: str, lang: str = "en") -> str:
    y = _t(lang, "years_short")
    d = _t(lang, "days_short")
    return (
        f"◽️ <b>{_t(lang, 'alert_vip_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"├ {_t(lang, 'alert_dormant')}: <code>{dormant_days}{d} (~{dormant_years}{y})</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code>\n\n"
        f"🔍 <b>{_t(lang, 'alert_ai')}</b>\n{ai_summary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>"
    )


def tracked_wallet_alert(label: str, address: str, dormant_days: int, dormant_years: float,
                          amount_eth: float, ai_summary: str, tx_hash: str, lang: str = "en") -> str:
    """Личный алерт по адресу, добавленному пользователем через /track (доступно на Free)."""
    y = _t(lang, "years_short")
    d = _t(lang, "days_short")
    return (
        f"🔎 <b>{_t(lang, 'alert_tracked_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"├ {_t(lang, 'alert_dormant')}: <code>{dormant_days}{d} (~{dormant_years}{y})</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code>\n\n"
        f"🔍 <b>{_t(lang, 'alert_ai')}</b>\n{ai_summary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>\n\n"
        f"{_t(lang, 'alert_tracked_footer')}"
    )


# ==========================================================================
# Радар крупных переводов (services/radar.py) — три варианта доставки:
# публичный канал, VIP мгновенный, личный /track — тот же light-grey стиль.
# ==========================================================================

def _radar_direction_label(direction: str, lang: str) -> str:
    """direction приходит из services/radar.py уже как русское слово
    ('отправил'/'получил') — эта функция нормализует его под текущий язык
    вывода, чтобы radar.py не зависел от языка пользователя."""
    if direction in ("sent", "отправил"):
        return _t(lang, "radar_direction_sent")
    return _t(lang, "radar_direction_received")


def radar_public_alert(label: str, address: str, amount_eth: float, direction: str,
                        ai_commentary: str, tx_hash: str, lang: str = "en") -> str:
    dir_label = _radar_direction_label(direction, lang)
    return (
        f"⚪️ <b>{_t(lang, 'radar_signal_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code> ({dir_label})\n\n"
        f"🔍 <b>{_t(lang, 'radar_impact')}</b>\n{ai_commentary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>\n\n"
        f"{DIVIDER}\n"
        f"◽️ {_t(lang, 'radar_public_cta')}"
    )


def radar_vip_alert(label: str, address: str, amount_eth: float, direction: str,
                     ai_commentary: str, tx_hash: str, lang: str = "en") -> str:
    dir_label = _radar_direction_label(direction, lang)
    return (
        f"◽️ <b>{_t(lang, 'radar_vip_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code> ({dir_label})\n\n"
        f"🔍 <b>{_t(lang, 'radar_impact')}</b>\n{ai_commentary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>"
    )


def radar_tracked_alert(label: str, address: str, amount_eth: float, direction: str,
                         ai_commentary: str, tx_hash: str, lang: str = "en") -> str:
    """Личный радар-сигнал по адресу, добавленному пользователем через /track."""
    dir_label = _radar_direction_label(direction, lang)
    return (
        f"🔎 <b>{_t(lang, 'radar_tracked_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'alert_label')}: <code>{_esc(label)}</code>\n"
        f"├ {_t(lang, 'alert_wallet')}: <code>{address}</code>\n"
        f"└ {_t(lang, 'alert_amount')}: <code>{amount_eth:.4f} ETH</code> ({dir_label})\n\n"
        f"🔍 <b>{_t(lang, 'radar_impact')}</b>\n{ai_commentary}\n\n"
        f"🌐 <a href=\"https://etherscan.io/tx/{tx_hash}\">{_t(lang, 'alert_link')}</a>\n\n"
        f"{_t(lang, 'radar_tracked_footer')}"
    )


# ==========================================================================
# /track
# ==========================================================================

def get_track_limit_text(is_vip: bool, lang: str = "en") -> str:
    return _t(lang, "track_limit_vip") if is_vip else _t(lang, "track_limit_free")


def get_track_success_text(address: str, lang: str = "en") -> str:
    return _t(lang, "track_success").format(address=address)


# ==========================================================================
# /check — минималистичная карточка + честная обработка ошибок API
# ==========================================================================

def get_check_result_text(snapshot: dict, ai_analysis: str, lang: str = "en") -> str:
    address = snapshot.get("address", "")
    label = snapshot.get("label") or _t(lang, "check_label_unknown")
    balance_ok = snapshot.get("balance_ok", True)
    tx_ok = snapshot.get("tx_ok", True)

    balance_line = (
        f"<code>{snapshot.get('balance', 0)} ETH</code>"
        if balance_ok else f"<code>—</code> ⚠️"
    )
    tx_line = (
        f"<code>{snapshot.get('tx_count', 0)}</code>"
        if tx_ok else f"<code>—</code> ⚠️"
    )
    last_active_line = (
        f"<code>{snapshot.get('last_active_days', 0)} {_t(lang, 'check_days_ago')}</code>"
        if tx_ok else f"<code>—</code> ⚠️"
    )

    body = (
        f"🔍 <b>{_t(lang, 'check_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'check_address')}: <code>{address}</code>\n"
        f"├ {_t(lang, 'check_label')}: <b>{_esc(label)}</b>\n"
        f"├ {_t(lang, 'check_balance')}: {balance_line}\n"
        f"├ {_t(lang, 'check_tx_count')}: {tx_line}\n"
        f"└ {_t(lang, 'check_last_active')}: {last_active_line}\n\n"
        f"{ai_analysis}"
    )

    if not balance_ok or not tx_ok:
        body += f"\n\n{_t(lang, 'check_data_unavailable')}"

    return body


# ==========================================================================
# /stats
# ==========================================================================

def get_stats_text(summary: dict, eth_price: float, lang: str = "en") -> str:
    return (
        f"📊 <b>{_t(lang, 'stats_title')}</b>\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'stats_wallets')}: <code>{summary.get('total_wallets', 0):,}</code>\n"
        f"├ {_t(lang, 'stats_alerts')}: <code>{summary.get('total_alerts', 0):,}</code>\n"
        f"├ {_t(lang, 'stats_vips')}: <code>{summary.get('active_vips', 0):,}</code>\n"
        f"└ {_t(lang, 'stats_referrals')}: <code>{summary.get('total_referrals', 0):,}</code>\n\n"
        f"🌐 {_t(lang, 'stats_eth_price')}: <code>${eth_price:,.2f}</code>"
    )


# ==========================================================================
# /invite — реферальная карточка + денежные комиссии
# ==========================================================================

def get_invite_text(user_id: int, bot_username: str, ref_count: int, lang: str = "en") -> str:
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    return (
        f"🔍 <b>{_t(lang, 'invite_title')}</b>\n"
        f"{DIVIDER}\n"
        f"{_t(lang, 'invite_body')}\n\n"
        f"├ {_t(lang, 'invite_count')}: <b>{ref_count}</b>\n"
        f"└ {_t(lang, 'invite_link')}:\n<code>{ref_link}</code>\n\n"
        f"{_t(lang, 'invite_share_hint')}\n\n"
        f"{DIVIDER}\n"
        f"{_t(lang, 'invite_earn_title')}\n"
        f"{_t(lang, 'invite_earn_body')}"
    )


def get_invite_keyboard(bot_username: str, user_id: int, lang: str = "en") -> InlineKeyboardMarkup:
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    share_url = f"https://t.me/share/url?url={ref_link}&text={_t(lang, 'invite_share_text')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_share"), url=share_url)],
        [InlineKeyboardButton(text=_t(lang, "btn_balance"), callback_data="open_balance")],
    ])


def get_balance_text(balance: dict, lang: str = "en") -> str:
    return (
        f"{_t(lang, 'invite_earn_title')}\n"
        f"{DIVIDER}\n"
        f"├ {_t(lang, 'invite_balance_pending')}: <code>${balance['pending']:.2f}</code>\n"
        f"├ {_t(lang, 'invite_balance_paid')}: <code>${balance['paid']:.2f}</code>\n"
        f"└ {_t(lang, 'invite_balance_total')}: <code>${balance['total']:.2f}</code>"
    )


def get_balance_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_withdraw"), callback_data="request_withdraw")]
    ])


def get_withdraw_requested_text(amount: float, lang: str = "en") -> str:
    return _t(lang, "withdraw_requested").format(amount=f"{amount:.2f}")


# ==========================================================================
# /recent — доверие и онбординг перед оплатой
# ==========================================================================

def get_recent_intro_text(lang: str = "en") -> str:
    return (
        f"🔍 <b>{_t(lang, 'recent_title')}</b>\n"
        f"{DIVIDER}\n"
        f"{_t(lang, 'recent_intro')}"
    )


def get_recent_footer_text(lang: str = "en") -> str:
    return f"{_t(lang, 'recent_disclaimer')}\n\n◽️ {_t(lang, 'recent_cta')}"


# ==========================================================================
# ONBOARDING — Step 1: language / Step 2: legal / Step 3: guide
# ==========================================================================

def get_onboarding_language_text() -> str:
    """Нейтральный двуязычный текст — язык еще не выбран, показываем оба варианта сразу."""
    return "🌐 <b>Welcome / Добро пожаловать</b>\n\nPlease choose your language:\nПожалуйста, выберите язык:"


def get_onboarding_language_keyboard() -> InlineKeyboardMarkup:
    """Отдельный callback_data (onboard_lang_*) от /language, чтобы не путать шаг онбординга
    с последующей сменой языка через настройки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="onboard_lang_en"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="onboard_lang_ru"),
        ]
    ])


def get_legal_text(lang: str = "en") -> str:
    return (
        f"📋 <b>{_t(lang, 'onboard_legal_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'onboard_legal_body')}"
    )


def get_legal_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_accept_terms"), callback_data="accept_terms")]
    ])


def get_guide_text(lang: str = "en", guide_url: str = "") -> str:
    return (
        f"📖 <b>{_t(lang, 'onboard_guide_title')}</b>\n"
        f"{DIVIDER}\n\n"
        f"{_t(lang, 'onboard_guide_body').format(guide_url=guide_url)}"
    )


def get_guide_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "btn_start_using"), callback_data="open_main_menu")]
    ])