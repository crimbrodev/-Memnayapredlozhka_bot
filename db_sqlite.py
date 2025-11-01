import sqlite3
import os
from contextlib import contextmanager

DB_FILE = 'bot_database.db'

@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Таблица pending_posts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                user_id INTEGER,
                username TEXT,
                photo_file_id TEXT,
                caption TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица banned_users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER,
                channel_id TEXT,
                username TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                banned_by INTEGER,
                PRIMARY KEY (user_id, channel_id)
            )
        """)
        
        # Таблица channels
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица channel_admins
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_admins (
                channel_id TEXT,
                user_id INTEGER,
                username TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        
        # Таблица channel_settings
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                channel_id TEXT PRIMARY KEY,
                post_interval_minutes INTEGER DEFAULT 0,
                max_posts_per_day INTEGER DEFAULT 0,
                require_caption INTEGER DEFAULT 0,
                allowed_media_types TEXT DEFAULT 'photo,video',
                spam_filter_enabled INTEGER DEFAULT 1,
                allow_global_posts INTEGER DEFAULT 1,
                last_post_time TIMESTAMP,
                smart_mode INTEGER DEFAULT 0,
                aggressiveness TEXT DEFAULT 'medium',
                auto_moderation INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица scheduled_posts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                user_id INTEGER,
                username TEXT,
                photo_file_id TEXT,
                caption TEXT,
                scheduled_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица audit_log
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                action TEXT,
                user_id INTEGER,
                admin_id INTEGER,
                post_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица published_posts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS published_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                user_id INTEGER,
                username TEXT,
                message_id INTEGER,
                reactions INTEGER DEFAULT 0,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица user_coins
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_coins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица coin_transactions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица user_streaks
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_streaks (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                current_streak INTEGER DEFAULT 0,
                longest_streak INTEGER DEFAULT 0,
                last_post_date DATE
            )
        """)
        
        # Таблица daily_quests
        cur.execute("""
            CREATE TABLE IF NOT EXISTS daily_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                quest_date DATE,
                quest_type TEXT,
                reward INTEGER,
                completed INTEGER DEFAULT 0,
                completed_at TIMESTAMP
            )
        """)
        
        # Таблица shop_purchases
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shop_purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                item_type TEXT,
                cost INTEGER,
                expires_at TIMESTAMP,
                used INTEGER DEFAULT 0,
                channel_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица user_subscriptions
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_subscriptions (
                user_id INTEGER PRIMARY KEY,
                subscription_type TEXT,
                expires_at TIMESTAMP,
                last_bonus_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица channel_protections
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_protections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id TEXT,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица lootboxes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lootboxes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                box_type TEXT,
                opened INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица lootbox_rewards
        cur.execute("""
            CREATE TABLE IF NOT EXISTS lootbox_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lootbox_id INTEGER,
                reward_type TEXT,
                reward_value INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица referral_codes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referral_codes (
                user_id INTEGER PRIMARY KEY,
                code TEXT UNIQUE,
                total_referrals INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица referrals
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                referred_username TEXT,
                reward_claimed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Индексы
        cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON coin_transactions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_published_posts_user ON published_posts(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_published_posts_channel ON published_posts(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pending_posts_channel ON pending_posts(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_channel ON audit_log(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_banned_users_user ON banned_users(user_id)")
        
        conn.commit()
        print("[OK] База данных SQLite инициализирована!")

if __name__ == '__main__':
    init_database()
