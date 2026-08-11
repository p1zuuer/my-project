import os
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Tuple
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Не бросаем исключение при импорте модуля — иначе весь бот падает при
    # старте вместо явного, диагностируемого сообщения об ошибке в момент
    # первого реального обращения к БД.
    import logging
    logging.getLogger(__name__).warning(
        "DATABASE_URL не задан в окружении — все обращения к БД будут падать "
        "с явным ValueError при первом вызове get_connection()."
    )


@contextmanager
def get_connection():
    """
    Контекстный менеджер подключения к PostgreSQL.

    ВАЖНО (найденный баг): раньше эта функция просто возвращала
    `psycopg2.connect(...)`, и весь код использовал ее как
    `with get_connection() as conn:`. У объекта psycopg2-соединения
    `__exit__` управляет ТОЛЬКО транзакцией (commit/rollback) — соединение
    физически НЕ закрывается. При десятках вызовов в каждом 30-секундном
    цикле checker.py это медленно исчерпывало лимит подключений на
    serverless Postgres (Neon), что могло проявляться как случайные,
    трудно воспроизводимые сбои под нагрузкой.

    Теперь `get_connection()` сама является контекстным менеджером и
    гарантированно закрывает соединение в `finally` — при этом ВСЕ 30
    существующих мест вызова вида `with get_connection() as conn:`
    продолжают работать без изменений, т.к. синтаксис идентичен.
    """
    if not DATABASE_URL:
        raise ValueError("Переменная окружения DATABASE_URL не задана в .env")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Инициализирует структуры таблиц в PostgreSQL."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            # Таблица кошельков
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    address TEXT PRIMARY KEY,
                    label TEXT,
                    last_tx_hash TEXT,
                    last_active_timestamp BIGINT
                )
            """)

            # Таблица зафиксированных алертов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts_history (
                    id SERIAL PRIMARY KEY,
                    address TEXT,
                    tx_hash TEXT UNIQUE,
                    dormant_days INTEGER,
                    amount_eth DOUBLE PRECISION,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица VIP пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vip_users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    expire_timestamp BIGINT
                )
            """)

            # Таблица обработанных инвойсов CryptoBot для предотвращения повторной активации
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_invoices (
                    invoice_id BIGINT PRIMARY KEY,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица пользовательских настроек фильтров
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT PRIMARY KEY,
                    min_dormant_years INT DEFAULT 3,
                    min_amount_eth FLOAT DEFAULT 10.0,
                    notify_enabled BOOLEAN DEFAULT TRUE
                )
            """)

            # i18n: язык интерфейса пользователя (en по умолчанию)
            cursor.execute("""
                ALTER TABLE user_settings
                ADD COLUMN IF NOT EXISTS language_code VARCHAR(10) DEFAULT 'en'
            """)

            # Онбординг: принял ли пользователь условия использования / дисклеймер
            cursor.execute("""
                ALTER TABLE user_settings
                ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN DEFAULT FALSE
            """)

            # Таблица рефералов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    referrer_id BIGINT,
                    referred_id BIGINT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица реферальных наград
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_rewards (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT,
                    referred_id BIGINT,
                    reward_days INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица кэша адресов для быстрой экспресс-проверки
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS address_cache (
                    address TEXT PRIMARY KEY,
                    data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Индексы для alerts_history
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_history_triggered_at ON alerts_history (triggered_at);
                CREATE INDEX IF NOT EXISTS idx_alerts_history_address ON alerts_history (address);
            """)

            # ==================================================================
            # WATCHLIST: гибридная система — куратор (seed) + пользовательский /track
            # ==================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    address TEXT UNIQUE NOT NULL,
                    label TEXT,
                    source TEXT NOT NULL DEFAULT 'seed',   -- 'seed' (куратор) или 'user' (личный /track)
                    added_by BIGINT,                        -- user_id, если source='user'; NULL для seed
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist (is_active)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_added_by ON watchlist (added_by)")

            # monitor_type различает ДВЕ независимые системы обнаружения, обе
            # работающие поверх одной и той же таблицы watchlist:
            #   'dormant' — детектор пробуждения спящих китов (существующий,
            #               365+ дней без активности -> первая транзакция)
            #   'radar'   — новый радар крупных переводов (лимит по сумме,
            #               работает на ЛЮБых, в т.ч. постоянно активных
            #               кошельках вроде биржевых hot wallet)
            #   'both'    — для пользовательских /track записей по умолчанию:
            #               пользователь получает максимум пользы с одного слота
            cursor.execute("""
                ALTER TABLE watchlist
                ADD COLUMN IF NOT EXISTS monitor_type TEXT NOT NULL DEFAULT 'dormant'
            """)

            # Порог радара крупных переводов — теперь настраивается ПЕР-КОШЕЛЕК
            # вместо единого глобального значения (services/radar.py читает это
            # поле вместо константы THRESHOLD_ETH).
            cursor.execute("""
                ALTER TABLE watchlist
                ADD COLUMN IF NOT EXISTS alert_threshold_eth DOUBLE PRECISION NOT NULL DEFAULT 10.0
            """)

            # radar_seen — отдельное состояние дедупликации для радара крупных
            # переводов. Намеренно ОТДЕЛЬНАЯ таблица от `wallets` (которая
            # хранит last_tx_hash для расчета dormant_days) — семантика разная:
            # дормант-детектору нужен ПРЕДЫДУЩИЙ tx как точка отсчета для
            # вычисления периода спячки, радару нужен просто "последний
            # обработанный tx", чтобы не дублировать алерты. Смешивание этих
            # двух состояний в одном поле привело бы к трудноотлаживаемым
            # багам в обеих системах одновременно.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS radar_seen (
                    address TEXT PRIMARY KEY,
                    last_seen_tx_hash TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # История сработавших радар-сигналов — отдельно от radar_seen (которая
            # хранит только ПОСЛЕДНИЙ обработанный хэш для дедупликации). Нужна
            # для кнопки "📊 История" в интерактивном /watchlist.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS radar_signal_history (
                    id SERIAL PRIMARY KEY,
                    address TEXT NOT NULL,
                    tx_hash TEXT,
                    amount_eth DOUBLE PRECISION,
                    direction TEXT,
                    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_radar_history_address ON radar_signal_history (address)")
            # Найденный баг: радар дедуплицирует ТОЛЬКО через "остановиться на
            # last_seen_tx_hash" внутри последних 5 запрошенных транзакций
            # (см. services/radar.py). Для кошелька с активностью выше 5 tx за
            # один цикл проверки (75с) — а это именно те постоянно активные
            # биржевые hot wallets, ради которых радар и существует — last_seen
            # может "выпасть" из окна, и уже отправленный сигнал будет
            # сгенерирован и разослан повторно. UNIQUE(address, tx_hash) здесь —
            # тот же защитный паттерн, что уже используется в alerts_history
            # (tx_hash UNIQUE) для дормант-детектора: последняя линия обороны,
            # даже если верхнеуровневая логика окна пропустит дубликат.
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'radar_signal_history_address_tx_hash_key'
                    ) THEN
                        ALTER TABLE radar_signal_history
                        ADD CONSTRAINT radar_signal_history_address_tx_hash_key UNIQUE (address, tx_hash);
                    END IF;
                END $$;
            """)

            # ==================================================================
            # AFFILIATE: денежные комиссии за оплативших VIP рефералов
            # ==================================================================
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS affiliate_earnings (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT NOT NULL,
                    referred_id BIGINT NOT NULL,
                    amount_usd DOUBLE PRECISION NOT NULL,
                    source TEXT NOT NULL,          -- 'stars' или 'cryptobot'
                    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'paid'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS affiliate_payouts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount_usd DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL DEFAULT 'requested',  -- 'requested' | 'paid' | 'rejected'
                    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TIMESTAMP
                )
            """)
        conn.commit()

    _seed_default_watchlist()


