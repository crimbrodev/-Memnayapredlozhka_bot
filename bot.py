import os
import logging
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError

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
SUPPORT_ADMIN_ID = 6895683980

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

def add_pending_post(channel_id: str, user_id: int, username: str, photo_file_id: str, caption: str = ""):
    conn = get_db_connection()
    cur = conn.cursor()
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
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"INSERT INTO channel_settings (channel_id, {setting}) VALUES (%s, %s) ON CONFLICT (channel_id) DO UPDATE SET {setting} = %s", (channel_id, value, value))
    conn.commit()
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
        
        short_channel_id = str(hash(ch_id))[-8:]
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel_name} ({pending_count} постов)", 
            callback_data=f"mod_{short_channel_id}"
        )])
    
    # Сохраняем соответствие для админа
    context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in [(ch,) for ch in user_channels]}
    
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
    
    short_channel_id = str(hash(channel_id))[-8:]
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
        await query.edit_message_media(
            media={"type": "photo", "media": photo_file_id, "caption": caption_text},
            reply_markup=reply_markup
        )
    except:
        await query.edit_message_text(caption_text, reply_markup=reply_markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not update.message.photo:
        return
    
    channels = get_channels_with_names()
    
    if not channels:
        await update.message.reply_text(
            "⚠️ Пока не настроено ни одного канала.\n"
            "Попросите администратора добавить канал командой /addchannel"
        )
        return
    
    photo = update.message.photo[-1]
    caption = update.message.caption or ""
    
    if check_spam(caption):
        await update.message.reply_text("⚠️ Обнаружен подозрительный контент. Пожалуйста, не отправляйте рекламу.")
        return
    
    context.user_data['photo_file_id'] = photo.file_id
    context.user_data['photo_caption'] = caption
    context.user_data['waiting_for_channel'] = True
    
    keyboard = [
        [InlineKeyboardButton("🌐 Отправить во все каналы", callback_data=f"all_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📤 Напишите название или @username канала, в который хотите отправить контент:\n\n"
        "Или нажмите кнопку ниже, чтобы отправить во все каналы сразу:",
        reply_markup=reply_markup
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        # Найден только один канал - добавляем в очередь сразу
        channel_id, channel_name, channel_username = matched_channels[0]
        
        if is_user_banned(user_id, channel_id):
            await update.message.reply_text(f"❌ Вы заблокированы в канале '{channel_name}'.")
            context.user_data['waiting_for_channel'] = False
            return
        
        add_pending_post(channel_id, user_id, username, photo_file_id, caption)
        
        context.user_data['waiting_for_channel'] = False
        
        await update.message.reply_text(
            f"✅ Ваш контент добавлен в очередь модерации канала '{channel_name}'!"
        )
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
                callback_data=f"sel_{user_id}_{short_channel_id}"
            )])
        
        # Сохраняем соответствие короткого ID и полного
        context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in matched_channels}
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔍 Найдено {len(matched_channels)} канал(ов) с похожим названием.\nВыберите канал:",
            reply_markup=reply_markup
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data_parts = query.data.split("_")
    action = data_parts[0]
    
    if action == "all":
        user_id = int(data_parts[1])
        
        if query.from_user.id != user_id:
            await query.edit_message_text("❌ Это не ваш контент!")
            return
        
        photo_file_id = context.user_data.get('photo_file_id')
        caption = context.user_data.get('photo_caption', '')
        username = query.from_user.username or query.from_user.first_name
        
        channels = get_channels_with_names()
        added_count = 0
        skipped_count = 0
        
        for channel in channels:
            channel_id = channel[0]
            settings = get_channel_settings(channel_id)
            
            if not settings.get('allow_global', True):
                skipped_count += 1
                continue
            
            if is_user_banned(user_id, channel_id):
                skipped_count += 1
                continue
            
            add_pending_post(channel_id, user_id, username, photo_file_id, caption)
            added_count += 1
        
        context.user_data['waiting_for_channel'] = False
        
        await query.edit_message_text(
            f"✅ Ваш контент добавлен в очередь модерации!\n\n"
            f"📢 Отправлено в {added_count} канал(ов)\n"
            f"⏭️ Пропущено: {skipped_count}"
        )
    
    elif action == "sel":
        # Пользователь выбрал канал из списка похожих
        user_id = int(data_parts[1])
        short_channel_id = data_parts[2]
        
        if query.from_user.id != user_id:
            await query.edit_message_text("❌ Это не ваш контент!")
            return
        
        # Получаем полный ID канала
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
        
        if is_user_banned(user_id, channel_id):
            await query.edit_message_text(f"❌ Вы заблокированы в канале '{channel_name}'.")
            context.user_data['waiting_for_channel'] = False
            return
        
        # Добавляем пост в очередь
        photo_file_id = context.user_data.get('photo_file_id')
        caption = context.user_data.get('photo_caption', '')
        username = query.from_user.username or query.from_user.first_name
        
        add_pending_post(channel_id, user_id, username, photo_file_id, caption)
        
        # Очищаем состояние
        context.user_data['waiting_for_channel'] = False
        
        await query.edit_message_text(
            f"✅ Ваш контент добавлен в очередь модерации канала '{channel_name}'!"
        )
    
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
        keyboard = [
            [InlineKeyboardButton(f"⏱ Интервал: {settings['interval']} мин", callback_data=f"cfg_interval_{short_channel_id}")],
            [InlineKeyboardButton(f"📊 Лимит: {settings['max_posts']} постов/день", callback_data=f"cfg_limit_{short_channel_id}")],
            [InlineKeyboardButton(f"📝 Подпись: {'required' if settings['require_caption'] else 'optional'}", callback_data=f"cfg_caption_{short_channel_id}")],
            [InlineKeyboardButton(f"🚫 Спам-фильтр: {'ON' if settings['spam_filter'] else 'OFF'}", callback_data=f"cfg_spam_{short_channel_id}")],
            [InlineKeyboardButton(f"🌐 Общие мемы: {'ON' if settings.get('allow_global', True) else 'OFF'}", callback_data=f"cfg_global_{short_channel_id}")]
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
            response += f"{medal} @{username}\n"
            response += f"   📊 Мемов: {posts} | 👍 Реакций: {reactions}\n\n"
        
        await query.edit_message_text(response)
    
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
                
                msg = await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=photo_file_id,
                    caption=caption if caption else None
                )
                
                add_published_post(channel_id, user_id, username, msg.message_id)
                update_channel_setting(channel_id, 'last_post_time', datetime.now())
                remove_pending_post(post_id)
                log_action(channel_id, 'published', user_id, query.from_user.id, post_id)
                
                try:
                    chat = await context.bot.get_chat(channel_id)
                    channel_name = chat.title
                except:
                    channel_name = "канале"
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Ваш контент опубликован в {channel_name}!"
                )
                
                await show_next_post(query, context, channel_id)
                
            except Exception as e:
                logger.error(f"Ошибка публикации в {channel_id}: {str(e)}")
                await query.edit_message_caption(
                    caption=query.message.caption + "\n\n❌ ОШИБКА ПУБЛИКАЦИИ"
                )
        
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
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Использование: /addchannel <channel_id>\n\n"
            "Примеры:\n"
            "/addchannel @mychannel\n"
            "/addchannel -1001234567890\n\n"
            "📝 Убедитесь, что:\n"
            "1. Бот добавлен в канал как администратор\n"
            "2. У бота есть права на публикацию сообщений\n"
            "3. Вы сами являетесь администратором канала"
        )
        return
    
    channel_id = context.args[0]
    
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
    if not context.args:
        await update.message.reply_text(
            "🛠️ Техническая поддержка\n\n"
            "Напишите ваш вопрос после команды:\n"
            "/support ваш вопрос или проблема\n\n"
            "Пример:\n"
            "/support Не могу добавить канал, выдает ошибку"
        )
        return
    
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or f"user_{user_id}"
    message = " ".join(context.args)
    
    support_text = (
        f"🆘 Новое обращение в поддержку\n\n"
        f"👤 От: @{username} (ID: {user_id})\n"
        f"💬 Сообщение: {message}\n\n"
        f"📝 Ответить: /reply {user_id} ваш ответ"
    )
    
    try:
        await context.bot.send_message(
            chat_id=SUPPORT_ADMIN_ID,
            text=support_text
        )
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


    await update.message.reply_text(
        "🛠️ Техническая поддержка\n\n"
        "По всем вопросам обращайтесь к разработчику:\n"
        "👨‍💻 @crimbr6\n\n"
        "📝 При обращении укажите:\n"
        "• Описание проблемы\n"
        "• Ваш ID (если нужно)\n"
        "• Скриншот ошибки (если есть)"
    )

