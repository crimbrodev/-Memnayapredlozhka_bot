import os
import logging
import psycopg2
import hashlib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError
from aiohttp import web
import asyncio

# Загружаем переменные из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')
SUPPORT_ADMIN_ID = int(os.getenv('SUPPORT_ADMIN_ID', '0'))

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def is_user_banned(user_id: int, channel_id: str = None) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("SELECT user_id FROM banned_users WHERE user_id = %s AND channel_id = %s", (user_id, channel_id))
    else:
        cur.execute("SELECT user_id FROM banned_users WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

def ban_user(user_id: int, username: str, banned_by: int, channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO banned_users (user_id, channel_id, username, banned_by) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, channel_id) DO NOTHING",
        (user_id, channel_id, username, banned_by)
    )
    conn.commit()
    cur.close()
    conn.close()

def unban_user(user_id: int, channel_id: str = None):
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("DELETE FROM banned_users WHERE user_id = %s AND channel_id = %s", (user_id, channel_id))
    else:
        cur.execute("DELETE FROM banned_users WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_banned_users(channel_id: str = None):
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("SELECT user_id, username, banned_at, banned_by FROM banned_users WHERE channel_id = %s ORDER BY banned_at DESC", (channel_id,))
    else:
        cur.execute("SELECT user_id, channel_id, username, banned_at, banned_by FROM banned_users ORDER BY banned_at DESC")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return users

def add_channel(channel_id: str, added_by: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO channels (channel_id, added_by) VALUES (%s, %s) ON CONFLICT (channel_id) DO NOTHING",
        (channel_id, added_by)
    )
    conn.commit()
    cur.close()
    conn.close()

def update_channel_admins(channel_id: str, admins: list):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM channel_admins WHERE channel_id = %s", (channel_id,))
    for admin in admins:
        cur.execute(
            "INSERT INTO channel_admins (channel_id, user_id, username) VALUES (%s, %s, %s)",
            (channel_id, admin['user_id'], admin['username'])
        )
    conn.commit()
    cur.close()
    conn.close()

def add_pending_post(channel_id: str, user_id: int, username: str, photo_file_id: str, caption: str = "", priority: bool = False):
    conn = get_db_connection()
    cur = conn.cursor()
    if priority:
        cur.execute(
            "INSERT INTO pending_posts (channel_id, user_id, username, photo_file_id, caption, created_at) VALUES (%s, %s, %s, %s, %s, '1970-01-01')",
            (channel_id, user_id, username, photo_file_id, caption)
        )
    else:
        cur.execute(
            "INSERT INTO pending_posts (channel_id, user_id, username, photo_file_id, caption) VALUES (%s, %s, %s, %s, %s)",
            (channel_id, user_id, username, photo_file_id, caption)
        )
    conn.commit()
    cur.close()
    conn.close()

def get_pending_posts(channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, username, photo_file_id, caption, created_at FROM pending_posts WHERE channel_id = %s ORDER BY created_at ASC", (channel_id,))
    posts = cur.fetchall()
    cur.close()
    conn.close()
    return posts

def remove_pending_post(post_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM pending_posts WHERE id = %s", (post_id,))
    conn.commit()
    cur.close()
    conn.close()

def get_channel_admins(channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM channel_admins WHERE channel_id = %s", (channel_id,))
    admins = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return admins

def get_channels():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM channels")
    channels = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return channels

def get_channels_with_names():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM channels")
    channels = cur.fetchall()
    cur.close()
    conn.close()
    return channels

def is_channel_admin(user_id: int, channel_id: str = None) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("SELECT user_id FROM channel_admins WHERE user_id = %s AND channel_id = %s", (user_id, channel_id))
    else:
        cur.execute("SELECT user_id FROM channel_admins WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

def get_user_channels(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT channel_id FROM channel_admins WHERE user_id = %s", (user_id,))
    channels = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return channels

def get_channel_settings(channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT post_interval_minutes, max_posts_per_day, require_caption, allowed_media_types, spam_filter_enabled, last_post_time, allow_global_posts FROM channel_settings WHERE channel_id = %s", (channel_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    if result:
        return {'interval': result[0], 'max_posts': result[1], 'require_caption': result[2], 'media_types': result[3], 'spam_filter': result[4], 'last_post': result[5], 'allow_global': result[6] if len(result) > 6 else True}
    return {'interval': 0, 'max_posts': 0, 'require_caption': False, 'media_types': 'photo,video', 'spam_filter': True, 'last_post': None, 'allow_global': True}

def update_channel_setting(channel_id: str, setting: str, value):
    ALLOWED_SETTINGS = {
        'post_interval_minutes', 'max_posts_per_day', 'require_caption',
        'spam_filter_enabled', 'allow_global_posts', 'smart_mode',
        'aggressiveness', 'auto_moderation', 'last_post_time'
    }
    if setting not in ALLOWED_SETTINGS:
        raise ValueError(f"Invalid setting: {setting}")
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = f"INSERT INTO channel_settings (channel_id, {setting}) VALUES (%s, %s) ON CONFLICT (channel_id) DO UPDATE SET {setting} = %s"
        cur.execute(query, (channel_id, value, value))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

def add_scheduled_post(channel_id: str, user_id: int, username: str, photo_file_id: str, caption: str, scheduled_time):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO scheduled_posts (channel_id, user_id, username, photo_file_id, caption, scheduled_time) VALUES (%s, %s, %s, %s, %s, %s)", (channel_id, user_id, username, photo_file_id, caption, scheduled_time))
    conn.commit()
    cur.close()
    conn.close()

def get_scheduled_posts(channel_id: str = None):
    from datetime import datetime
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("SELECT id, channel_id, user_id, username, photo_file_id, caption, scheduled_time FROM scheduled_posts WHERE channel_id = %s ORDER BY scheduled_time ASC", (channel_id,))
    else:
        now = datetime.now()
        cur.execute("SELECT id, channel_id, user_id, username, photo_file_id, caption, scheduled_time FROM scheduled_posts WHERE scheduled_time <= %s ORDER BY scheduled_time ASC", (now,))
    posts = cur.fetchall()
    cur.close()
    conn.close()
    return posts

def remove_scheduled_post(post_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM scheduled_posts WHERE id = %s", (post_id,))
    conn.commit()
    cur.close()
    conn.close()

def log_action(channel_id: str, action: str, user_id: int, admin_id: int, post_id: int = None, details: str = ""):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO audit_log (channel_id, action, user_id, admin_id, post_id, details) VALUES (%s, %s, %s, %s, %s, %s)", (channel_id, action, user_id, admin_id, post_id, details))
    conn.commit()
    cur.close()
    conn.close()

def add_published_post(channel_id: str, user_id: int, username: str, message_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO published_posts (channel_id, user_id, username, message_id) VALUES (%s, %s, %s, %s)",
        (channel_id, user_id, username, message_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def update_post_reactions(channel_id: str, message_id: int, reactions: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE published_posts SET reactions = %s WHERE channel_id = %s AND message_id = %s",
        (reactions, channel_id, message_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_global_leaderboard(limit: int = 10):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, COUNT(*) as posts, COALESCE(SUM(reactions), 0) as total_reactions "
        "FROM published_posts GROUP BY user_id, username ORDER BY total_reactions DESC, posts DESC LIMIT %s",
        (limit,)
    )
    result = cur.fetchall()
    cur.close()
    conn.close()
    return result

def get_channel_leaderboard(channel_id: str, limit: int = 10):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, username, COUNT(*) as posts, COALESCE(SUM(reactions), 0) as total_reactions "
        "FROM published_posts WHERE channel_id = %s GROUP BY user_id, username ORDER BY total_reactions DESC, posts DESC LIMIT %s",
        (channel_id, limit)
    )
    result = cur.fetchall()
    cur.close()
    conn.close()
    return result

def add_coins(user_id: int, username: str, amount: int, reason: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_coins (user_id, username, balance, total_earned) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET balance = user_coins.balance + %s, total_earned = user_coins.total_earned + %s, username = %s, updated_at = CURRENT_TIMESTAMP",
        (user_id, username, amount, amount, amount, amount, username)
    )
    cur.execute(
        "INSERT INTO coin_transactions (user_id, amount, reason) VALUES (%s, %s, %s)",
        (user_id, amount, reason)
    )
    conn.commit()
    cur.close()
    conn.close()

def get_user_balance(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance, total_earned FROM user_coins WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result if result else (0, 0)

def get_user_rank(posts_count: int):
    if posts_count >= 100:
        return "👑 Легенда"
    elif posts_count >= 50:
        return "🦅 Про-мемер"
    elif posts_count >= 20:
        return "🐥 Мемер"
    elif posts_count >= 5:
        return "🐣 Любитель"
    else:
        return "🥚 Новичок"

def check_and_award_achievements(user_id: int, username: str, posts_count: int):
    achievements = []
    if posts_count == 1:
        add_coins(user_id, username, 20, "🔥 Достижение: Первая кровь")
        achievements.append("🔥 Первая кровь (+20 монет)")
    elif posts_count == 10:
        add_coins(user_id, username, 50, "💯 Достижение: Десятка")
        achievements.append("💯 Десятка (+50 монет)")
    elif posts_count == 50:
        add_coins(user_id, username, 200, "🎊 Достижение: Полтинник")
        achievements.append("🎊 Полтинник (+200 монет)")
    elif posts_count == 100:
        add_coins(user_id, username, 500, "👑 Достижение: Легенда")
        achievements.append("👑 Легенда (+500 монет)")
    return achievements

def spend_coins(user_id: int, amount: int, reason: str) -> bool:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_coins SET balance = balance - %s "
            "WHERE user_id = %s AND balance >= %s RETURNING balance",
            (amount, user_id, amount)
        )
        result = cur.fetchone()
        if not result:
            conn.rollback()
            return False
        cur.execute(
            "INSERT INTO coin_transactions (user_id, amount, reason) VALUES (%s, %s, %s)",
            (user_id, -amount, reason)
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Error spending coins: {e}")
        return False
    finally:
        cur.close()
        conn.close()

def transfer_coins(from_user_id: int, to_user_id: int, amount: int, from_username: str, to_username: str) -> bool:
    if from_user_id == SUPPORT_ADMIN_ID:
        add_coins(to_user_id, to_username, amount, f"💸 Перевод от @{from_username}")
        return True
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_coins SET balance = balance - %s "
            "WHERE user_id = %s AND balance >= %s RETURNING balance",
            (amount, from_user_id, amount)
        )
        result = cur.fetchone()
        if not result:
            conn.rollback()
            return False
        cur.execute(
            "INSERT INTO coin_transactions (user_id, amount, reason) VALUES (%s, %s, %s)",
            (from_user_id, -amount, f"💸 Перевод @{to_username}")
        )
        conn.commit()
        cur.close()
        conn.close()
        add_coins(to_user_id, to_username, amount, f"💸 Перевод от @{from_username}")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"Error transferring coins: {e}")
        return False
    finally:
        if conn:
            cur.close()
            conn.close()

def update_streak(user_id: int, username: str):
    from datetime import date, timedelta
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_streak, longest_streak, last_post_date FROM user_streaks WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    today = date.today()
    
    if not result:
        cur.execute("INSERT INTO user_streaks (user_id, username, current_streak, longest_streak, last_post_date) VALUES (%s, %s, 1, 1, %s)", (user_id, username, today))
    else:
        current, longest, last_date = result
        if last_date == today:
            pass
        elif last_date == today - timedelta(days=1):
            current += 1
            longest = max(longest, current)
            cur.execute("UPDATE user_streaks SET current_streak = %s, longest_streak = %s, last_post_date = %s WHERE user_id = %s", (current, longest, today, user_id))
            if current == 7:
                add_coins(user_id, username, 50, "🔥 Стрик 7 дней")
            elif current == 30:
                add_coins(user_id, username, 300, "🔥 Стрик 30 дней")
        else:
            cur.execute("UPDATE user_streaks SET current_streak = 1, last_post_date = %s WHERE user_id = %s", (today, user_id))
    conn.commit()
    cur.close()
    conn.close()

def get_streak(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT current_streak, longest_streak FROM user_streaks WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result if result else (0, 0)

def check_daily_quests(user_id: int, username: str):
    from datetime import date
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    
    cur.execute("SELECT quest_type, completed FROM daily_quests WHERE user_id = %s AND quest_date = %s", (user_id, today))
    quests = {row[0]: row[1] for row in cur.fetchall()}
    
    if not quests:
        cur.execute("INSERT INTO daily_quests (user_id, quest_date, quest_type, reward) VALUES (%s, %s, 'post_1', 10)", (user_id, today))
        cur.execute("INSERT INTO daily_quests (user_id, quest_date, quest_type, reward) VALUES (%s, %s, 'post_3', 30)", (user_id, today))
        cur.execute("INSERT INTO daily_quests (user_id, quest_date, quest_type, reward) VALUES (%s, %s, 'post_5', 50)", (user_id, today))
        cur.execute("INSERT INTO daily_quests (user_id, quest_date, quest_type, reward) VALUES (%s, %s, 'streak_3', 100)", (user_id, today))
        cur.execute("INSERT INTO daily_quests (user_id, quest_date, quest_type, reward) VALUES (%s, %s, 'open_lootbox', 20)", (user_id, today))
        quests = {'post_1': False, 'post_3': False, 'post_5': False, 'streak_3': False, 'open_lootbox': False}
    
    cur.execute("SELECT COUNT(*) FROM published_posts WHERE user_id = %s AND DATE(published_at) = %s", (user_id, today))
    posts_today = cur.fetchone()[0]
    
    if posts_today >= 1 and not quests.get('post_1'):
        cur.execute("UPDATE daily_quests SET completed = TRUE, completed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND quest_date = %s AND quest_type = 'post_1'", (user_id, today))
        add_coins(user_id, username, 10, "✅ Задание: 1 мем")
    
    if posts_today >= 3 and not quests.get('post_3'):
        cur.execute("UPDATE daily_quests SET completed = TRUE, completed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND quest_date = %s AND quest_type = 'post_3'", (user_id, today))
        add_coins(user_id, username, 30, "✅ Задание: 3 мема")
    
    if posts_today >= 5 and not quests.get('post_5'):
        cur.execute("UPDATE daily_quests SET completed = TRUE, completed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND quest_date = %s AND quest_type = 'post_5'", (user_id, today))
        add_coins(user_id, username, 50, "✅ Задание: 5 мемов")
    
    cur.execute("SELECT current_streak FROM user_streaks WHERE user_id = %s", (user_id,))
    streak_result = cur.fetchone()
    if streak_result and streak_result[0] >= 3 and not quests.get('streak_3'):
        cur.execute("UPDATE daily_quests SET completed = TRUE, completed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND quest_date = %s AND quest_type = 'streak_3'", (user_id, today))
        add_coins(user_id, username, 100, "✅ Задание: Стрик 3 дня")
    
    conn.commit()
    cur.close()
    conn.close()

def get_daily_quests(user_id: int):
    from datetime import date
    conn = get_db_connection()
    cur = conn.cursor()
    today = date.today()
    cur.execute("SELECT quest_type, completed, reward FROM daily_quests WHERE user_id = %s AND quest_date = %s", (user_id, today))
    quests = cur.fetchall()
    cur.close()
    conn.close()
    return quests

def buy_shop_item(user_id: int, username: str, item_type: str, cost: int, duration_hours: int = 0):
    from datetime import datetime, timedelta
    if not spend_coins(user_id, cost, f"🛒 Покупка: {item_type}"):
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    expires = datetime.now() + timedelta(hours=duration_hours) if duration_hours > 0 else None
    cur.execute("INSERT INTO shop_purchases (user_id, username, item_type, cost, expires_at) VALUES (%s, %s, %s, %s, %s)", (user_id, username, item_type, cost, expires))
    conn.commit()
    cur.close()
    conn.close()
    return True

def has_active_item(user_id: int, item_type: str):
    from datetime import datetime
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM shop_purchases WHERE user_id = %s AND item_type = %s AND used = FALSE AND (expires_at IS NULL OR expires_at > %s)", (user_id, item_type, datetime.now()))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

def use_shop_item(user_id: int, item_type: str, channel_id: str = None):
    conn = get_db_connection()
    cur = conn.cursor()
    if channel_id:
        cur.execute("UPDATE shop_purchases SET used = TRUE WHERE ctid = (SELECT ctid FROM shop_purchases WHERE user_id = %s AND item_type = %s AND channel_id = %s AND used = FALSE LIMIT 1)", (user_id, item_type, channel_id))
    else:
        cur.execute("UPDATE shop_purchases SET used = TRUE WHERE ctid = (SELECT ctid FROM shop_purchases WHERE user_id = %s AND item_type = %s AND used = FALSE LIMIT 1)", (user_id, item_type))
    conn.commit()
    cur.close()
    conn.close()

def has_active_subscription(user_id: int):
    from datetime import datetime
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT subscription_type FROM user_subscriptions WHERE user_id = %s AND expires_at > %s", (user_id, datetime.now()))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result[0] if result else None

def buy_subscription(user_id: int, username: str, sub_type: str, cost: int, days: int):
    from datetime import datetime, timedelta
    if not spend_coins(user_id, cost, f"💎 Подписка {sub_type}"):
        return False
    conn = get_db_connection()
    cur = conn.cursor()
    expires = datetime.now() + timedelta(days=days)
    cur.execute("INSERT INTO user_subscriptions (user_id, subscription_type, expires_at) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET subscription_type = %s, expires_at = %s", (user_id, sub_type, expires, sub_type, expires))
    conn.commit()
    cur.close()
    conn.close()
    return True

def has_channel_protection(user_id: int, channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM channel_protections WHERE user_id = %s AND channel_id = %s AND used = FALSE", (user_id, channel_id))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None

def use_channel_protection(user_id: int, channel_id: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE channel_protections SET used = TRUE WHERE ctid = (SELECT ctid FROM channel_protections WHERE user_id = %s AND channel_id = %s AND used = FALSE LIMIT 1)", (user_id, channel_id))
    conn.commit()
    cur.close()
    conn.close()

def get_audit_log(channel_id: str, limit: int = 50):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT action, user_id, admin_id, details, created_at FROM audit_log WHERE channel_id = %s ORDER BY created_at DESC LIMIT %s", (channel_id, limit))
    logs = cur.fetchall()
    cur.close()
    conn.close()
    return logs

def is_channel_creator(user_id: int, channel_id: str) -> bool:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT added_by FROM channels WHERE channel_id = %s", (channel_id,))
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result and result[0] == user_id

def validate_channel_id(channel_id: str) -> bool:
    if not channel_id:
        return False
    if channel_id.startswith('@'):
        return len(channel_id) > 1 and channel_id[1:].replace('_', '').isalnum()
    if channel_id.startswith('-100'):
        return channel_id[1:].isdigit() and len(channel_id) >= 13
    return False

def sanitize_caption(caption: str) -> str:
    if not caption:
        return ""
    caption = caption[:1000]
    caption = ''.join(char for char in caption if ord(char) >= 32 or char in '\n\r\t')
    return caption

def check_spam(text: str) -> bool:
    spam_keywords = ['реклама', 'заработок', 'казино', 'ставки', 'кредит', 'займ']
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in spam_keywords)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_user_banned(user_id):
        await update.message.reply_text("❌ Вы заблокированы и не можете отправлять контент.")
        return
    
    help_text = "👋 Привет! Я платформа для модерации контента в Telegram каналах.\n\n"
    
    if is_channel_admin(user_id):
        help_text += "🛡️ Вы администратор канала!\n\n"
        help_text += "Команды админа:\n"
        help_text += "/addchannel - добавить новый канал\n"
        help_text += "/moderate - начать модерацию\n"
        help_text += "/channels - ваши каналы\n"
        help_text += "/stats - статистика ваших каналов\n\n"
    
    help_text += "📤 Отправьте мне картинку, напишите название канала, и я передам её администраторам этого канала на модерацию."
    
    await update.message.reply_text(help_text)

async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    # Показываем кнопки с каналами для модерации
    keyboard = []
    for ch_id in user_channels:
        try:
            chat = await context.bot.get_chat(ch_id)
            channel_name = chat.title
        except:
            channel_name = ch_id
        
        # Считаем количество постов в очереди
        pending_count = len(get_pending_posts(ch_id))
        
        short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel_name} ({pending_count} постов)", 
            callback_data=f"mod_{short_channel_id}"
        )])
    
    # Сохраняем соответствие для админа
    context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛡️ Выберите канал для модерации:",
        reply_markup=reply_markup
    )

async def show_next_post(query, context: ContextTypes.DEFAULT_TYPE, channel_id: str):
    pending_posts = get_pending_posts(channel_id)
    
    if not pending_posts:
        await query.edit_message_text("✅ Все посты в этом канале обработаны!")
        return
    
    # Берем первый пост из очереди
    post_id, user_id, username, photo_file_id, caption, created_at = pending_posts[0]
    
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_name = chat.title
    except:
        channel_name = channel_id
    
    short_channel_id = hashlib.sha256(channel_id.encode()).hexdigest()[:8]
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"app_{post_id}_{short_channel_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"rej_{post_id}_{short_channel_id}")
        ],
        [
            InlineKeyboardButton("🚫 Забанить автора", callback_data=f"ban_{post_id}_{short_channel_id}"),
            InlineKeyboardButton("⏭️ Следующий", callback_data=f"next_{short_channel_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    caption_text = f"📩 Пост от @{username} (ID: {user_id})\n📢 Канал: {channel_name}\n📅 {created_at}\n\nОсталось в очереди: {len(pending_posts)}"
    if caption:
        caption_text += f"\n\n💬 Подпись: {caption}"
    
    try:
        from telegram import InputMediaPhoto
        await query.edit_message_media(
            media=InputMediaPhoto(media=photo_file_id, caption=caption_text),
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error editing media: {e}")
        try:
            await query.message.delete()
        except:
            pass
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=photo_file_id,
                caption=caption_text,
                reply_markup=reply_markup
            )
        except Exception as e2:
            logger.error(f"Error sending new photo: {e2}")
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=caption_text,
                    reply_markup=reply_markup
                )
            except Exception as e3:
                logger.error(f"Error sending message: {e3}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not update.message.photo:
        return
    
    # Проверяем только купленный пропуск (VIP не автопубликует)
    if has_active_item(user_id, 'skip'):
        channels = get_channels_with_names()
        if channels:
            photo = update.message.photo[-1]
            caption = sanitize_caption(update.message.caption or "")
            from datetime import datetime
            for channel in channels:
                channel_id = channel[0]
                try:
                    msg = await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=photo.file_id,
                        caption=caption if caption else None
                    )
                    add_published_post(channel_id, user_id, username, msg.message_id)
                    if has_active_item(user_id, 'pin'):
                        try:
                            await context.bot.pin_chat_message(channel_id, msg.message_id)
                            use_shop_item(user_id, 'pin')
                        except:
                            pass
                    update_channel_setting(channel_id, 'last_post_time', datetime.now())
                except:
                    pass
            use_shop_item(user_id, 'skip')
            
            # Применяем бонусы подписки
            sub = has_active_subscription(user_id)
            coin_bonus = 10
            if sub == 'vip':
                coin_bonus = int(10 * 3)
            elif sub == 'pro':
                coin_bonus = int(10 * 1.5)
            elif sub == 'basic':
                coin_bonus = int(10 * 1.2)
            
            add_coins(user_id, username, coin_bonus, "Мем опубликован")
            await update.message.reply_text("🎫 Пропуск использован! Мем опубликован во всех каналах без модерации.")
            return
    
    channels = get_channels_with_names()
    
    if not channels:
        await update.message.reply_text(
            "⚠️ Пока не настроено ни одного канала.\n"
            "Попросите администратора добавить канал командой /addchannel"
        )
        return
    
    photo = update.message.photo[-1]
    caption = sanitize_caption(update.message.caption or "")
    
    # ФАЗА 4: AI-модерация
    try:
        file = await context.bot.get_file(photo.file_id)
        file_size = file.file_size
        
        # Проверяем автомодерацию для каждого канала
        conn = get_db_connection()
        photo_hash = str(hash(photo.file_id))[:32]  # Упрощенный хеш
        
        # Проверяем базовый спам
        if check_spam(caption):
            await update.message.reply_text("⚠️ Обнаружен подозрительный контент. Пожалуйста, не отправляйте рекламу.")
            conn.close()
            return
        
        # Автомодерация (если включена хотя бы в одном канале)
        auto_mod_result = auto_moderate_content(photo_hash, file_size, sanitize_caption(caption), user_id, conn)
        conn.close()
        
        if not auto_mod_result['approved']:
            warning_text = "⚠️ Автомодерация обнаружила проблемы:\n\n"
            warning_text += "\n".join([f"• {issue}" for issue in auto_mod_result['issues']])
            warning_text += f"\n\nУверенность: {auto_mod_result['confidence']}%"
            await update.message.reply_text(warning_text)
            return
        
        if auto_mod_result['warnings']:
            warning_text = "⚠️ Предупреждения:\n\n"
            warning_text += "\n".join([f"• {w}" for w in auto_mod_result['warnings']])
            await update.message.reply_text(warning_text)
    except Exception as e:
        logger.error(f"Error in auto-moderation: {e}")
    
    context.user_data['photo_file_id'] = photo.file_id
    context.user_data['photo_caption'] = caption
    context.user_data['waiting_for_channel'] = True
    
    # Проверяем привилегии
    sub = has_active_subscription(user_id)
    if has_active_item(user_id, 'priority') or sub in ['basic', 'pro', 'vip']:
        context.user_data['has_priority'] = True
    
    keyboard = [
        [InlineKeyboardButton("🌐 Отправить во все каналы", callback_data=f"selectch_all_{user_id}")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📤 Напишите название или @username канала, в который хотите отправить контент:\n\n"
        "Или нажмите кнопку ниже:",
        reply_markup=reply_markup
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /pay - шаг 1: получатель
    if context.user_data and context.user_data.get('awaiting_pay_recipient'):
        context.user_data['pay_recipient'] = update.message.text.strip()
        context.user_data['awaiting_pay_recipient'] = False
        context.user_data['awaiting_pay_amount'] = True
        await update.message.reply_text("💰 Введите сумму:")
        return
    
    # /pay - шаг 2: сумма
    if context.user_data and context.user_data.get('awaiting_pay_amount'):
        try:
            amount = int(update.message.text.strip())
            recipient = context.user_data.get('pay_recipient')
            context.user_data['awaiting_pay_amount'] = False
            
            user_id = update.effective_user.id
            username = update.effective_user.username or update.effective_user.first_name
            
            if amount <= 0:
                await update.message.reply_text("❌ Сумма должна быть положительной!")
                return
            
            recipient_id = None
            recipient_username = None
            
            if recipient.startswith('@'):
                recipient_username = recipient[1:]
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT user_id FROM user_coins WHERE username = %s", (recipient_username,))
                result = cur.fetchone()
                cur.close()
                conn.close()
                if result:
                    recipient_id = result[0]
                else:
                    await update.message.reply_text(f"❌ Пользователь {recipient} не найден в системе.")
                    return
            else:
                recipient_id = int(recipient)
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT username FROM user_coins WHERE user_id = %s", (recipient_id,))
                result = cur.fetchone()
                cur.close()
                conn.close()
                if result:
                    recipient_username = result[0]
                else:
                    recipient_username = f"user_{recipient_id}"
            
            if recipient_id == user_id and user_id != SUPPORT_ADMIN_ID:
                await update.message.reply_text("❌ Нельзя переводить монеты самому себе!")
                return
            
            if transfer_coins(user_id, recipient_id, amount, username, recipient_username):
                await update.message.reply_text(f"✅ Переведено {amount} монет пользователю @{recipient_username}")
                try:
                    await context.bot.send_message(recipient_id, f"💰 Вы получили {amount} мемкоинов от @{username}!")
                except:
                    pass
            else:
                await update.message.reply_text("❌ Недостаточно монет для перевода!")
            return
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Сумма должна быть числом.")
            return
    
    # /addchannel
    if context.user_data and context.user_data.get('awaiting_addchannel'):
        channel_id = update.message.text.strip()
        context.user_data['awaiting_addchannel'] = False
        await process_addchannel(update, context, channel_id)
        return
    
    # /support
    if context.user_data and context.user_data.get('awaiting_support'):
        message = update.message.text.strip()
        context.user_data['awaiting_support'] = False
        await process_support(update, context, message)
        return
    
    # /reply - шаг 1: user_id
    if context.user_data and context.user_data.get('awaiting_reply_user'):
        try:
            user_id = int(update.message.text.strip())
            context.user_data['reply_user_id'] = user_id
            context.user_data['awaiting_reply_user'] = False
            context.user_data['awaiting_reply_message'] = True
            await update.message.reply_text("💬 Введите сообщение:")
            return
        except ValueError:
            await update.message.reply_text("❌ Неверный ID. Введите число:")
            return
    
    # /reply - шаг 2: сообщение
    if context.user_data and context.user_data.get('awaiting_reply_message'):
        user_id = context.user_data.get('reply_user_id')
        reply_message = update.message.text.strip()
        context.user_data['awaiting_reply_message'] = False
        
        try:
            await context.bot.send_message(user_id, f"💬 Ответ от техподдержки:\n\n{reply_message}")
            await update.message.reply_text(f"✅ Ответ отправлен пользователю {user_id}")
        except Exception as e:
            logger.error(f"Error sending reply: {e}")
            await update.message.reply_text("❌ Ошибка отправки ответа")
        return
    
    # /update - шаг 1: message_id
    if context.user_data and context.user_data.get('awaiting_update_msgid'):
        try:
            message_id = int(update.message.text.strip())
            context.user_data['update_message_id'] = message_id
            context.user_data['awaiting_update_msgid'] = False
            context.user_data['awaiting_update_reactions'] = True
            await update.message.reply_text("👍 Введите количество реакций:")
            return
        except ValueError:
            await update.message.reply_text("❌ Неверный ID. Введите число:")
            return
    
    # /update - шаг 2: reactions
    if context.user_data and context.user_data.get('awaiting_update_reactions'):
        try:
            reactions = int(update.message.text.strip())
            message_id = context.user_data.get('update_message_id')
            context.user_data['awaiting_update_reactions'] = False
            await process_update(update, context, message_id, reactions)
            return
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите число:")
            return
    
    # Обрабатываем ручной ввод настроек
    if context.user_data and context.user_data.get('awaiting_input'):
        setting_type = context.user_data.get('awaiting_input')
        short_channel_id = context.user_data.get('input_channel')
        
        try:
            value = int(update.message.text.strip())
            if value < 0:
                await update.message.reply_text("❌ Значение должно быть положительным числом!")
                return
            
            channel_mapping = context.user_data.get('channel_mapping', {})
            channel_id = channel_mapping.get(short_channel_id)
            
            if setting_type == "interval":
                update_channel_setting(channel_id, 'post_interval_minutes', value)
                text = f"✅ Интервал установлен: {value} мин"
            elif setting_type == "limit":
                update_channel_setting(channel_id, 'max_posts_per_day', value)
                text = f"✅ Лимит установлен: {value} постов/день"
            
            context.user_data['awaiting_input'] = None
            await update.message.reply_text(text)
            return
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите число!")
            return
    
    # Обрабатываем ввод названия канала
    if not context.user_data or not context.user_data.get('waiting_for_channel'):
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    search_query = update.message.text.lower().strip()
    
    if not search_query:
        await update.message.reply_text("❌ Пожалуйста, введите название канала.")
        return
    
    channels = get_channels_with_names()
    matched_channels = []
    
    # Ищем подходящие каналы
    for channel in channels:
        channel_id = channel[0]
        try:
            chat = await context.bot.get_chat(channel_id)
            channel_name = chat.title.lower()
            channel_username = getattr(chat, 'username', '') or ''
            
            # Поиск по названию или username
            if (search_query in channel_name or 
                search_query.replace('@', '') in channel_username.lower() or
                channel_username.lower() == search_query.replace('@', '')):
                matched_channels.append((channel_id, chat.title, channel_username))
        except:
            # Если не можем получить инфо о канале, проверяем по ID
            if search_query == channel_id.lower():
                matched_channels.append((channel_id, channel_id, ''))
    
    if not matched_channels:
        await update.message.reply_text(
            f"❌ Канал с названием '{search_query}' не найден.\n\n"
            "📝 Попробуйте ввести часть названия или @username канала."
        )
        return
    
    photo_file_id = context.user_data.get('photo_file_id')
    caption = context.user_data.get('photo_caption', '')
    
    if len(matched_channels) == 1:
        # Найден только один канал - переходим к выбору опций
        channel_id, channel_name, channel_username = matched_channels[0]
        
        if is_user_banned(user_id, channel_id):
            await update.message.reply_text(f"❌ Вы заблокированы в канале '{channel_name}'.")
            context.user_data['waiting_for_channel'] = False
            return
        
        context.user_data['waiting_for_channel'] = False
        context.user_data['selected_channels'] = [channel_id]
        
        # Переходим к выбору опций
        await ask_pin_option(update, context, user_id)
    else:
        # Найдено несколько каналов - показываем кнопки
        keyboard = []
        for channel_id, channel_name, channel_username in matched_channels:
            short_channel_id = str(hash(channel_id))[-8:]
            display_name = f"{channel_name}"
            if channel_username:
                display_name += f" (@{channel_username})"
            
            keyboard.append([InlineKeyboardButton(
                f"📢 {display_name}", 
                callback_data=f"selectch_{short_channel_id}_{user_id}"
            )])
        
        # Сохраняем соответствие короткого ID и полного
        context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in matched_channels}
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔍 Найдено {len(matched_channels)} канал(ов) с похожим названием.\nВыберите канал:",
            reply_markup=reply_markup
        )

async def ask_pin_option(message_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Спрашивает, нужно ли закреплять пост"""
    sub = has_active_subscription(user_id)
    has_pin = has_active_item(user_id, 'pin') or sub == 'vip'
    
    if has_pin:
        keyboard = [
            [InlineKeyboardButton("📌 Да, закрепить", callback_data=f"optpin_{user_id}_yes")],
            [InlineKeyboardButton("➡️ Нет, продолжить", callback_data=f"optpin_{user_id}_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "📌 Закрепить пост в канале?"
        
        if hasattr(message_or_query, 'edit_message_text'):
            await message_or_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await message_or_query.reply_text(text, reply_markup=reply_markup)
    else:
        context.user_data['use_pin'] = False
        await ask_delayed_option(message_or_query, context, user_id)

async def ask_delayed_option(message_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Спрашивает, нужна ли отложенная публикация"""
    has_delayed = has_active_item(user_id, 'delayed')
    
    if has_delayed:
        keyboard = [
            [InlineKeyboardButton("⏰ Да, с задержкой", callback_data=f"optdelay_{user_id}_yes")],
            [InlineKeyboardButton("➡️ Нет, продолжить", callback_data=f"optdelay_{user_id}_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "⏰ Опубликовать с задержкой?"
        
        if hasattr(message_or_query, 'edit_message_text'):
            await message_or_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await message_or_query.reply_text(text, reply_markup=reply_markup)
    else:
        context.user_data['delay_hours'] = 0
        await ask_skip_option(message_or_query, context, user_id)

async def ask_skip_option(message_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Спрашивает, нужно ли пропустить модерацию"""
    sub = has_active_subscription(user_id)
    has_skip = has_active_item(user_id, 'skip') or sub == 'vip'
    
    if has_skip:
        keyboard = [
            [InlineKeyboardButton("🎫 Да, пропустить", callback_data=f"optskip_{user_id}_yes")],
            [InlineKeyboardButton("📋 Нет, на модерацию", callback_data=f"optskip_{user_id}_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "🎫 Пропустить модерацию?"
        
        if hasattr(message_or_query, 'edit_message_text'):
            await message_or_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await message_or_query.reply_text(text, reply_markup=reply_markup)
    else:
        context.user_data['skip_moderation'] = False
        await finalize_post_submission(message_or_query, context, user_id)

async def finalize_post_submission(message_or_query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Финальная отправка поста с учетом всех выбранных опций"""
    from datetime import datetime, timedelta
    
    username = context.bot_data.get(f'username_{user_id}', 'user')
    if hasattr(message_or_query, 'from_user'):
        username = message_or_query.from_user.username or message_or_query.from_user.first_name
    
    photo_file_id = context.user_data.get('photo_file_id')
    caption = context.user_data.get('photo_caption', '')
    selected_channels = context.user_data.get('selected_channels', [])
    use_pin = context.user_data.get('use_pin', False)
    delay_hours = context.user_data.get('delay_hours', 0)
    skip_moderation = context.user_data.get('skip_moderation', False)
    has_priority = context.user_data.get('has_priority', False)
    
    sub = has_active_subscription(user_id)
    
    if skip_moderation:
        # Публикуем сразу (или с задержкой)
        if delay_hours > 0:
            # Запланированная публикация
            scheduled_time = datetime.now() + timedelta(hours=delay_hours)
            for channel_id in selected_channels:
                add_scheduled_post(channel_id, user_id, username, photo_file_id, caption, scheduled_time)
            
            use_shop_item(user_id, 'delayed')
            if has_active_item(user_id, 'skip'):
                use_shop_item(user_id, 'skip')
            
            text = f"⏰ Пост запланирован на {scheduled_time.strftime('%H:%M %d.%m')}\n📢 Каналов: {len(selected_channels)}"
        else:
            # Мгновенная публикация
            for channel_id in selected_channels:
                try:
                    msg = await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=photo_file_id,
                        caption=caption if caption else None
                    )
                    add_published_post(channel_id, user_id, username, msg.message_id)
                    
                    if use_pin:
                        try:
                            await context.bot.pin_chat_message(channel_id, msg.message_id)
                        except:
                            pass
                    
                    update_channel_setting(channel_id, 'last_post_time', datetime.now())
                except Exception as e:
                    logger.error(f"Error publishing to {channel_id}: {e}")
            
            # Списываем предметы
            if use_pin and has_active_item(user_id, 'pin'):
                use_shop_item(user_id, 'pin')
            if has_active_item(user_id, 'skip'):
                use_shop_item(user_id, 'skip')
            
            # Начисляем монеты
            coin_bonus = 10
            if sub == 'vip':
                coin_bonus = int(10 * 3)
            elif sub == 'pro':
                coin_bonus = int(10 * 1.5)
            elif sub == 'basic':
                coin_bonus = int(10 * 1.2)
            
            add_coins(user_id, username, coin_bonus, "Мем опубликован")
            update_streak(user_id, username)
            check_daily_quests(user_id, username)
            
            text = f"🎉 Мем опубликован!\n💰 +{coin_bonus} монет\n📢 Каналов: {len(selected_channels)}"
    else:
        # Отправляем на модерацию
        for channel_id in selected_channels:
            add_pending_post(channel_id, user_id, username, photo_file_id, caption, has_priority)
        
        if has_priority:
            use_shop_item(user_id, 'priority')
        
        text = f"✅ Отправлено на модерацию\n📢 Каналов: {len(selected_channels)}"
    
    # Очищаем состояние
    context.user_data.clear()
    
    if hasattr(message_or_query, 'edit_message_text'):
        await message_or_query.edit_message_text(text)
    else:
        await message_or_query.reply_text(text)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    action = data_parts[0]
    
    if action == "adm":
        admin_action = data_parts[1]
        if admin_action == "moderate":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            keyboard = []
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    channel_name = chat.title
                except:
                    channel_name = ch_id
                
                pending_count = len(get_pending_posts(ch_id))
                short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                keyboard.append([InlineKeyboardButton(
                    f"📢 {channel_name} ({pending_count} постов)", 
                    callback_data=f"mod_{short_channel_id}"
                )])
            
            context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🛡️ Выберите канал для модерации:", reply_markup=reply_markup)
            return
        elif admin_action == "addchannel":
            await query.edit_message_text("➕ Используйте: /addchannel <channel_id>\n\nПример: /addchannel @mychannel")
            return
        elif admin_action == "settings":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            keyboard = []
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    channel_name = chat.title
                except:
                    channel_name = ch_id
                short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                keyboard.append([InlineKeyboardButton(f"⚙️ {channel_name}", callback_data=f"set_{short_channel_id}")])
            
            context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("⚙️ Выберите канал для настройки:", reply_markup=reply_markup)
            return
        elif admin_action == "stats":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                placeholders = ','.join(['%s'] * len(user_channels))
                cur.execute(f"SELECT COUNT(*) FROM pending_posts WHERE channel_id IN ({placeholders})", user_channels)
                pending_count = cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM banned_users WHERE channel_id IN ({placeholders})", user_channels)
                banned_count = cur.fetchone()[0]
                cur.execute(f"SELECT COUNT(*) FROM audit_log WHERE channel_id IN ({placeholders}) AND action = 'published'", user_channels)
                published_count = cur.fetchone()[0]
                cur.close()
                conn.close()
                
                await query.edit_message_text(
                    f"📊 Статистика ваших каналов:\n\n"
                    f"📢 Каналов: {len(user_channels)}\n"
                    f"✅ Опубликовано: {published_count}\n"
                    f"⏳ В очереди: {pending_count}\n"
                    f"🚫 Забанено: {banned_count}"
                )
            except Exception as e:
                logger.error(f"Error in stats: {e}")
                await query.edit_message_text("❌ Ошибка получения статистики.")
            return
        elif admin_action == "queue":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            response = "📅 Запланированные посты:\n\n"
            has_posts = False
            
            for ch_id in user_channels:
                scheduled = get_scheduled_posts(ch_id)
                if scheduled:
                    has_posts = True
                    try:
                        chat = await context.bot.get_chat(ch_id)
                        response += f"📢 {chat.title}:\n"
                    except:
                        response += f"📢 {ch_id}:\n"
                    
                    for post in scheduled:
                        post_id, _, _, username, _, _, scheduled_time = post
                        response += f"  • От @{username} → {scheduled_time.strftime('%H:%M %d.%m')}\n"
            
            if not has_posts:
                response += "✅ Нет запланированных постов"
            
            await query.edit_message_text(response)
            return
        elif admin_action == "audit":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            keyboard = []
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    channel_name = chat.title
                except:
                    channel_name = ch_id
                short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                keyboard.append([InlineKeyboardButton(f"📊 {channel_name}", callback_data=f"aud_{short_channel_id}")])
            
            context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📊 Выберите канал для просмотра истории:", reply_markup=reply_markup)
            return
        elif admin_action == "unban":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Эта команда доступна только администраторам.")
                return
            
            keyboard = []
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    channel_name = chat.title
                except:
                    channel_name = ch_id
                
                short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                keyboard.append([InlineKeyboardButton(
                    f"📢 {channel_name}",
                    callback_data=f"ubc_{short_channel_id}"
                )])
            
            context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🚫 Выберите канал для разблокировки пользователей:", reply_markup=reply_markup)
            return
        elif admin_action == "channels":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("📋 Вы не являетесь администратором ни одного канала.")
                return
            
            response = "📋 Ваши каналы:\n\n"
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    pending_count = len(get_pending_posts(ch_id))
                    response += f"• {chat.title} ({pending_count} в очереди)\n"
                except:
                    response += f"• {ch_id}\n"
            
            await query.edit_message_text(response)
            return
        elif admin_action == "topchannel":
            user_id = query.from_user.id
            user_channels = get_user_channels(user_id)
            
            if not user_channels:
                await query.edit_message_text("❌ Вы не являетесь администратором ни одного канала.")
                return
            
            keyboard = []
            for ch_id in user_channels:
                try:
                    chat = await context.bot.get_chat(ch_id)
                    channel_name = chat.title
                except:
                    channel_name = ch_id
                
                short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                keyboard.append([InlineKeyboardButton(
                    f"🏆 {channel_name}",
                    callback_data=f"top_{short_channel_id}"
                )])
            
            context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🏆 Выберите канал для просмотра таблицы лидеров:", reply_markup=reply_markup)
            return
    
    if action == "selectch":
        # Выбор канала (конкретный или все)
        if data_parts[1] == "all":
            user_id = int(data_parts[2])
            if query.from_user.id != user_id:
                await query.answer("❌ Это не ваш контент!")
                return
            
            channels = get_channels_with_names()
            channel_ids = []
            for channel in channels:
                channel_id = channel[0]
                settings = get_channel_settings(channel_id)
                if settings.get('allow_global', True) and not is_user_banned(user_id, channel_id):
                    channel_ids.append(channel_id)
            
            context.user_data['selected_channels'] = channel_ids
            await ask_pin_option(query, context, user_id)
        else:
            short_channel_id = data_parts[1]
            user_id = int(data_parts[2])
            
            if query.from_user.id != user_id:
                await query.answer("❌ Это не ваш контент!")
                return
            
            channel_mapping = context.user_data.get('channel_mapping', {})
            channel_id = channel_mapping.get(short_channel_id)
            
            if not channel_id:
                await query.edit_message_text("❌ Ошибка: канал не найден.")
                return
            
            if is_user_banned(user_id, channel_id):
                await query.edit_message_text("❌ Вы заблокированы в этом канале.")
                return
            
            context.user_data['selected_channels'] = [channel_id]
            await ask_pin_option(query, context, user_id)
    
    elif action == "mod":
        # Админ выбрал канал для модерации
        short_channel_id = data_parts[1]
        
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id:
            await query.edit_message_text("❌ Ошибка: канал не найден.")
            return
        
        if not is_channel_admin(query.from_user.id, channel_id):
            await query.edit_message_text("❌ Вы не администратор этого канала!")
            return
        
        # Показываем первый пост из очереди
        await show_next_post(query, context, channel_id)
    
    elif action == "set":
        short_channel_id = data_parts[1]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id or not is_channel_creator(query.from_user.id, channel_id):
            await query.edit_message_text("❌ Только создатель канала может изменять настройки!")
            return
        
        settings = get_channel_settings(channel_id)
        smart_mode = "🤖 AI" if settings.get('smart_mode', False) else "📅 Простой"
        automod = "✅ ON" if settings.get('auto_moderation', False) else "❌ OFF"
        
        keyboard = [
            [InlineKeyboardButton(f"⏱ Интервал: {settings['interval']} мин", callback_data=f"cfg_interval_{short_channel_id}")],
            [InlineKeyboardButton(f"📊 Лимит: {settings['max_posts']} постов/день", callback_data=f"cfg_limit_{short_channel_id}")],
            [InlineKeyboardButton(f"📝 Подпись: {'required' if settings['require_caption'] else 'optional'}", callback_data=f"cfg_caption_{short_channel_id}")],
            [InlineKeyboardButton(f"🚫 Спам-фильтр: {'ON' if settings['spam_filter'] else 'OFF'}", callback_data=f"cfg_spam_{short_channel_id}")],
            [InlineKeyboardButton(f"🌐 Общие мемы: {'ON' if settings.get('allow_global', True) else 'OFF'}", callback_data=f"cfg_global_{short_channel_id}")],
            [InlineKeyboardButton(f"🤖 Планирование: {smart_mode}", callback_data=f"cfg_smartmode_{short_channel_id}")],
            [InlineKeyboardButton(f"🛡️ Автомодерация: {automod}", callback_data=f"cfg_automod_{short_channel_id}")],
            [InlineKeyboardButton("📊 Аналитика", callback_data=f"cfg_analytics_{short_channel_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚙️ Настройки канала:", reply_markup=reply_markup)
    
    elif action == "cfg":
        setting_type = data_parts[1]
        short_channel_id = data_parts[2]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if setting_type == "interval":
            keyboard = [
                [InlineKeyboardButton("⚡ 0 мин (сразу)", callback_data=f"sav_interval_0_{short_channel_id}")],
                [InlineKeyboardButton("⏱ 1 мин", callback_data=f"sav_interval_1_{short_channel_id}")],
                [InlineKeyboardButton("🕔 5 мин", callback_data=f"sav_interval_5_{short_channel_id}")],
                [InlineKeyboardButton("🕛 30 мин", callback_data=f"sav_interval_30_{short_channel_id}")],
                [InlineKeyboardButton("🕐 60 мин", callback_data=f"sav_interval_60_{short_channel_id}")],
                [InlineKeyboardButton("🕒 180 мин", callback_data=f"sav_interval_180_{short_channel_id}")],
                [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"inp_interval_{short_channel_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("⏱ Выберите интервал между постами:", reply_markup=reply_markup)
        elif setting_type == "limit":
            keyboard = [
                [InlineKeyboardButton("♾️ Без лимита", callback_data=f"sav_limit_0_{short_channel_id}")],
                [InlineKeyboardButton("🔟 10 постов/день", callback_data=f"sav_limit_10_{short_channel_id}")],
                [InlineKeyboardButton("🔠 20 постов/день", callback_data=f"sav_limit_20_{short_channel_id}")],
                [InlineKeyboardButton("🔡 50 постов/день", callback_data=f"sav_limit_50_{short_channel_id}")],
                [InlineKeyboardButton("✏️ Ввести вручную", callback_data=f"inp_limit_{short_channel_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📊 Выберите лимит постов в день:", reply_markup=reply_markup)
        elif setting_type == "caption":
            settings = get_channel_settings(channel_id)
            new_value = not settings['require_caption']
            update_channel_setting(channel_id, 'require_caption', new_value)
            await query.answer(f"✅ Подпись {'required' if new_value else 'optional'}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"✅ Подпись теперь {'required' if new_value else 'optional'}", reply_markup=reply_markup)
        elif setting_type == "spam":
            settings = get_channel_settings(channel_id)
            new_value = not settings['spam_filter']
            update_channel_setting(channel_id, 'spam_filter_enabled', new_value)
            await query.answer(f"✅ Спам-фильтр {'ON' if new_value else 'OFF'}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"✅ Спам-фильтр теперь {'ON' if new_value else 'OFF'}", reply_markup=reply_markup)
        elif setting_type == "global":
            settings = get_channel_settings(channel_id)
            new_value = not settings.get('allow_global', True)
            update_channel_setting(channel_id, 'allow_global_posts', new_value)
            await query.answer(f"✅ Общие мемы {'ON' if new_value else 'OFF'}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"✅ Общие мемы теперь {'ON' if new_value else 'OFF'}\n\n{'Канал будет получать мемы, отправленные во все каналы' if new_value else 'Канал не будет получать мемы, отправленные во все каналы'}", reply_markup=reply_markup)
        elif setting_type == "smartmode":
            settings = get_channel_settings(channel_id)
            current_mode = settings.get('smart_mode', False)
            keyboard = [
                [InlineKeyboardButton("📅 Простой режим", callback_data=f"sms_simple_{short_channel_id}")],
                [InlineKeyboardButton("🤖 AI (Conservative)", callback_data=f"sms_conservative_{short_channel_id}")],
                [InlineKeyboardButton("🤖 AI (Medium)", callback_data=f"sms_medium_{short_channel_id}")],
                [InlineKeyboardButton("🤖 AI (Aggressive)", callback_data=f"sms_aggressive_{short_channel_id}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            mode_text = "🤖 AI" if current_mode else "📅 Простой"
            await query.edit_message_text(
                f"🤖 Текущий режим: {mode_text}\n\n"
                f"📅 Простой: публикация через N минут\n"
                f"🤖 AI: умное планирование на основе:\n"
                f"  • Размер очереди\n"
                f"  • Лучшее время (по реакциям)\n"
                f"  • День недели\n"
                f"  • Избегание перегрузки\n\n"
                f"Выберите режим:",
                reply_markup=reply_markup
            )
        elif setting_type == "automod":
            settings = get_channel_settings(channel_id)
            new_value = not settings.get('auto_moderation', False)
            update_channel_setting(channel_id, 'auto_moderation', new_value)
            await query.answer(f"✅ Автомодерация {'ON' if new_value else 'OFF'}")
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            status_text = "ON" if new_value else "OFF"
            details_text = "🛡️ Проверяется:\n• Дубликаты мемов\n• Качество изображения\n• Спам и реклама\n• Частота отправки" if new_value else "❌ Автоматическая проверка отключена"
            await query.edit_message_text(
                f"✅ Автомодерация: {status_text}\n\n{details_text}",
                reply_markup=reply_markup
            )
        elif setting_type == "analytics":
            conn = get_db_connection()
            growth = get_growth_stats(channel_id, conn)
            approval = get_approval_rate(channel_id, conn)
            top_authors = get_top_authors(channel_id, conn, 3)
            analytics_data = get_channel_analytics(channel_id, conn)
            conn.close()
            
            response = f"📊 Аналитика канала:\n\n"
            response += f"📈 Рост за неделю:\n"
            response += f"📊 Постов: {growth['posts_week']} ({growth['posts_growth']:+.1f}%)\n\n"
            response += f"✅ Одобрение: {approval['rate']:.1f}%\n"
            response += f"📋 Очередь: {analytics_data['queue_size']} постов\n\n"
            
            if top_authors:
                response += "🏆 Топ-3 автора:\n"
                for idx, (uid, uname, posts) in enumerate(top_authors, 1):
                    response += f"{idx}. @{uname} - {posts} постов\n"
            
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(response, reply_markup=reply_markup)
    
    elif action == "sav":
        setting_type = data_parts[1]
        value = int(data_parts[2])
        short_channel_id = data_parts[3]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if setting_type == "interval":
            update_channel_setting(channel_id, 'post_interval_minutes', value)
            text = f"✅ Интервал установлен: {value} мин"
        elif setting_type == "limit":
            update_channel_setting(channel_id, 'max_posts_per_day', value)
            text = f"✅ Лимит установлен: {value} постов/день"
        
        await query.answer("✅ Сохранено!")
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data=f"set_{short_channel_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    elif action == "inp":
        setting_type = data_parts[1]
        short_channel_id = data_parts[2]
        
        context.user_data['awaiting_input'] = setting_type
        context.user_data['input_channel'] = short_channel_id
        
        if setting_type == "interval":
            text = "✏️ Введите интервал в минутах (например: 15)"
        elif setting_type == "limit":
            text = "✏️ Введите лимит постов в день (например: 25)"
        
        await query.edit_message_text(text)
    
    elif action == "ubc":
        # Выбор канала для разбана
        short_channel_id = data_parts[1]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id or not is_channel_admin(query.from_user.id, channel_id):
            await query.edit_message_text("❌ Вы не администратор этого канала!")
            return
        
        banned = get_banned_users(channel_id)
        if not banned:
            await query.edit_message_text("✅ В этом канале нет заблокированных пользователей")
            return
        
        keyboard = []
        for user_id, username, banned_at, banned_by in banned:
            keyboard.append([InlineKeyboardButton(
                f"🚫 @{username} (ID: {user_id})",
                callback_data=f"unb_{user_id}_{short_channel_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🚫 Заблокированные пользователи:\nНажмите для разблокировки:", reply_markup=reply_markup)
    
    elif action == "unb":
        # Разбан пользователя
        banned_user_id = int(data_parts[1])
        short_channel_id = data_parts[2]
        
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id or not is_channel_admin(query.from_user.id, channel_id):
            await query.answer("❌ Нет прав!")
            return
        
        unban_user(banned_user_id, channel_id)
        await query.answer("✅ Пользователь разблокирован!")
        
        # Обновляем список
        banned = get_banned_users(channel_id)
        if not banned:
            await query.edit_message_text("✅ Все пользователи разблокированы!")
            return
        
        keyboard = []
        for user_id, username, banned_at, banned_by in banned:
            keyboard.append([InlineKeyboardButton(
                f"🚫 @{username} (ID: {user_id})",
                callback_data=f"unb_{user_id}_{short_channel_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🚫 Заблокированные пользователи:\nНажмите для разблокировки:", reply_markup=reply_markup)
    
    elif action == "aud":
        short_channel_id = data_parts[1]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        logs = get_audit_log(channel_id, 20)
        response = "📊 История действий:\n\n"
        for log in logs:
            action_name, user_id, admin_id, details, created_at = log
            response += f"• {action_name} | Админ: {admin_id} | {created_at.strftime('%H:%M %d.%m')}\n"
        
        await query.edit_message_text(response)
    
    elif action == "sms":
        # Сохранение режима планирования
        mode = data_parts[1]
        short_channel_id = data_parts[2]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if mode == "simple":
            update_channel_setting(channel_id, 'smart_mode', False)
            await query.answer("✅ Простой режим")
            await query.edit_message_text("✅ Установлен простой режим планирования")
        else:
            update_channel_setting(channel_id, 'smart_mode', True)
            update_channel_setting(channel_id, 'aggressiveness', mode)
            await query.answer(f"✅ AI-режим ({mode})")
            await query.edit_message_text(f"✅ Установлен AI-режим ({mode})\n\nПубликации будут планироваться автоматически")
    
    elif action == "top":
        short_channel_id = data_parts[1]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id:
            await query.edit_message_text("❌ Ошибка: канал не найден.")
            return
        
        try:
            chat = await context.bot.get_chat(channel_id)
            channel_name = chat.title
        except:
            channel_name = channel_id
        
        leaders = get_channel_leaderboard(channel_id, 10)
        
        if not leaders:
            await query.edit_message_text(f"🏆 Таблица лидеров канала '{channel_name}' пуста.")
            return
        
        response = f"🏆 Таблица лидеров: {channel_name}\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (user_id, username, posts, reactions) in enumerate(leaders, 1):
            medal = medals[idx-1] if idx <= 3 else f"{idx}."
            rank = get_user_rank(posts)
            response += f"{medal} @{username} {rank}\n"
            response += f"   📊 Мемов: {posts} | 👍 Реакций: {reactions}\n\n"
        
        await query.edit_message_text(response)
    
    elif action == "shop":
        shop_action = data_parts[1]
        user_id = query.from_user.id
        balance, _ = get_user_balance(user_id)
        
        if shop_action == "items":
            keyboard = [
                [InlineKeyboardButton("🎁 Премиум лутбокс (500)", callback_data="buy_lootbox")],
                [InlineKeyboardButton("🎰 Рулетка удачи (500)", callback_data="buy_roulette")],
                [InlineKeyboardButton("🎫 Пропуск модерации (2000)", callback_data="buy_skip")],
                [InlineKeyboardButton("⚡ Приоритет (1000)", callback_data="buy_priority")],
                [InlineKeyboardButton("📌 Закрепить пост (3000)", callback_data="buy_pin")],
                [InlineKeyboardButton("🛡️ Защита от бана (5000)", callback_data="buy_protection")],
                [InlineKeyboardButton("⏰ Отложенная публикация (500)", callback_data="buy_delayed")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="shop_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"📦 Одноразовые товары\n\n"
                f"💰 Баланс: {balance} монет\n\n"
                f"🎁 Премиум лутбокс - 200-2000 монет\n"
                f"🎰 Рулетка - шанс выиграть до 5000\n"
                f"🎫 Пропуск - без модерации\n"
                f"⚡ Приоритет - первым в очереди\n"
                f"📌 Закрепить - пост будет закреплен\n"
                f"🛡️ Защита - отменяет бан 1 раз\n"
                f"⏰ Отложенная - по расписанию",
                reply_markup=reply_markup
            )
            return
        elif shop_action == "subs":
            sub = has_active_subscription(user_id)
            keyboard = [
                [InlineKeyboardButton("🌟 Basic (2000 / 30 дней)", callback_data="buy_sub_basic")],
                [InlineKeyboardButton("⭐ Pro (5000 / 14 дней)", callback_data="buy_sub_pro")],
                [InlineKeyboardButton("👑 VIP (50000 / 7 дней)", callback_data="buy_sub_vip")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="shop_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sub_text = f"\n\n💎 Активна: {sub}" if sub else ""
            await query.edit_message_text(
                f"💎 Подписки Premium\n\n"
                f"💰 Баланс: {balance} монет{sub_text}\n\n"
                f"🌟 Basic:\n• Автоприоритет\n• +20% монет\n• 1 лутбокс/неделю\n\n"
                f"⭐ Pro:\n• Все из Basic\n• +50% монет\n• 1 пропуск/неделю\n• 2 лутбокса/неделю\n\n"
                f"👑 VIP:\n• Все из Pro\n• +200% монет\n• Безлимит пропусков\n• Защита от бана\n• 1 лутбокс/день",
                reply_markup=reply_markup
            )
            return
        elif shop_action == "back":
            sub = has_active_subscription(user_id)
            keyboard = [
                [InlineKeyboardButton("📦 Одноразовые товары", callback_data="shop_items")],
                [InlineKeyboardButton("💎 Подписки Premium", callback_data="shop_subs")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            sub_text = f"\n💎 Активна: {sub}" if sub else ""
            await query.edit_message_text(
                f"🛒 Магазин\n\n"
                f"💰 Баланс: {balance} монет{sub_text}\n\n"
                f"Выберите категорию:",
                reply_markup=reply_markup
            )
            return
    
    elif action == "buy":
        item_type = data_parts[1]
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name
        
        if item_type == "sub":
            sub_type = data_parts[2]
            costs = {'basic': 2000, 'pro': 5000, 'vip': 50000}
            days = {'basic': 30, 'pro': 14, 'vip': 7}
            cost = costs[sub_type]
            
            if buy_subscription(user_id, username, sub_type, cost, days[sub_type]):
                await query.answer("✅ Подписка активирована!")
                await query.edit_message_text(f"✅ Подписка {sub_type.upper()} активирована на {days[sub_type]} дней!")
            else:
                await query.answer("❌ Недостаточно монет!")
            return
        
        if item_type == "lootbox":
            import random
            cost = 500
            if spend_coins(user_id, cost, "🎁 Премиум лутбокс"):
                roll = random.random()
                if roll < 0.01:
                    reward = 2000
                elif roll < 0.10:
                    reward = random.randint(1000, 1500)
                elif roll < 0.40:
                    reward = random.randint(500, 1000)
                else:
                    reward = random.randint(200, 500)
                add_coins(user_id, username, reward, "🎁 Лутбокс")
                await query.answer(f"🎉 +{reward} монет!")
                await query.edit_message_text(f"🎁 Лутбокс открыт!\n\n💰 Вы получили: {reward} монет")
            else:
                await query.answer("❌ Недостаточно монет!")
            return
        
        if item_type == "roulette":
            import random
            cost = 500
            if spend_coins(user_id, cost, "🎰 Рулетка"):
                roll = random.random()
                if roll < 0.02:
                    reward = 5000
                elif roll < 0.10:
                    reward = 2000
                elif roll < 0.30:
                    reward = 1000
                elif roll < 0.60:
                    reward = 500
                else:
                    reward = 0
                if reward > 0:
                    add_coins(user_id, username, reward, "🎰 Рулетка")
                    await query.answer(f"🎉 +{reward} монет!")
                    await query.edit_message_text(f"🎰 Рулетка!\n\n🎉 Выигрыш: {reward} монет")
                else:
                    await query.answer("😔 Не повезло")
                    await query.edit_message_text("🎰 Рулетка!\n\n😔 Не повезло. Попробуйте еще!")
            else:
                await query.answer("❌ Недостаточно монет!")
            return
        
        if item_type == 'protection':
            cost = 5000
            if spend_coins(user_id, cost, "🛡️ Защита от бана"):
                user_channels = get_user_channels(user_id)
                if user_channels:
                    keyboard = []
                    for ch_id in user_channels:
                        try:
                            chat = await context.bot.get_chat(ch_id)
                            channel_name = chat.title
                        except:
                            channel_name = ch_id
                        short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
                        keyboard.append([InlineKeyboardButton(f"📌 {channel_name}", callback_data=f"prot_{short_channel_id}")])
                    context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
                    context.user_data['buying_protection'] = True
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await query.edit_message_text("🛡️ Выберите канал для защиты:", reply_markup=reply_markup)
                else:
                    await query.answer("❌ Вы не админ каналов!")
            else:
                await query.answer("❌ Недостаточно монет!")
            return
        
        costs = {'priority': 1000, 'skip': 2000, 'pin': 3000, 'delayed': 500}
        cost = costs.get(item_type, 0)
        
        if buy_shop_item(user_id, username, item_type, cost, 24):
            await query.answer("✅ Куплено!")
            await query.edit_message_text(f"✅ Вы купили {item_type} за {cost} монет!")
        else:
            await query.answer("❌ Недостаточно монет!")
    
    elif action == "optpin":
        # Выбор: закреплять или нет
        user_id = int(data_parts[1])
        use_pin = data_parts[2] == "yes"
        
        if query.from_user.id != user_id:
            await query.answer("❌ Это не ваш контент!")
            return
        
        context.user_data['use_pin'] = use_pin
        await ask_delayed_option(query, context, user_id)
    
    elif action == "optdelay":
        # Выбор: с задержкой или нет
        user_id = int(data_parts[1])
        
        if query.from_user.id != user_id:
            await query.answer("❌ Это не ваш контент!")
            return
        
        if data_parts[2] == "no":
            context.user_data['delay_hours'] = 0
            await ask_skip_option(query, context, user_id)
        else:
            # Показываем варианты задержки
            keyboard = [
                [InlineKeyboardButton("⏱ 1 час", callback_data=f"setdelay_{user_id}_1")],
                [InlineKeyboardButton("⏱ 3 часа", callback_data=f"setdelay_{user_id}_3")],
                [InlineKeyboardButton("⏱ 6 часов", callback_data=f"setdelay_{user_id}_6")],
                [InlineKeyboardButton("⏱ 12 часов", callback_data=f"setdelay_{user_id}_12")],
                [InlineKeyboardButton("⏱ 24 часа", callback_data=f"setdelay_{user_id}_24")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("⏰ Выберите задержку:", reply_markup=reply_markup)
    
    elif action == "setdelay":
        # Установка конкретной задержки
        user_id = int(data_parts[1])
        hours = int(data_parts[2])
        
        if query.from_user.id != user_id:
            await query.answer("❌ Это не ваш контент!")
            return
        
        context.user_data['delay_hours'] = hours
        await ask_skip_option(query, context, user_id)
    
    elif action == "optskip":
        # Выбор: пропустить модерацию или нет
        user_id = int(data_parts[1])
        skip_mod = data_parts[2] == "yes"
        
        if query.from_user.id != user_id:
            await query.answer("❌ Это не ваш контент!")
            return
        
        context.user_data['skip_moderation'] = skip_mod
        await finalize_post_submission(query, context, user_id)
    
    elif action == "skipmod":
        user_id = int(data_parts[1])
        if query.from_user.id != user_id:
            await query.answer("❌ Это не ваш контент!")
            return
        
        photo_file_id = context.user_data.get('photo_file_id')
        caption = context.user_data.get('photo_caption', '')
        username = query.from_user.username or query.from_user.first_name
        channels = get_channels_with_names()
        
        if channels:
            from datetime import datetime
            for channel in channels:
                channel_id = channel[0]
                try:
                    msg = await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=photo_file_id,
                        caption=caption if caption else None
                    )
                    add_published_post(channel_id, user_id, username, msg.message_id)
                    sub = has_active_subscription(user_id)
                    if has_active_item(user_id, 'pin') or sub == 'vip':
                        try:
                            await context.bot.pin_chat_message(channel_id, msg.message_id)
                            if has_active_item(user_id, 'pin'):
                                use_shop_item(user_id, 'pin')
                        except:
                            pass
                    update_channel_setting(channel_id, 'last_post_time', datetime.now())
                except:
                    pass
            
            if has_active_item(user_id, 'skip'):
                use_shop_item(user_id, 'skip')
            
            sub = has_active_subscription(user_id)
            coin_bonus = 10
            if sub == 'vip':
                coin_bonus = int(10 * 3)
            elif sub == 'pro':
                coin_bonus = int(10 * 1.5)
            elif sub == 'basic':
                coin_bonus = int(10 * 1.2)
            
            add_coins(user_id, username, coin_bonus, "Мем опубликован")
            context.user_data['waiting_for_channel'] = False
            await query.edit_message_text("🎫 Пропуск использован! Мем опубликован во всех каналах.")
        return
    
    elif action == "refund":
        refund_type = data_parts[1]
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name
        
        if refund_type == "sub":
            from datetime import datetime, timedelta
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT subscription_type, created_at FROM user_subscriptions WHERE user_id = %s AND expires_at > NOW()", (user_id,))
            sub_info = cur.fetchone()
            
            if not sub_info:
                await query.answer("❌ Нет активной подписки!")
                cur.close()
                conn.close()
                return
            
            sub_type, created_at = sub_info
            
            # Проверяем, прошел ли 1 день
            if (datetime.now() - created_at) >= timedelta(days=1):
                await query.answer("❌ Возврат возможен только в первый день!")
                cur.close()
                conn.close()
                return
            
            # Рассчитываем возврат (50%)
            costs = {'basic': 2000, 'pro': 5000, 'vip': 50000}
            refund_amount = costs[sub_type] // 2
            
            # Удаляем подписку
            cur.execute("DELETE FROM user_subscriptions WHERE user_id = %s", (user_id,))
            conn.commit()
            cur.close()
            conn.close()
            
            # Возвращаем монеты
            add_coins(user_id, username, refund_amount, f"🔙 Возврат {sub_type.upper()} (-50%)")
            
            await query.answer("✅ Возврат оформлен!")
            await query.edit_message_text(
                f"🔙 Подписка {sub_type.upper()} отменена\n\n"
                f"💰 Возвращено: {refund_amount} монет (50%)\n\n"
                f"ℹ️ Комиссия за возврат: 50%"
            )
        return
    
    elif action == "prot":
        if not context.user_data.get('buying_protection'):
            return
        short_channel_id = data_parts[1]
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        user_id = query.from_user.id
        
        if channel_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO channel_protections (user_id, channel_id) VALUES (%s, %s)", (user_id, channel_id))
            conn.commit()
            cur.close()
            conn.close()
            
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
            except:
                channel_name = channel_id
            
            context.user_data['buying_protection'] = False
            await query.answer("✅ Защита активирована!")
            await query.edit_message_text(f"🛡️ Защита от бана активирована для '{channel_name}'!")
        return
    
    elif action in ["app", "rej", "ban", "next"]:
        # Админ модерирует пост
        if action == "next":
            short_channel_id = data_parts[1]
        else:
            post_id = int(data_parts[1])
            short_channel_id = data_parts[2]
        
        channel_mapping = context.user_data.get('channel_mapping', {})
        channel_id = channel_mapping.get(short_channel_id)
        
        if not channel_id:
            await query.edit_message_text("❌ Ошибка: канал не найден.")
            return
        
        if not is_channel_admin(query.from_user.id, channel_id):
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n⚠️ Вы не администратор этого канала!"
            )
            return
        
        if action == "next":
            # Просто показываем следующий пост
            await show_next_post(query, context, channel_id)
            return
        
        # Получаем данные поста
        pending_posts = get_pending_posts(channel_id)
        current_post = None
        for post in pending_posts:
            if post[0] == post_id:
                current_post = post
                break
        
        if not current_post:
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n❌ Пост не найден в очереди!"
            )
            return
        
        post_id, user_id, username, photo_file_id, caption, created_at = current_post
        
        if action == "app":
            try:
                settings = get_channel_settings(channel_id)
                from datetime import datetime, timedelta
                
                if settings['interval'] > 0 and settings['last_post']:
                    next_post_time = settings['last_post'] + timedelta(minutes=settings['interval'])
                    if datetime.now() < next_post_time:
                        add_scheduled_post(channel_id, user_id, username, photo_file_id, caption, next_post_time)
                        remove_pending_post(post_id)
                        log_action(channel_id, 'scheduled', user_id, query.from_user.id, post_id, f"Scheduled for {next_post_time}")
                        await query.answer(f"⏱ Пост запланирован на {next_post_time.strftime('%H:%M')}")
                        await show_next_post(query, context, channel_id)
                        return
                
                # ФАЗА 4: Умное планирование
                settings = get_channel_settings(channel_id)
                from datetime import datetime, timedelta
                
                if settings.get('smart_mode', False):
                    conn = get_db_connection()
                    next_time = calculate_smart_schedule(channel_id, conn, settings.get('aggressiveness', 'medium'))
                    conn.close()
                    
                    if next_time > datetime.now():
                        add_scheduled_post(channel_id, user_id, username, photo_file_id, caption, next_time)
                        remove_pending_post(post_id)
                        log_action(channel_id, 'smart_scheduled', user_id, query.from_user.id, post_id, f"Scheduled for {next_time}")
                        await query.answer(f"🤖 Умное планирование: {next_time.strftime('%H:%M %d.%m')}")
                        await show_next_post(query, context, channel_id)
                        return
                
                msg = await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=photo_file_id,
                    caption=caption if caption else None
                )
                
                add_published_post(channel_id, user_id, username, msg.message_id)
                
                # Проверяем привилегию закрепления или VIP
                sub = has_active_subscription(user_id)
                if has_active_item(user_id, 'pin') or sub == 'vip':
                    try:
                        await context.bot.pin_chat_message(channel_id, msg.message_id)
                        if has_active_item(user_id, 'pin'):
                            use_shop_item(user_id, 'pin')
                    except Exception as e:
                        logger.error(f"Error pinning message: {e}")
                
                # Применяем бонусы подписки
                sub = has_active_subscription(user_id)
                coin_bonus = 10
                if sub == 'vip':
                    coin_bonus = int(10 * 3)  # +200%
                elif sub == 'pro':
                    coin_bonus = int(10 * 1.5)  # +50%
                elif sub == 'basic':
                    coin_bonus = int(10 * 1.2)  # +20%
                
                add_coins(user_id, username, coin_bonus, "Мем опубликован")
                update_streak(user_id, username)
                check_daily_quests(user_id, username)
                
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM published_posts WHERE user_id = %s", (user_id,))
                posts_count = cur.fetchone()[0]
                cur.close()
                conn.close()
                
                achievements = check_and_award_achievements(user_id, username, posts_count)
                rank = get_user_rank(posts_count)
                
                update_channel_setting(channel_id, 'last_post_time', datetime.now())
                remove_pending_post(post_id)
                log_action(channel_id, 'published', user_id, query.from_user.id, post_id)
                
                try:
                    chat = await context.bot.get_chat(channel_id)
                    channel_name = chat.title
                except:
                    channel_name = "канале"
                
                notif = f"🎉 Ваш контент опубликован в {channel_name}!\n💰 +10 мемкоинов\n{rank} | Мемов: {posts_count}"
                if achievements:
                    notif += "\n\n🏆 " + "\n🏆 ".join(achievements)
                
                await context.bot.send_message(chat_id=user_id, text=notif)
                
                await show_next_post(query, context, channel_id)
                
            except Exception as e:
                logger.error(f"Ошибка публикации в {channel_id}: {str(e)}")
                remove_pending_post(post_id)
                await show_next_post(query, context, channel_id)
        
        elif action == "rej":
            remove_pending_post(post_id)
            log_action(channel_id, 'rejected', user_id, query.from_user.id, post_id)
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="😔 Ваш контент не прошел модерацию."
                )
            except:
                pass
            
            await show_next_post(query, context, channel_id)
        
        elif action == "ban":
            # Проверяем защиту от бана
            if has_channel_protection(user_id, channel_id):
                use_channel_protection(user_id, channel_id)
                await query.answer("🛡️ Защита сработала!")
                try:
                    await context.bot.send_message(user_id, "🛡️ Ваша защита от бана сработала!")
                except:
                    pass
                await show_next_post(query, context, channel_id)
                return
            
            # Проверяем VIP подписку
            sub = has_active_subscription(user_id)
            if sub == 'vip':
                await query.answer("👑 VIP защищен от бана!")
                try:
                    await context.bot.send_message(user_id, "👑 Ваша VIP подписка защитила вас от бана!")
                except:
                    pass
                await show_next_post(query, context, channel_id)
                return
            
            ban_user(user_id, username, query.from_user.id, channel_id)
            remove_pending_post(post_id)
            log_action(channel_id, 'banned', user_id, query.from_user.id, post_id, f"User {username} banned")
            
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
            except:
                channel_name = "этом канале"
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🚫 Вы заблокированы в канале '{channel_name}' и больше не можете отправлять туда контент."
                )
            except:
                pass
            
            await show_next_post(query, context, channel_id)

async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    context.user_data['awaiting_addchannel'] = True
    await update.message.reply_text(
        "➕ Добавление канала\n\n"
        "Введите @username или ID канала:\n\n"
        "📝 Убедитесь, что:\n"
        "1. Бот добавлен в канал как администратор\n"
        "2. У бота есть права на публикацию сообщений\n"
        "3. Вы сами являетесь администратором канала"
    )
    return

async def process_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: str):
    user_id = update.effective_user.id
    
    if not validate_channel_id(channel_id):
        await update.message.reply_text("❌ Неверный формат ID канала!\n\nИспользуйте @username или -100XXXXXXXXXX")
        return
    
    try:
        chat = await context.bot.get_chat(channel_id)
        
        if chat.type not in ['channel', 'supergroup']:
            await update.message.reply_text("❌ Это не канал или супергруппа!")
            return
        
        member = await context.bot.get_chat_member(channel_id, user_id)
        if member.status not in ["administrator", "creator"]:
            await update.message.reply_text("❌ Вы не являетесь администратором этого канала!")
            return
        
        administrators = await context.bot.get_chat_administrators(channel_id)
        
        admin_list = []
        for admin in administrators:
            if not admin.user.is_bot:
                admin_list.append({
                    'user_id': admin.user.id,
                    'username': admin.user.username or admin.user.first_name or f"user_{admin.user.id}"
                })
        
        add_channel(channel_id, user_id)
        update_channel_admins(channel_id, admin_list)
        
        admin_names = ", ".join([f"@{a['username']}" for a in admin_list])
        
        await update.message.reply_text(
            f"✅ Канал {chat.title} успешно добавлен!\n\n"
            f"👥 Администраторы: {admin_names}\n\n"
            f"Используйте /moderate для начала модерации."
        )
        
    except Exception as e:
        logger.error(f"Error in addchannel: {str(e)}")
        await update.message.reply_text("❌ Ошибка при добавлении канала.")

async def process_support(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"user_{user_id}"
    
    support_text = (
        f"🆘 Новое обращение в поддержку\n\n"
        f"👤 От: @{username} (ID: {user_id})\n"
        f"💬 Сообщение: {message}\n\n"
        f"📝 Ответить: /reply {user_id} ваш ответ"
    )
    
    try:
        await context.bot.send_message(SUPPORT_ADMIN_ID, support_text)
        await update.message.reply_text(
            "✅ Ваше обращение отправлено в техподдержку!\n"
            "Мы ответим вам в ближайшее время."
        )
    except Exception as e:
        logger.error(f"Error sending support message: {e}")
        await update.message.reply_text(
            "❌ Ошибка отправки сообщения в поддержку.\n"
            "Попробуйте позже или обратитесь напрямую: @crimbr6"
        )

async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_channel_admin(update.effective_user.id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам каналов.")
        return
    
    user_channels = get_user_channels(update.effective_user.id)
    
    if not user_channels:
        await update.message.reply_text("📋 Вы не являетесь администратором ни одного канала.")
        return
    
    response = "📋 Ваши каналы:\n\n"
    for ch_id in user_channels:
        try:
            chat = await context.bot.get_chat(ch_id)
            pending_count = len(get_pending_posts(ch_id))
            response += f"• {chat.title} ({pending_count} в очереди)\n"
        except:
            response += f"• {ch_id}\n"
    
    await update.message.reply_text(response)

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_support'] = True
    await update.message.reply_text(
        "🛠️ Техническая поддержка\n\n"
        "Напишите ваш вопрос:"
    )
    return

async def process_support(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"user_{user_id}"


async def reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPPORT_ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    context.user_data['awaiting_reply_user'] = True
    await update.message.reply_text("👤 Введите ID пользователя:")
    return

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_channel_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    if len(context.args) == 0:
        keyboard = []
        for ch_id in user_channels:
            try:
                chat = await context.bot.get_chat(ch_id)
                channel_name = chat.title
            except:
                channel_name = ch_id
            short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
            keyboard.append([InlineKeyboardButton(f"⚙️ {channel_name}", callback_data=f"set_{short_channel_id}")])
        
        context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⚙️ Выберите канал для настройки:", reply_markup=reply_markup)
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Использование: /settings <channel_id> <настройка> <значение>")
        return

async def queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_channel_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    response = "📅 Запланированные посты:\n\n"
    has_posts = False
    
    for ch_id in user_channels:
        scheduled = get_scheduled_posts(ch_id)
        if scheduled:
            has_posts = True
            try:
                chat = await context.bot.get_chat(ch_id)
                response += f"📢 {chat.title}:\n"
            except:
                response += f"📢 {ch_id}:\n"
            
            for post in scheduled:
                post_id, _, _, username, _, _, scheduled_time = post
                response += f"  • От @{username} → {scheduled_time.strftime('%H:%M %d.%m')}\n"
    
    if not has_posts:
        response += "✅ Нет запланированных постов"
    
    await update.message.reply_text(response)

async def audit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_channel_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    keyboard = []
    for ch_id in user_channels:
        try:
            chat = await context.bot.get_chat(ch_id)
            channel_name = chat.title
        except:
            channel_name = ch_id
        short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
        keyboard.append([InlineKeyboardButton(f"📊 {channel_name}", callback_data=f"aud_{short_channel_id}")])
    
    context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Выберите канал для просмотра истории:", reply_markup=reply_markup)

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Эта команда доступна только администраторам.")
        return
    
    # Показываем список каналов для выбора
    keyboard = []
    for ch_id in user_channels:
        try:
            chat = await context.bot.get_chat(ch_id)
            channel_name = chat.title
        except:
            channel_name = ch_id
        
        short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel_name}",
            callback_data=f"ubc_{short_channel_id}"
        )])
    
    context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🚫 Выберите канал для разблокировки пользователей:", reply_markup=reply_markup)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Глобальная статистика для админа
    if user_id == SUPPORT_ADMIN_ID:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM channels")
            total_channels = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM channel_admins")
            total_admins = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM pending_posts")
            total_pending = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM banned_users")
            total_banned = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'published'")
            total_published = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM audit_log WHERE action = 'rejected'")
            total_rejected = cur.fetchone()[0]
            
            cur.close()
            conn.close()
            
            await update.message.reply_text(
                f"📊 Глобальная статистика бота:\n\n"
                f"📢 Каналов: {total_channels}\n"
                f"👥 Администраторов: {total_admins}\n"
                f"📤 Мемов предложено: {total_published + total_rejected + total_pending}\n"
                f"✅ Опубликовано: {total_published}\n"
                f"❌ Отклонено: {total_rejected}\n"
                f"⏳ В очереди: {total_pending}\n"
                f"🚫 Забанено: {total_banned}"
            )
            return
        except Exception as e:
            logger.error(f"Error in global stats: {e}")
    
    # Статистика для обычного админа
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        placeholders = ','.join(['%s'] * len(user_channels))
        cur.execute(f"SELECT COUNT(*) FROM pending_posts WHERE channel_id IN ({placeholders})", user_channels)
        pending_count = cur.fetchone()[0]
        
        cur.execute(f"SELECT COUNT(*) FROM banned_users WHERE channel_id IN ({placeholders})", user_channels)
        banned_count = cur.fetchone()[0]
        
        cur.execute(f"SELECT COUNT(*) FROM audit_log WHERE channel_id IN ({placeholders}) AND action = 'published'", user_channels)
        published_count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        await update.message.reply_text(
            f"📊 Статистика ваших каналов:\n\n"
            f"📢 Каналов: {len(user_channels)}\n"
            f"✅ Опубликовано: {published_count}\n"
            f"⏳ В очереди: {pending_count}\n"
            f"🚫 Забанено: {banned_count}"
        )
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        leaders = get_global_leaderboard(10)
        
        if not leaders:
            await update.message.reply_text("🏆 Таблица лидеров пуста. Пока никто не опубликовал мемы!")
            return
        
        response = "🏆 Глобальная таблица лидеров\n\n"
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, (user_id, username, posts, reactions) in enumerate(leaders, 1):
            medal = medals[idx-1] if idx <= 3 else f"{idx}."
            rank = get_user_rank(posts)
            response += f"{medal} @{username} {rank}\n"
            response += f"   📊 Мемов: {posts} | 👍 Реакций: {reactions}\n\n"
        
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error in leaderboard: {e}")
        await update.message.reply_text("❌ Ошибка получения таблицы лидеров.")

async def topchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_channels = get_user_channels(user_id)
    
    if not user_channels:
        await update.message.reply_text("❌ Вы не являетесь администратором ни одного канала.")
        return
    
    keyboard = []
    for ch_id in user_channels:
        try:
            chat = await context.bot.get_chat(ch_id)
            channel_name = chat.title
        except:
            channel_name = ch_id
        
        short_channel_id = hashlib.sha256(ch_id.encode()).hexdigest()[:8]
        keyboard.append([InlineKeyboardButton(
            f"🏆 {channel_name}",
            callback_data=f"top_{short_channel_id}"
        )])
    
    context.user_data['channel_mapping'] = {hashlib.sha256(ch[0].encode()).hexdigest()[:8]: ch[0] for ch in [(ch,) for ch in user_channels]}
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏆 Выберите канал для просмотра таблицы лидеров:", reply_markup=reply_markup)

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM published_posts WHERE user_id = %s", (user_id,))
        published = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM audit_log WHERE user_id = %s AND action = 'rejected'", (user_id,))
        rejected = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM pending_posts WHERE user_id = %s", (user_id,))
        pending = cur.fetchone()[0]
        
        cur.execute("SELECT COALESCE(SUM(reactions), 0) FROM published_posts WHERE user_id = %s", (user_id,))
        total_reactions = cur.fetchone()[0]
        
        balance, total_earned = get_user_balance(user_id)
        current_streak, longest_streak = get_streak(user_id)
        
        total_sent = published + rejected + pending
        approval_rate = (published / total_sent * 100) if total_sent > 0 else 0
        
        leaders = get_global_leaderboard(100)
        position = None
        for idx, (uid, uname, posts, reactions) in enumerate(leaders, 1):
            if uid == user_id:
                position = idx
                break
        
        cur.close()
        conn.close()
        
        rank = get_user_rank(published)
        sub = has_active_subscription(user_id)
        sub_badge = ""
        if sub == 'vip':
            sub_badge = " 👑"
        elif sub == 'pro':
            sub_badge = " ⭐"
        elif sub == 'basic':
            sub_badge = " 🌟"
        
        response = f"📊 Статистика @{username}{sub_badge}\n\n"
        response += f"{rank} | Мемов: {published}\n"
        response += f"💰 Мемкоины: {balance}\n"
        response += f"🔥 Стрик: {current_streak} дней (рекорд: {longest_streak})\n\n"
        response += f"📤 Отправлено: {total_sent}\n"
        response += f"✅ Опубликовано: {published}\n"
        response += f"❌ Отклонено: {rejected}\n"
        response += f"⏳ На модерации: {pending}\n"
        response += f"💯 Одобрение: {approval_rate:.1f}%\n"
        response += f"👍 Реакций: {total_reactions}\n\n"
        
        if position:
            response += f"🏆 Позиция: #{position}"
        else:
            response += "🏆 Позиция: не в топ-100"
        
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error in mystats: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики.")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    try:
        balance, total_earned = get_user_balance(user_id)
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT amount, reason, created_at FROM coin_transactions WHERE user_id = %s ORDER BY created_at DESC LIMIT 10", (user_id,))
        transactions = cur.fetchall()
        
        # Проверяем подписку
        cur.execute("SELECT subscription_type, expires_at, created_at FROM user_subscriptions WHERE user_id = %s AND expires_at > NOW()", (user_id,))
        sub_info = cur.fetchone()
        cur.close()
        conn.close()
        
        response = f"💰 Баланс @{username}\n\n"
        response += f"💵 Текущий баланс: {balance} монет\n"
        response += f"📈 Всего заработано: {total_earned} монет\n\n"
        
        keyboard = []
        if sub_info:
            sub_type, expires_at, created_at = sub_info
            from datetime import datetime, timedelta
            days_left = (expires_at - datetime.now()).days
            response += f"💎 Подписка: {sub_type.upper()}\n"
            response += f"⏰ Осталось: {days_left} дней\n\n"
            
            # Можно вернуть только в первый день
            if (datetime.now() - created_at) < timedelta(days=1):
                keyboard.append([InlineKeyboardButton("🔙 Вернуть подписку (-50%)", callback_data="refund_sub")])
        
        if transactions:
            response += "📜 Последние транзакции:\n"
            for amount, reason, created_at in transactions:
                sign = "+" if amount > 0 else ""
                response += f"{sign}{amount} - {reason} ({created_at.strftime('%d.%m %H:%M')})\n"
        else:
            response += "📜 Транзакций пока нет"
        
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, reply_markup=reply_markup)
        else:
            await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Error in balance: {e}")
        await update.message.reply_text("❌ Ошибка получения баланса.")

async def quests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    check_daily_quests(user_id, username)
    quests = get_daily_quests(user_id)
    
    response = "📋 Ежедневные задания:\n\n"
    
    quest_names = {
        'post_1': '📤 Отправить 1 мем',
        'post_3': '📤 Отправить 3 мема',
        'post_5': '📤 Отправить 5 мемов',
        'streak_3': '🔥 Стрик 3 дня',
        'open_lootbox': '🎁 Открыть лутбокс'
    }
    
    for quest_type, completed, reward in quests:
        status = "✅" if completed else "⏳"
        name = quest_names.get(quest_type, quest_type)
        response += f"{status} {name} (+{reward} монет)\n"
    
    if not quests:
        response += "Заданий пока нет. Отправьте мем!"
    
    await update.message.reply_text(response)

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance, _ = get_user_balance(user_id)
    sub = has_active_subscription(user_id)
    
    keyboard = [
        [InlineKeyboardButton("📦 Одноразовые товары", callback_data="shop_items")],
        [InlineKeyboardButton("💎 Подписки Premium", callback_data="shop_subs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    sub_text = f"\n💎 Активна: {sub}" if sub else ""
    
    await update.message.reply_text(
        f"🛒 Магазин\n\n"
        f"💰 Баланс: {balance} монет{sub_text}\n\n"
        f"Выберите категорию:",
        reply_markup=reply_markup
    )

async def weekwinner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import date, timedelta
    conn = get_db_connection()
    cur = conn.cursor()
    
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    
    cur.execute(
        "SELECT user_id, username, COUNT(*) as posts, COALESCE(SUM(reactions), 0) as reactions "
        "FROM published_posts WHERE DATE(published_at) >= %s "
        "GROUP BY user_id, username ORDER BY reactions DESC LIMIT 1",
        (week_start,)
    )
    winner = cur.fetchone()
    cur.close()
    conn.close()
    
    if not winner:
        await update.message.reply_text("⭐ Мем недели еще не определен!")
        return
    
    user_id, username, posts, reactions = winner
    rank = get_user_rank(posts)
    
    await update.message.reply_text(
        f"⭐ Мем недели\n\n"
        f"🏆 Победитель: @{username}\n"
        f"{rank}\n"
        f"📊 Мемов: {posts}\n"
        f"👍 Реакций: {reactions}\n\n"
        f"Новый победитель будет объявлен в понедельник!"
    )

async def updatemenu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPPORT_ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    try:
        commands = [
            BotCommand("start", "Начать работу с ботом"),
            BotCommand("mystats", "Моя статистика"),
            BotCommand("balance", "Мой баланс мемкоинов"),
            BotCommand("quests", "Ежедневные задания"),
            BotCommand("shop", "Магазин привилегий"),
            BotCommand("lootbox", "Открыть лутбокс"),
            BotCommand("referral", "Реферальная программа"),
            BotCommand("pay", "Перевести мемкоины"),
            BotCommand("weekwinner", "Мем недели"),
            BotCommand("leaderboard", "Таблица лидеров"),
            BotCommand("admin", "Панель администратора"),
            BotCommand("support", "Техподдержка")
        ]
        await context.bot.set_my_commands(commands)
        await update.message.reply_text("✅ Меню команд обновлено!\n\nПерезапустите Telegram или отправьте /start для применения изменений.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def manual_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPPORT_ADMIN_ID:
        return
    
    context.user_data['awaiting_update_msgid'] = True
    await update.message.reply_text("📝 Введите ID сообщения:")
    return

async def process_update(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int, reactions: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE published_posts SET reactions = %s WHERE message_id = %s", (reactions, message_id))
    rows = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    
    if rows > 0:
        await update.message.reply_text(f"✅ Обновлено! Пост {message_id}: {reactions} реакций")
    else:
        await update.message.reply_text(f"❌ Пост с ID {message_id} не найден в БД")

# ФАЗА 4: Функции автоматизации
def auto_moderate_content(photo_hash: str, file_size: int, caption: str, user_id: int, conn):
    result = {'approved': True, 'confidence': 100, 'issues': [], 'warnings': []}
    spam_keywords = ['реклама', 'заработок', 'казино', 'ставки', 'кредит', 'займ']
    caption_lower = sanitize_caption(caption).lower()
    if any(keyword in caption_lower for keyword in spam_keywords):
        result['approved'] = False
        result['issues'].append('Обнаружен спам')
    return result

def get_channel_analytics(channel_id: str, conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pending_posts WHERE channel_id = %s", (channel_id,))
    queue_size = cur.fetchone()[0]
    cur.close()
    return {'queue_size': queue_size}

def calculate_smart_schedule(channel_id: str, conn, aggressiveness: str = 'medium'):
    from datetime import datetime, timedelta
    analytics = get_channel_analytics(channel_id, conn)
    now = datetime.now()
    base_intervals = {'conservative': 180, 'medium': 90, 'aggressive': 45}
    base_interval = base_intervals.get(aggressiveness, 90)
    if analytics['queue_size'] > 10:
        base_interval = max(30, base_interval - 20)
    elif analytics['queue_size'] < 3:
        base_interval += 30
    next_time = now + timedelta(minutes=base_interval)
    if 1 <= next_time.hour < 7:
        next_time = next_time.replace(hour=9, minute=0)
        if next_time < now:
            next_time += timedelta(days=1)
    return next_time

def get_approval_rate(channel_id: str, conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audit_log WHERE channel_id = %s AND action = 'published'", (channel_id,))
    published = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM audit_log WHERE channel_id = %s AND action = 'rejected'", (channel_id,))
    rejected = cur.fetchone()[0]
    cur.close()
    total = published + rejected
    rate = (published / total * 100) if total > 0 else 0
    return {'published': published, 'rejected': rejected, 'total': total, 'rate': rate}

def get_top_authors(channel_id: str, conn, limit: int = 10):
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, COUNT(*) as posts FROM published_posts WHERE channel_id = %s GROUP BY user_id, username ORDER BY posts DESC LIMIT %s", (channel_id, limit))
    result = cur.fetchall()
    cur.close()
    return result

def get_growth_stats(channel_id: str, conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM published_posts WHERE channel_id = %s AND published_at > NOW() - INTERVAL '7 days'", (channel_id,))
    posts_week = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM published_posts WHERE channel_id = %s AND published_at BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days'", (channel_id,))
    posts_prev_week = cur.fetchone()[0]
    cur.close()
    posts_growth = ((posts_week - posts_prev_week) / posts_prev_week * 100) if posts_prev_week > 0 else 0
    return {'posts_week': posts_week, 'posts_prev_week': posts_prev_week, 'posts_growth': posts_growth}

async def lootbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import random
    from datetime import date, timedelta
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Проверяем подписку для бонусных лутбоксов
    sub = has_active_subscription(user_id)
    today = date.today()
    
    # Добавляем бонусные лутбоксы от подписки
    if sub == 'vip':
        cur.execute("SELECT last_bonus_date FROM user_subscriptions WHERE user_id = %s", (user_id,))
        last_bonus = cur.fetchone()
        if not last_bonus or last_bonus[0] != today:
            cur.execute("INSERT INTO lootboxes (user_id, username, box_type) VALUES (%s, %s, 'vip_daily')", (user_id, username))
            cur.execute("UPDATE user_subscriptions SET last_bonus_date = %s WHERE user_id = %s", (today, user_id))
            conn.commit()
    elif sub in ['pro', 'basic']:
        cur.execute("SELECT last_bonus_date FROM user_subscriptions WHERE user_id = %s", (user_id,))
        last_bonus = cur.fetchone()
        week_start = today - timedelta(days=today.weekday())
        if not last_bonus or last_bonus[0] < week_start:
            boxes = 2 if sub == 'pro' else 1
            for _ in range(boxes):
                cur.execute("INSERT INTO lootboxes (user_id, username, box_type) VALUES (%s, %s, %s)", (user_id, username, f'{sub}_weekly'))
            cur.execute("UPDATE user_subscriptions SET last_bonus_date = %s WHERE user_id = %s", (today, user_id))
            conn.commit()
    
    cur.execute("SELECT COUNT(*) FROM published_posts WHERE user_id = %s", (user_id,))
    posts = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM lootboxes WHERE user_id = %s AND opened = FALSE", (user_id,))
    available = cur.fetchone()[0]
    earned = posts // 10
    cur.execute("SELECT COUNT(*) FROM lootboxes WHERE user_id = %s", (user_id,))
    total = cur.fetchone()[0]
    if earned > total:
        for _ in range(earned - total):
            cur.execute("INSERT INTO lootboxes (user_id, username, box_type) VALUES (%s, %s, 'standard')", (user_id, username))
        conn.commit()
        available = earned - total
    if available == 0:
        await update.message.reply_text(f"📦 Нет лутбоксов!\n\nОпубликуйте {10 - (posts % 10)} мемов для следующего.")
        cur.close()
        conn.close()
        return
    cur.execute("SELECT id FROM lootboxes WHERE user_id = %s AND opened = FALSE LIMIT 1", (user_id,))
    box_id = cur.fetchone()[0]
    roll = random.random()
    reward = 500 if roll < 0.01 else 200 if roll < 0.10 else random.randint(20, 100)
    cur.execute("INSERT INTO lootbox_rewards (lootbox_id, reward_type, reward_value) VALUES (%s, 'coins', %s)", (box_id, reward))
    cur.execute("UPDATE lootboxes SET opened = TRUE WHERE id = %s", (box_id,))
    conn.commit()
    add_coins(user_id, username, reward, "🎁 Лутбокс")
    
    cur.execute("SELECT completed FROM daily_quests WHERE user_id = %s AND quest_date = %s AND quest_type = 'open_lootbox'", (user_id, today))
    quest_result = cur.fetchone()
    if quest_result and not quest_result[0]:
        cur.execute("UPDATE daily_quests SET completed = TRUE, completed_at = CURRENT_TIMESTAMP WHERE user_id = %s AND quest_date = %s AND quest_type = 'open_lootbox'", (user_id, today))
        add_coins(user_id, username, 20, "✅ Задание: Открыть лутбокс")
        conn.commit()
    
    cur.close()
    conn.close()
    await update.message.reply_text(f"🎁 Лутбокс открыт!\n\n💰 +{reward} монет\n📦 Осталось: {available - 1}")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    user_id = update.effective_user.id
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT code FROM referral_codes WHERE user_id = %s", (user_id,))
    result = cur.fetchone()
    if not result:
        code = hashlib.sha256(f"{user_id}{datetime.now()}".encode()).hexdigest()[:8]
        cur.execute("INSERT INTO referral_codes (user_id, code) VALUES (%s, %s)", (user_id, code))
        conn.commit()
    else:
        code = result[0]
    cur.execute("SELECT total_referrals FROM referral_codes WHERE user_id = %s", (user_id,))
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = %s AND reward_claimed = TRUE", (user_id,))
    rewarded = cur.fetchone()[0]
    cur.close()
    conn.close()
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{code}"
    await update.message.reply_text(f"🎁 Реферальная программа\n\n👥 Приглашено: {total}\n💰 Награды: {rewarded}\n\n🔗 Ваша ссылка:\n{link}\n\n💵 +100 монет за друга\n💵 +50 когда друг опубликует 5 мемов")

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    context.user_data['awaiting_pay_recipient'] = True
    await update.message.reply_text(
        "💸 Перевод мемкоинов\n\n"
        "Введите @username или ID получателя:"
    )
    return
    
    try:
        recipient = context.args[0]
        amount = int(context.args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной!")
            return
        
        recipient_id = None
        recipient_username = None
        
        if recipient.startswith('@'):
            recipient_username = recipient[1:]
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM user_coins WHERE username = %s", (recipient_username,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            if result:
                recipient_id = result[0]
            else:
                await update.message.reply_text(f"❌ Пользователь {recipient} не найден в системе.")
                return
        else:
            recipient_id = int(recipient)
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT username FROM user_coins WHERE user_id = %s", (recipient_id,))
            result = cur.fetchone()
            cur.close()
            conn.close()
            if result:
                recipient_username = result[0]
            else:
                recipient_username = f"user_{recipient_id}"
        
        if recipient_id == user_id and user_id != SUPPORT_ADMIN_ID:
            await update.message.reply_text("❌ Нельзя переводить монеты самому себе!")
            return
        
        if transfer_coins(user_id, recipient_id, amount, username, recipient_username):
            await update.message.reply_text(f"✅ Переведено {amount} монет пользователю @{recipient_username}")
            try:
                await context.bot.send_message(
                    chat_id=recipient_id,
                    text=f"💰 Вы получили {amount} мемкоинов от @{username}!"
                )
            except:
                pass
        else:
            await update.message.reply_text("❌ Недостаточно монет для перевода!")
    
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Сумма должна быть числом.")
    except Exception as e:
        logger.error(f"Error in pay command: {e}")
        await update.message.reply_text("❌ Ошибка при переводе монет.")

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_channel_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только администраторам каналов.")
        return
    
    keyboard = [
        [InlineKeyboardButton("🛡️ Модерация", callback_data="adm_moderate")],
        [InlineKeyboardButton("➕ Добавить канал", callback_data="adm_addchannel")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="adm_settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton("📝 Очередь", callback_data="adm_queue")],
        [InlineKeyboardButton("📊 История", callback_data="adm_audit")],
        [InlineKeyboardButton("🚫 Разбан", callback_data="adm_unban")],
        [InlineKeyboardButton("📢 Каналы", callback_data="adm_channels")],
        [InlineKeyboardButton("🏆 Топ канала", callback_data="adm_topchannel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛡️ Панель администратора\n\nВыберите действие:",
        reply_markup=reply_markup
    )

async def post_init(application: Application):
    # Создаем таблицу для очереди постов
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_posts (
                id SERIAL PRIMARY KEY,
                channel_id VARCHAR(255),
                user_id BIGINT,
                username VARCHAR(255),
                photo_file_id VARCHAR(255),
                caption TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT,
                channel_id VARCHAR(255),
                username VARCHAR(255),
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                banned_by BIGINT,
                PRIMARY KEY (user_id, channel_id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id VARCHAR(255) PRIMARY KEY,
                added_by BIGINT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_admins (
                channel_id VARCHAR(255),
                user_id BIGINT,
                username VARCHAR(255),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_settings (
                channel_id VARCHAR(255) PRIMARY KEY,
                post_interval_minutes INTEGER DEFAULT 0,
                max_posts_per_day INTEGER DEFAULT 0,
                require_caption BOOLEAN DEFAULT FALSE,
                allowed_media_types VARCHAR(255) DEFAULT 'photo,video',
                spam_filter_enabled BOOLEAN DEFAULT TRUE,
                allow_global_posts BOOLEAN DEFAULT TRUE,
                last_post_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id SERIAL PRIMARY KEY,
                channel_id VARCHAR(255),
                user_id BIGINT,
                username VARCHAR(255),
                photo_file_id VARCHAR(255),
                caption TEXT,
                scheduled_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id SERIAL PRIMARY KEY,
                channel_id VARCHAR(255),
                action VARCHAR(50),
                user_id BIGINT,
                admin_id BIGINT,
                post_id INTEGER,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS published_posts (
                id SERIAL PRIMARY KEY,
                channel_id VARCHAR(255),
                user_id BIGINT,
                username VARCHAR(255),
                message_id BIGINT,
                reactions INTEGER DEFAULT 0,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_coins (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                balance INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                amount INTEGER,
                reason VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON coin_transactions(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_published_posts_user ON published_posts(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_published_posts_channel ON published_posts(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pending_posts_channel ON pending_posts(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_log_channel ON audit_log(channel_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_banned_users_user ON banned_users(user_id)")
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
    
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("mystats", "Моя статистика"),
        BotCommand("balance", "Мой баланс мемкоинов"),
        BotCommand("quests", "Ежедневные задания"),
        BotCommand("shop", "Магазин привилегий"),
        BotCommand("lootbox", "Открыть лутбокс"),
        BotCommand("referral", "Реферальная программа"),
        BotCommand("pay", "Перевести мемкоины"),
        BotCommand("weekwinner", "Мем недели"),
        BotCommand("leaderboard", "Таблица лидеров"),
        BotCommand("admin", "Панель администратора"),
        BotCommand("support", "Техподдержка")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Меню команд настроено!")

async def update_reactions(context: ContextTypes.DEFAULT_TYPE):
    """Обновляет количество реакций для последних 50 постов"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, channel_id, message_id FROM published_posts "
        "WHERE published_at > NOW() - INTERVAL '7 days' "
        "ORDER BY published_at DESC LIMIT 50"
    )
    posts = cur.fetchall()
    cur.close()
    conn.close()
    
    for post_id, channel_id, message_id in posts:
        try:
            msg = await context.bot.forward_message(
                chat_id=channel_id,
                from_chat_id=channel_id,
                message_id=message_id
            )
            # Telegram API не дает прямого доступа к реакциям через Bot API
            # Это заглушка для будущей реализации через MTProto
        except:
            pass

async def check_expired_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет и уведомляет об истекших подписках"""
    from datetime import datetime, timedelta
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, subscription_type FROM user_subscriptions WHERE expires_at <= %s AND expires_at > %s", (datetime.now(), datetime.now() - timedelta(hours=1)))
    expired = cur.fetchall()
    cur.close()
    conn.close()
    
    for user_id, sub_type in expired:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ Ваша подписка {sub_type.upper()} истекла!\n\nПродлите в /shop"
            )
        except:
            pass

async def publish_scheduled_posts(context: ContextTypes.DEFAULT_TYPE):
    from datetime import datetime
    now = datetime.now()
    scheduled = get_scheduled_posts()
    logger.info(f"[SCHEDULER] Current time: {now}, Checking scheduled posts: {len(scheduled)} found")
    
    for post in scheduled:
        post_id, channel_id, user_id, username, photo_file_id, caption, scheduled_time = post
        logger.info(f"[SCHEDULER] Post {post_id}: scheduled for {scheduled_time}, current time {now}")
        
        if scheduled_time > now:
            logger.info(f"[SCHEDULER] Post {post_id} not ready yet (scheduled: {scheduled_time}, now: {now})")
            break
            
        logger.info(f"[SCHEDULER] Publishing post {post_id} to channel {channel_id}")
        try:
            msg = await context.bot.send_photo(
                chat_id=channel_id,
                photo=photo_file_id,
                caption=caption if caption else None
            )
            add_published_post(channel_id, user_id, username, msg.message_id)
            # Применяем бонусы подписки
            sub = has_active_subscription(user_id)
            coin_bonus = 10
            if sub == 'vip':
                coin_bonus = int(10 * 3)
            elif sub == 'pro':
                coin_bonus = int(10 * 1.5)
            elif sub == 'basic':
                coin_bonus = int(10 * 1.2)
            
            add_coins(user_id, username, coin_bonus, "Мем опубликован")
            update_streak(user_id, username)
            check_daily_quests(user_id, username)
            
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM published_posts WHERE user_id = %s", (user_id,))
            posts_count = cur.fetchone()[0]
            cur.close()
            conn.close()
            
            achievements = check_and_award_achievements(user_id, username, posts_count)
            rank = get_user_rank(posts_count)
            
            update_channel_setting(channel_id, 'last_post_time', datetime.now())
            remove_scheduled_post(post_id)
            log_action(channel_id, 'auto_published', user_id, 0, post_id, 'Published by scheduler')
            logger.info(f"[SCHEDULER] Successfully published post {post_id}")
            
            try:
                notif = f"🎉 Ваш контент опубликован!\n💰 +10 мемкоинов\n{rank} | Мемов: {posts_count}"
                if achievements:
                    notif += "\n\n🏆 " + "\n🏆 ".join(achievements)
                await context.bot.send_message(chat_id=user_id, text=notif)
            except:
                pass
            
            break
        except Exception as e:
            logger.error(f"[SCHEDULER] Error publishing post {post_id}: {e}")

async def health(request):
    return web.Response(text="OK")

async def start_bot():
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    if application.job_queue:
        application.job_queue.run_repeating(publish_scheduled_posts, interval=60, first=10)
        application.job_queue.run_repeating(check_expired_subscriptions, interval=3600, first=60)
    else:
        logger.warning("JobQueue не доступен. Установите: pip install python-telegram-bot[job-queue]")
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mystats", mystats))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("quests", quests))
    application.add_handler(CommandHandler("shop", shop))
    application.add_handler(CommandHandler("lootbox", lootbox))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(CommandHandler("pay", pay))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("weekwinner", weekwinner))
    application.add_handler(CommandHandler("moderate", moderate))
    application.add_handler(CommandHandler("addchannel", addchannel))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("queue", queue))
    application.add_handler(CommandHandler("audit", audit))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("channels", channels))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("topchannel", topchannel))
    application.add_handler(CommandHandler("update", manual_update))
    application.add_handler(CommandHandler("updatemenu", updatemenu))
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("reply", reply_support))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("Бот запущен!")
    return application

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    app = web.Application()
    app.router.add_get('/', health)
    app.router.add_get('/health', health)
    
    async def start_services(app):
        app['bot'] = await start_bot()
    
    async def cleanup(app):
        if 'bot' in app:
            await app['bot'].updater.stop()
            await app['bot'].stop()
            await app['bot'].shutdown()
    
    app.on_startup.append(start_services)
    app.on_cleanup.append(cleanup)
    
    port = int(os.getenv('PORT', 10000))
    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()