# Курируемый стартовый список спящих китов (>100 ETH баланс, предположительно
# неактивны 3+ года на момент составления списка). Реальный продакшн-список
# стоит обновлять периодически через отдельный скрипт/крон, а не хардкодить
# здесь бесконечно — это просто безопасный сид для первого запуска.
SEED_WATCHLIST = [
    {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "label": "Vitalik Buterin (Public)"},
    {"address": "0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "label": "Ethereum Foundation"},
    {"address": "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B", "label": "Vitalik Buterin (Alt)"},
    {"address": "0xE9D75f2447c9E9A65d19cC10C6C1cd2eD11ec0B0", "label": "Dormant Whale (Watch #4)"},
    {"address": "0xF977814e90dA44bFA03b6295A0616a897441aceC", "label": "Binance Cold Wallet (Watch)"},
]


def _seed_default_watchlist():
    """Заполняет watchlist куратором SEED_WATCHLIST при первом запуске (идемпотентно)."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for w in SEED_WATCHLIST:
                cursor.execute("""
                    INSERT INTO watchlist (address, label, source, added_by, is_active, monitor_type)
                    VALUES (%s, %s, 'seed', NULL, TRUE, 'dormant')
                    ON CONFLICT (address) DO NOTHING
                """, (w["address"].lower(), w["label"]))
            for w in RADAR_SEED_WATCHLIST:
                cursor.execute("""
                    INSERT INTO watchlist (address, label, source, added_by, is_active, monitor_type)
                    VALUES (%s, %s, 'seed', NULL, %s, 'radar')
                    ON CONFLICT (address) DO NOTHING
                """, (w["address"].lower(), w["label"], w["verified"]))
        conn.commit()


# Курируемый список известных активных китов для РАДАРА крупных переводов
# (отдельная система от SEED_WATCHLIST выше — эти кошельки НЕ спящие, они
# транслируют крупные суммы регулярно, и именно поэтому интересны для
# радара, а не для детектора пробуждения).
#
# ВАЖНО — точность адресов: "Vitalik Buterin (Public)" и "Ethereum Foundation"
# уже присутствуют выше и переиспользуются здесь через monitor_type='both'
# не требуется — они остаются 'dormant'. Адрес Justin Sun ниже подтвержден
# через публичный Etherscan label по состоянию на момент написания. Адреса
# для "Jump Trading" и бирж НЕ подтверждены с высокой уверенностью и
# ПОМЕЧЕНЫ как заглушки — заполните реальными checksummed-адресами из
# etherscan.io/accounts/label/* перед продакшн-использованием. Ончейн-адрес,
# указанный неверно, будет молча мониторить чужой (или несуществующий)
# кошелек без какой-либо ошибки — это не потребует падения кода, но исказит
# сигнал, поэтому вручную сверьте каждый TODO-адрес перед деплоем.
RADAR_SEED_WATCHLIST = [
    {"address": "0x3dDfA8eC3052539b6C9549F12cEA2C295cff5296", "label": "Justin Sun", "verified": True},
    # TODO: сверить и заменить на реальный адрес перед продакшеном (не подтвержден).
    # Намеренно вставлены как is_active=FALSE — placeholder-адрес НЕ должен молча
    # мониториться и генерировать сигналы по случайному/несуществующему кошельку.
    # (Найденный баг: прежние placeholder-адреса были 40 символов вместо 42 —
    # на 2 hex-цифры короче валидного Ethereum-адреса. Безвредно, пока
    # is_active=False, но исправлено на правильную длину, чтобы не стать
    # тихим источником багов, если кто-то активирует запись, не проверив формат.)
    {"address": "0x00000000000000000000000000000000DEAD0001", "label": "Jump Trading (TODO: verify address)", "verified": False},
    {"address": "0x00000000000000000000000000000000DEAD0002", "label": "Exchange Hot Wallet #1 (TODO: verify address)", "verified": False},
    {"address": "0x00000000000000000000000000000000DEAD0003", "label": "Exchange Hot Wallet #2 (TODO: verify address)", "verified": False},
]


def get_wallet(address: str) -> Optional[Tuple[str, str, str, int]]:
    """Возвращает информацию о кошельке из БД."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT address, label, last_tx_hash, last_active_timestamp FROM wallets WHERE address = %s",
                (address.lower(),)
            )
            return cursor.fetchone()