async def reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPPORT_ADMIN_ID:
        await update.message.reply_text("❌ Эта команда доступна только администратору.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Использование: /reply <user_id> <ответ>\n\n"
            "Пример:\n"
            "/reply 123456789 Проблема решена, попробуйте снова"
        )
        return
    
    try:
        user_id = int(context.args[0])
        reply_message = " ".join(context.args[1:])
        
        reply_text = (
            f"💬 Ответ от техподдержки:\n\n"
            f"{reply_message}"
        )
        
        await context.bot.send_message(
            chat_id=user_id,
            text=reply_text
        )
        
        await update.message.reply_text(
            f"✅ Ответ отправлен пользователю {user_id}"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя")
    except Exception as e:
        logger.error(f"Error sending reply: {e}")
        await update.message.reply_text("❌ Ошибка отправки ответа")

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
            short_channel_id = str(hash(ch_id))[-8:]
            keyboard.append([InlineKeyboardButton(f"⚙️ {channel_name}", callback_data=f"set_{short_channel_id}")])
        
        context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in [(ch,) for ch in user_channels]}
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
        short_channel_id = str(hash(ch_id))[-8:]
        keyboard.append([InlineKeyboardButton(f"📊 {channel_name}", callback_data=f"aud_{short_channel_id}")])
    
    context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in [(ch,) for ch in user_channels]}
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
        
        short_channel_id = str(hash(ch_id))[-8:]
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel_name}",
            callback_data=f"ubc_{short_channel_id}"
        )])
    
    context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in [(ch,) for ch in user_channels]}
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
            response += f"{medal} @{username}\n"
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
        
        short_channel_id = str(hash(ch_id))[-8:]
        keyboard.append([InlineKeyboardButton(
            f"🏆 {channel_name}",
            callback_data=f"top_{short_channel_id}"
        )])
    
    context.user_data['channel_mapping'] = {str(hash(ch[0]))[-8:]: ch[0] for ch in [(ch,) for ch in user_channels]}
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🏆 Выберите канал для просмотра таблицы лидеров:", reply_markup=reply_markup)