def upsert_wallet(address: str, label: str, last_tx_hash: str, last_active_timestamp: int):
    """Добавляет или обновляет информацию о кошельке."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO wallets (address, label, last_tx_hash, last_active_timestamp)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (address) DO UPDATE SET
                    label = EXCLUDED.label,
                    last_tx_hash = EXCLUDED.last_tx_hash,
                    last_active_timestamp = EXCLUDED.last_active_timestamp
            """, (address.lower(), label, last_tx_hash, last_active_timestamp))
        conn.commit()


def save_alert(address: str, tx_hash: str, dormant_days: int, amount_eth: float) -> bool:
    """Записывает алерт в историю. Возвращает False, если такой tx_hash уже был записан."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO alerts_history (address, tx_hash, dormant_days, amount_eth)
                    VALUES (%s, %s, %s, %s)
                """, (address.lower(), tx_hash, dormant_days, amount_eth))
            conn.commit()
            return True
    except psycopg2.errors.UniqueViolation:
        return False
    except Exception:
        return False


def add_vip_user(user_id: int, username: str, days: int):
    """Добавляет или продлевает VIP-доступ пользователю."""
    import time
    current_time = int(time.time())
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT expire_timestamp FROM vip_users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            
            base_time = current_time
            if row and row[0] and row[0] > current_time:
                base_time = row[0]
                
            expire_timestamp = base_time + (days * 86400)
            
            cursor.execute("""
                INSERT INTO vip_users (user_id, username, expire_timestamp)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    expire_timestamp = EXCLUDED.expire_timestamp
            """, (user_id, username, expire_timestamp))
        conn.commit()


def is_vip(user_id: int) -> bool:
    """Проверяет, активен ли VIP-доступ у пользователя."""
    import time
    current_time = int(time.time())
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT expire_timestamp FROM vip_users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if row and row[0] and row[0] > current_time:
                return True
            return False


def get_active_vips() -> list:
    """Возвращает список всех пользователей с активным VIP-доступом [(user_id, username, expire_timestamp), ...]."""
    import time
    current_time = int(time.time())
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, username, expire_timestamp FROM vip_users WHERE expire_timestamp > %s", (current_time,))
            return cursor.fetchall()


def is_invoice_processed(invoice_id: int) -> bool:
    """Проверяет, был ли инвойс CryptoBot уже обработан."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT invoice_id FROM processed_invoices WHERE invoice_id = %s", (invoice_id,))
            return cursor.fetchone() is not None


def mark_invoice_processed(invoice_id: int):
    """Отмечает инвойс CryptoBot как обработанный."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO processed_invoices (invoice_id)
                VALUES (%s)
                ON CONFLICT (invoice_id) DO NOTHING
            """, (invoice_id,))
        conn.commit()


def get_user_settings(user_id: int) -> dict:
    """Возвращает настройки пользователя или дефолтные значения."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT min_dormant_years, min_amount_eth, notify_enabled, language_code "
                "FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d["language_code"] = d.get("language_code") or "en"
                return d
            return {
                "min_dormant_years": 3,
                "min_amount_eth": 10.0,
                "notify_enabled": True,
                "language_code": "en"
            }


def get_user_language(user_id: int) -> str:
    """Возвращает код языка пользователя ('en' или 'ru'), 'en' по умолчанию."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT language_code FROM user_settings WHERE user_id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
            return "en"


def set_user_language(user_id: int, lang_code: str):
    """Устанавливает язык интерфейса пользователя. Допустимые значения: 'en', 'ru'."""
    if lang_code not in ("en", "ru"):
        lang_code = "en"
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_settings (user_id, language_code)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    language_code = EXCLUDED.language_code
            """, (user_id, lang_code))
        conn.commit()


def get_terms_accepted(user_id: int) -> bool:
    """Проверяет, прошел ли пользователь онбординг (принял дисклеймер/условия)."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT terms_accepted FROM user_settings WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return bool(row and row[0])


def set_terms_accepted(user_id: int, accepted: bool = True):
    """Отмечает, что пользователь принял условия использования / дисклеймер."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_settings (user_id, terms_accepted)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    terms_accepted = EXCLUDED.terms_accepted
            """, (user_id, accepted))
        conn.commit()


def update_user_setting(user_id: int, key: str, value):
    """Обновляет конкретную настройку пользователя."""
    allowed_keys = ["min_dormant_years", "min_amount_eth", "notify_enabled"]
    if key not in allowed_keys:
        raise ValueError(f"Недопустимый ключ настройки: {key}")
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                INSERT INTO user_settings (user_id, {key})
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    {key} = EXCLUDED.{key}
            """, (user_id, value))
        conn.commit()


def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Добавляет реферала. Возвращает True, если успешно, False если уже существует или саморефералы."""
    # Строгая проверка на саморефералы: приводим оба ID к int, чтобы избежать
    # ложноотрицательных сравнений из-за разных типов (str vs int из callback_data / Message).
    if int(referrer_id) == int(referred_id):
        return False
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES (%s, %s)
                    ON CONFLICT (referred_id) DO NOTHING
                """, (referrer_id, referred_id))
                if cursor.rowcount == 0:
                    return False
            conn.commit()
            return True
    except Exception:
        return False