async def manual_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != SUPPORT_ADMIN_ID:
        return
    
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 Использование: /update <message_id> <reactions>\n\n"
            "Пример:\n"
            "/update 206 3\n\n"
            "Где 206 - ID сообщения, 3 - количество реакций"
        )
        return
    
    try:
        message_id = int(context.args[0])
        reactions = int(context.args[1])
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE published_posts SET reactions = %s WHERE message_id = %s",
            (reactions, message_id)
        )
        rows = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        
        if rows > 0:
            await update.message.reply_text(f"✅ Обновлено! Пост {message_id}: {reactions} реакций")
        else:
            await update.message.reply_text(f"❌ Пост с ID {message_id} не найден в БД")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте числа.")
    except Exception as e:
        logger.error(f"Error updating reactions: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
    
    commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("moderate", "Модерация постов"),
        BotCommand("addchannel", "Добавить канал"),
        BotCommand("settings", "Настройки канала"),
        BotCommand("queue", "Очередь постов"),
        BotCommand("audit", "История действий"),
        BotCommand("unban", "Разблокировать пользователя"),
        BotCommand("channels", "Список каналов"),
        BotCommand("stats", "Статистика"),
        BotCommand("leaderboard", "Глобальная таблица лидеров"),
        BotCommand("topchannel", "Таблица лидеров канала"),
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
            update_channel_setting(channel_id, 'last_post_time', datetime.now())
            remove_scheduled_post(post_id)
            log_action(channel_id, 'auto_published', user_id, 0, post_id, 'Published by scheduler')
            logger.info(f"[SCHEDULER] Successfully published post {post_id}")
            
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 Ваш контент опубликован!"
                )
            except:
                pass
            
            break
        except Exception as e:
            logger.error(f"[SCHEDULER] Error publishing post {post_id}: {e}")

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    if application.job_queue:
        application.job_queue.run_repeating(publish_scheduled_posts, interval=60, first=10)
        application.job_queue.run_repeating(update_reactions, interval=300, first=60)
    else:
        logger.warning("JobQueue не доступен. Установите: pip install python-telegram-bot[job-queue]")
    
    application.add_handler(CommandHandler("start", start))
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
    application.add_handler(CommandHandler("support", support))
    application.add_handler(CommandHandler("reply", reply_support))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()