def count_referrals(user_id: int) -> int:
    """Возвращает количество рефералов пользователя."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else 0


def get_stats_summary() -> dict:
    """Возвращает общую статистику системы."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM wallets")
            total_wallets = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM alerts_history")
            total_alerts = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM vip_users WHERE expire_timestamp > extract(epoch from now())")
            active_vips = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM referrals")
            total_referrals = cursor.fetchone()[0]

            return {
                "total_wallets": total_wallets,
                "total_alerts": total_alerts,
                "active_vips": active_vips,
                "total_referrals": total_referrals
            }




# ==============================================================================
# WATCHLIST — гибридная система мониторинга (seed + пользовательские /track)
# ==============================================================================

FREE_TRACK_LIMIT = 1
VIP_TRACK_LIMIT = 10


def get_active_watchlist() -> list:
    """Возвращает все активные адреса для мониторинга:
    [(address, label, source, added_by, monitor_type, alert_threshold_eth), ...]."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT address, label, source, added_by, monitor_type, alert_threshold_eth
                FROM watchlist
                WHERE is_active = TRUE
            """)
            return cursor.fetchall()


def get_radar_last_seen(address: str):
    """Возвращает last_seen_tx_hash для радара крупных переводов, или None если еще не было."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT last_seen_tx_hash FROM radar_seen WHERE address = %s", (address.lower(),))
            row = cursor.fetchone()
            return row[0] if row else None


def upsert_radar_last_seen(address: str, tx_hash: str):
    """Обновляет last_seen_tx_hash для радара — независимое состояние от таблицы wallets."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO radar_seen (address, last_seen_tx_hash, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (address) DO UPDATE SET
                    last_seen_tx_hash = EXCLUDED.last_seen_tx_hash,
                    updated_at = CURRENT_TIMESTAMP
            """, (address.lower(), tx_hash))
        conn.commit()


def count_user_tracked_wallets(user_id: int) -> int:
    """Считает, сколько личных кошельков пользователь уже отслеживает через /track."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM watchlist
                WHERE source = 'user' AND added_by = %s AND is_active = TRUE
            """, (user_id,))
            return cursor.fetchone()[0]


def add_tracked_wallet(user_id: int, address: str, is_vip: bool, label: str = None) -> tuple:
    """
    Добавляет личный кошелек в watchlist пользователя.
    Возвращает (success: bool, reason: str), где reason — код причины отказа:
    'limit_reached' | 'already_tracked' | 'ok'.
    """
    address = address.lower()
    limit = VIP_TRACK_LIMIT if is_vip else FREE_TRACK_LIMIT

    current_count = count_user_tracked_wallets(user_id)
    if current_count >= limit:
        return False, "limit_reached"

    display_label = label.strip() if label and label.strip() else f"Tracked by {user_id}"

    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                # Один и тот же адрес может уже быть в seed-листе — тогда просто разрешаем
                # пользователю "подписаться" на него отдельной строкой с source='user',
                # т.к. ON CONFLICT (address) в таблице сработает лишь при точном совпадении адреса.
                cursor.execute("SELECT id FROM watchlist WHERE address = %s AND added_by = %s", (address, user_id))
                if cursor.fetchone():
                    return False, "already_tracked"

                cursor.execute("""
                    INSERT INTO watchlist (address, label, source, added_by, is_active, monitor_type, alert_threshold_eth)
                    VALUES (%s, %s, 'user', %s, TRUE, 'both', 10.0)
                """, (address, display_label, user_id))
            conn.commit()
        return True, "ok"
    except psycopg2.errors.UniqueViolation:
        return False, "already_tracked"
    except Exception:
        return False, "error"


def get_trackers_for_address(address: str) -> list:
    """Возвращает user_id всех, кто лично отслеживает данный адрес через /track."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT added_by FROM watchlist
                WHERE source = 'user' AND address = %s AND is_active = TRUE AND added_by IS NOT NULL
            """, (address.lower(),))
            return [row[0] for row in cursor.fetchall()]


def list_tracked_wallets(user_id: int) -> list:
    """Возвращает список [(address, label, alert_threshold_eth), ...] личных кошельков пользователя."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT address, label, alert_threshold_eth FROM watchlist
                WHERE source = 'user' AND added_by = %s AND is_active = TRUE
                ORDER BY created_at ASC
            """, (user_id,))
            return cursor.fetchall()


def get_tracked_wallet_for_owner(user_id: int, address: str):
    """Возвращает (address, label, alert_threshold_eth, monitor_type) для управления
    конкретным кошельком — только если он принадлежит user_id (проверка владения)."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT address, label, alert_threshold_eth, monitor_type FROM watchlist
                WHERE address = %s AND added_by = %s AND is_active = TRUE
            """, (address.lower(), user_id))
            return cursor.fetchone()


def update_wallet_label(user_id: int, address: str, label: str) -> bool:
    """Обновляет метку кошелька — только если он принадлежит user_id."""
    label = (label or "").strip()
    if not label:
        return False
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE watchlist SET label = %s
                WHERE address = %s AND added_by = %s
            """, (label, address.lower(), user_id))
            updated = cursor.rowcount > 0
        conn.commit()
    return updated


def update_wallet_threshold(user_id: int, address: str, threshold_eth: float) -> bool:
    """Обновляет персональный порог алертов для кошелька — только если он принадлежит user_id."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE watchlist SET alert_threshold_eth = %s
                WHERE address = %s AND added_by = %s
            """, (threshold_eth, address.lower(), user_id))
            updated = cursor.rowcount > 0
        conn.commit()
    return updated


def deactivate_tracked_wallet(user_id: int, address: str) -> bool:
    """Мягко удаляет кошелек из watchlist пользователя (is_active=FALSE) — только если он принадлежит user_id."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE watchlist SET is_active = FALSE
                WHERE address = %s AND added_by = %s
            """, (address.lower(), user_id))
            updated = cursor.rowcount > 0
        conn.commit()
    return updated


def record_radar_signal(address: str, tx_hash: str, amount_eth: float, direction: str) -> bool:
    """
    Записывает сработавший радар-сигнал в историю (для кнопки '📊 История').

    Возвращает True, если это НОВАЯ запись, False — если (address, tx_hash)
    уже был записан ранее (см. UNIQUE constraint в init_db) — вызывающий код
    в services/radar.py использует это как последний рубеж защиты от повторной
    отправки алерта по одной и той же транзакции, если она "выпала" из окна
    last_seen_tx_hash (см. комментарий у ограничения в init_db).
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO radar_signal_history (address, tx_hash, amount_eth, direction)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (address, tx_hash) DO NOTHING
                """, (address.lower(), tx_hash, amount_eth, direction))
                inserted = cursor.rowcount > 0
            conn.commit()
            return inserted
    except Exception:
        # История — не критичный путь сам по себе, но раз мы не знаем,
        # было ли это дубликатом, безопаснее по умолчанию считать "новым",
        # чтобы сбой БД не тихо проглатывал реальные сигналы.
        return True


def get_wallet_signal_history(address: str, limit: int = 5) -> list:
    """
    Объединяет дормант-алерты (alerts_history) и радар-сигналы
    (radar_signal_history) для одного адреса в единый список, отсортированный
    по времени (новые первыми): [(kind, triggered_at, amount_eth, extra), ...]
    где kind = 'dormant' | 'radar', extra = dormant_days для 'dormant' или
    direction для 'radar'.
    """
    address = address.lower()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 'dormant' AS kind, triggered_at, amount_eth, dormant_days::text AS extra
                FROM alerts_history WHERE address = %s
                UNION ALL
                SELECT 'radar' AS kind, triggered_at, amount_eth, direction AS extra
                FROM radar_signal_history WHERE address = %s
                ORDER BY triggered_at DESC
                LIMIT %s
            """, (address, address, limit))
            return cursor.fetchall()


# ==============================================================================
# AFFILIATE — денежные комиссии за оплативших VIP рефералов
# ==============================================================================

COMMISSION_RATE = 0.20  # 20% с каждой оплаты VIP оплатившим рефералом


def record_affiliate_commission(referrer_id: int, referred_id: int, amount_usd: float, source: str):
    """Начисляет комиссию рефереру за платеж его реферала. Не бросает исключение наружу."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO affiliate_earnings (referrer_id, referred_id, amount_usd, source, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                """, (referrer_id, referred_id, round(amount_usd * COMMISSION_RATE, 2), source))
            conn.commit()
    except Exception:
        pass


def get_referrer_for_user(user_id: int) -> Optional[int]:
    """Возвращает referrer_id для пользователя, если он был кем-то приглашен."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None


def get_affiliate_balance(user_id: int) -> dict:
    """Возвращает баланс аффилиата: {pending, paid, total}."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    COALESCE(SUM(amount_usd) FILTER (WHERE status = 'pending'), 0),
                    COALESCE(SUM(amount_usd) FILTER (WHERE status = 'paid'), 0)
                FROM affiliate_earnings WHERE referrer_id = %s
            """, (user_id,))
            pending, paid = cursor.fetchone()
            return {"pending": float(pending), "paid": float(paid), "total": float(pending) + float(paid)}


def request_payout(user_id: int, amount_usd: float) -> bool:
    """
    Создает заявку на вывод средств (обрабатывается вручную админом — см. /payouts).

    ВАЖНО (найденный баг — двойная выплата): раньше эта функция только
    вставляла строку в affiliate_payouts, не трогая affiliate_earnings —
    значит get_affiliate_balance() по-прежнему показывал ту же самую сумму
    "pending" сразу после запроса, и повторный тап по кнопке "Запросить
    выплату" (до того как админ обработает первую заявку через /pay)
    создавал ВТОРУЮ заявку на ту же самую еще не выплаченную сумму —
    админ мог случайно заплатить дважды за одни и те же начисления.

    Теперь запрос атомарно "резервирует" earnings-строки на сумму заявки,
    переводя их из 'pending' в 'requested' — тем самым сразу уменьшая
    видимый pending-баланс, так что повторный тап увидит pending=0 и будет
    заблокирован (см. process_withdraw_request), а не создаст дубликат.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, amount_usd FROM affiliate_earnings
                    WHERE referrer_id = %s AND status = 'pending'
                    ORDER BY created_at ASC
                """, (user_id,))
                rows = cursor.fetchall()

                remaining = amount_usd
                reserved_ids = []
                for row_id, row_amount in rows:
                    if remaining <= 0:
                        break
                    reserved_ids.append(row_id)
                    remaining -= float(row_amount)

                # Ничего не удалось зарезервировать (баланс уже был выведен/запрошен
                # в параллельном запросе) — не создаем заявку "из воздуха".
                if not reserved_ids:
                    return False

                cursor.execute(
                    "UPDATE affiliate_earnings SET status = 'requested' WHERE id = ANY(%s)",
                    (reserved_ids,)
                )
                cursor.execute("""
                    INSERT INTO affiliate_payouts (user_id, amount_usd, status)
                    VALUES (%s, %s, 'requested')
                """, (user_id, amount_usd))
            conn.commit()
        return True
    except Exception:
        return False


def get_pending_payouts() -> list:
    """Для админа: список всех невыплаченных заявок на вывод."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, user_id, amount_usd, requested_at FROM affiliate_payouts
                WHERE status = 'requested' ORDER BY requested_at ASC
            """)
            return cursor.fetchall()


def mark_payout_paid(payout_id: int, user_id: int, amount_usd: float):
    """
    Помечает заявку выплаченной и переводит соответствующие начисления в 'paid'.

    Раньше закрывались 'pending' начисления — но теперь request_payout() уже
    резервирует нужные строки в 'requested' в момент запроса (см. фикс двойной
    выплаты выше), поэтому здесь нужно закрывать 'requested', а не 'pending' —
    иначе эта функция могла бы найти и списать чужие, никак не связанные с этой
    заявкой pending-начисления, появившиеся уже ПОСЛЕ запроса на выплату.
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE affiliate_payouts SET status = 'paid', resolved_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (payout_id,))
            cursor.execute("""
                SELECT id, amount_usd FROM affiliate_earnings
                WHERE referrer_id = %s AND status = 'requested' ORDER BY created_at ASC
            """, (user_id,))
            remaining = amount_usd
            for row_id, row_amount in cursor.fetchall():
                if remaining <= 0:
                    break
                cursor.execute("UPDATE affiliate_earnings SET status = 'paid' WHERE id = %s", (row_id,))
                remaining -= float(row_amount)
        conn.commit()