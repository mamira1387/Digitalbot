import logging
import os
import re
import time
from datetime import datetime, timedelta
from telegram import Update, ForceReply, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
# Make sure you are using googletrans==4.0.0-rc1 in your requirements.txt
from googletrans import Translator 
import yt_dlp
from flask import Flask, request # Make sure 'Flask' is in your requirements.txt
from threading import Thread # Required for running Flask in a separate thread

# --- Database Setup ---
from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base

# Create a SQLite database engine. 'digitalbot.db' file will be created.
engine = create_engine('sqlite:///digitalbot.db')
Base = declarative_base() # Base class for our models
Session = sessionmaker(bind=engine) # Session factory

# Define models (database tables)
class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True) # Telegram User ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=True)
    
    total_messages = Column(Integer, default=0)
    daily_messages = Column(Integer, default=0)
    hourly_messages = Column(Integer, default=0)
    weekly_messages = Column(Integer, default=0)
    monthly_messages = Column(Integer, default=0)
    last_message_time = Column(DateTime, default=datetime.min)
    
    warnings = Column(Integer, default=0)
    is_special = Column(Boolean, default=False) # Special user
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', total_messages={self.total_messages})>"

class ChatSettings(Base):
    __tablename__ = 'chat_settings'
    chat_id = Column(BigInteger, primary_key=True)
    welcome_text = Column(Text, default="خوش آمدید به گروه {group_name}!")
    welcome_media_id = Column(String, nullable=True)
    welcome_media_type = Column(String, nullable=True) # 'photo', 'video'
    warning_limit = Column(Integer, default=5)
    
    def __repr__(self):
        return f"<ChatSettings(chat_id={self.chat_id})>"

class BotOwner(Base):
    __tablename__ = 'bot_owner'
    user_id = Column(BigInteger, primary_key=True) # Bot owner's User ID
    
    def __repr__(self):
        return f"<BotOwner(user_id={self.user_id})>"

# Create all tables in the database (if they don't exist)
Base.metadata.create_all(engine)

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Token ---
# It's highly recommended to load this from an environment variable
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN_HERE")

# --- Flask App for Render Health Check ---
# This new section solves the 'Port scan timeout' issue.
# Render needs a web server to confirm the service is alive.
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!", 200 # Message for Render that the service is alive

# --- Helper Functions for Database Interaction ---

def get_chat_settings_db(session, chat_id):
    """Retrieves or creates chat settings from the database."""
    settings = session.query(ChatSettings).filter_by(chat_id=chat_id).first()
    if not settings:
        settings = ChatSettings(chat_id=chat_id)
        session.add(settings)
        session.commit()
    return settings

def get_or_create_user_db(session, user_id, username, first_name, last_name):
    """Retrieves or creates a user from the database."""
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        session.add(user)
        session.commit()
    return user

def get_bot_owner_id_db(session):
    """Retrieves the bot owner's ID from the database."""
    owner = session.query(BotOwner).first()
    return owner.user_id if owner else None

def set_bot_owner_id_db(session, user_id):
    """Sets the bot owner's ID in the database."""
    session.query(BotOwner).delete() # Remove previous owner if exists
    owner = BotOwner(user_id=user_id)
    session.add(owner)
    session.commit()

async def is_admin_or_creator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is an administrator or creator in the chat."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        return False # No need to reply for private chat non-admin checks
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status in ["creator", "administrator"]:
            return True
        else:
            if update.message: 
                await update.message.reply_text("این دستور فقط برای ادمین‌ها و سازنده گروه قابل استفاده است.")
            return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        if update.message:
            await update.message.reply_text("خطایی در بررسی وضعیت ادمین رخ داد.")
        return False

async def is_group_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is the creator of the group."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status == "creator":
            return True
        else:
            if update.message:
                await update.message.reply_text("این دستور فقط برای سازنده گروه قابل استفاده است.")
            return False
    except Exception as e:
        logger.error(f"Error checking group owner status: {e}")
        if update.message:
            await update.message.reply_text("خطایی در بررسی وضعیت سازنده گروه رخ داد.")
        return False

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf'''سلام {user.mention_html()}! من DigitalBot هستم و **فعال** هستم. برای استفاده از قابلیت‌های من، می‌تونی از دستورات زیر استفاده کنی:
/help - راهنمای کامل
/translate <متن> - ترجمه متن به فارسی
/download <لینک> - دانلود محتوا از لینک
/myprofile - مشاهده آمار چت خودت
/stats - مشاهده آمار کلی گروه
''',
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(f"""
راهنمای استفاده از DigitalBot (سازنده: armanloyalguy):

**دستورات عمومی:**
/start : شروع کار با ربات و معرفی (نشون می‌ده که ربات فعاله).
/help : نمایش این راهنما.
/translate <متن> : متن مورد نظر شما رو به فارسی ترجمه می‌کنه.
/download <لینک> : لینک ویدیوی مورد نظر شما رو از سایت‌های پشتیبانی شده (یوتیوب، اینستاگرام، تیک‌تاک، پینترست و ...) دانلود می‌کنه.
/myprofile : آمار چت خودت رو نشون می‌ده.
/stats : آمار کلی چت گروه.

**قابلیت‌های گروه:**
- **مدیریت لینک:** لینک‌های اینستاگرام، یوتیوب، تیک‌تاک و پینترست رو دانلود می‌کنم. لینک‌های دیگه رو حذف می‌کنم.
- **ترجمه ریپلای:** با ریپلای روی یک پیام و نوشتن 'ترجمه'، اون پیام رو به فارسی ترجمه می‌کنم.
- **پیام خوشامدگویی:** به اعضای جدید خوشامد می‌گم.

**قابلیت‌های ادمین (فقط برای ادمین‌ها و سازنده گروه):**
- **پین کردن پیام:** روی پیامی ریپلای کن و بنویس 'پین'.
- **بن کردن کاربر:** روی پیامی از کاربر ریپلای کن و بنویس 'بن'.
- **رفع بن کردن کاربر:** روی پیامی حاوی آیدی عددی کاربر ریپلای کن و بنویس 'رفع بن'.
- **اخطار دادن:** روی پیامی از کاربر ریپلای کن و بنویس 'اخطار'. (پیش‌فرض 5 اخطار تا بن)
- **تنظیم حد اخطار:** روی پیامی ریپلای کن و بنویس 'تنظیم اخطار <عدد>'.
- **سکوت کاربر:** روی پیامی از کاربر ریپلای کن و بنویس 'سکوت <عدد به دقیقه>'.
- **ادمین کردن کاربر:** روی پیامی از کاربر ریپلای کن و بنویس 'ادمین'.
- **تنظیم پیام خوشامدگویی:**
    - برای تنظیم متن: روی پیامی ریپلای کن و بنویس 'تنظیم خوشامد متن'.
    - برای تنظیم تصویر/ویدیو: روی تصویر/ویدیوی مورد نظر ریپلای کن و بنویس 'تنظیم خوشامد رسانه'.

**قابلیت‌های مالک گروه (فقط برای سازنده گروه یا مالک ربات):**
- **کاربر ویژه:** روی پیامی از کاربر ریپلای کن و بنویس 'کاربر ویژه'. (کاربر ویژه می‌تونه لینک بده)
- **مالک ربات:** روی پیامی از کاربر ریپلای کن و بنویس 'مالک ربات'. (کاربر قابلیت‌های مالک گروه رو می‌گیره)
""")

async def translate_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translates text to Farsi."""
    if not context.args:
        await update.message.reply_text("لطفاً متنی برای ترجمه بعد از /translate وارد کنید. مثال: /translate hello world")
        return

    text_to_translate = " ".join(context.args)
    translator = Translator()
    try:
        translated = translator.translate(text_to_translate, dest='fa')
        await update.message.reply_text(f"ترجمه: {translated.text}")
    except Exception as e:
        logger.error(f"Translation error: {e}")
        await update.message.reply_text("متاسفانه در حال حاضر امکان ترجمه وجود نداره. لطفاً بعداً امتحان کنید.")
        # --- Download Handler & Link Management ---

async def _perform_download(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """Helper function to perform the actual download using yt-dlp."""
    instagram_cookies = os.environ.get("INSTAGRAM_COOKIES") # Get cookies from environment variable
        
    # Path for temporary cookies file
    cookies_file_path = 'cookies.txt' 

    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'noplaylist': True,
            'max_filesize': 50 * 1024 * 1024, # 50 MB limit for easy upload to Telegram
            'nocheckcertificate': True,
            'retries': 3,
            'no_warnings': True,
            'quiet': True,
            # Add cookies if available
            'cookiefile': cookies_file_path, # yt-dlp reads cookies from this file
        }
        
        # If cookies are received from environment variable, save them to a temporary file
        if instagram_cookies:
            with open(cookies_file_path, 'w') as f:
                f.write(instagram_cookies)
            logger.info("Instagram cookies loaded from environment variable.")
        else:
            logger.warning("INSTAGRAM_COOKIES environment variable not set. Instagram downloads might fail.")

        os.makedirs('downloads', exist_ok=True) # Ensure 'downloads' directory exists

        await update.message.reply_text("در حال پردازش و دانلود لینک شما، لطفاً منتظر بمانید...")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        if os.path.exists(filename):
            if info.get('ext') in ['mp4', 'webm', 'avi', 'mkv', 'mov']:
                await update.message.reply_video(video=open(filename, 'rb'), caption="ویدیوی شما آماده است!")
            elif info.get('ext') in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                await update.message.reply_photo(photo=open(filename, 'rb'), caption="تصویر شما آماده است!")
            elif info.get('ext') in ['mp3', 'wav', 'ogg', 'flac']:
                await update.message.reply_audio(audio=open(filename, 'rb'), caption="فایل صوتی شما آماده است!")
            else:
                await update.message.reply_document(document=open(filename, 'rb'), caption="فایل شما آماده است!")
            
            os.remove(filename)  # Delete file after sending
            if os.path.exists('downloads') and not os.listdir('downloads'): # Check if dir is empty before removing
                os.rmdir('downloads')
        else:
            await update.message.reply_text("متاسفانه در دانلود محتوا مشکلی پیش آمد.")

    except yt_dlp.DownloadError as e:
        logger.error(f"Download error with yt-dlp for {url}: {e}")
        await update.message.reply_text(f"متاسفانه در دانلود محتوا مشکلی پیش آمد. دلیل احتمالی: {e.msg}")
    except Exception as e:
        logger.error(f"General download error for {url}: {e}")
        await update.message.reply_text("یک خطای ناشناخته در هنگام دانلود رخ داد. لطفاً مطمئن شوید لینک معتبر است.")
    finally:
        # Clean up the temporary cookies file after completion (important for security and cleanup)
        if os.path.exists(cookies_file_path):
            os.remove(cookies_file_path)

async def download_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /download command for private chats or explicit command usage."""
    if not context.args:
        await update.message.reply_text("لطفاً لینکی برای دانلود بعد از /download وارد کنید. مثال: /download https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    url = context.args[0]
    await _perform_download(update, context, url)

async def manage_group_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing URLs in groups. Downloads content from allowed sites or deletes the message.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        return # Only for groups

    session = Session()
    try:
        user_id = update.effective_user.id
        user = get_or_create_user_db(
            session,
            user_id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )

        message_text = update.message.text
        urls = re.findall(r'https?://[^\s]+', message_text)

        if not urls:
            return # No URL found in the message

        # Define allowed domains for direct download/keeping the message
        allowed_domains = [
            "youtube.com", "youtu.be", "instagram.com", "tiktok.com", "pinterest.com", "pin.it"
        ]

        is_allowed_link = False
        for url in urls:
            # Check if any part of the URL matches an allowed domain
            if any(domain in url for domain in allowed_domains):
                is_allowed_link = True
                break
        
        # Check if the user is a special user and allowed to send any link
        if user.is_special:
            is_allowed_link = True # Special users can send any link

        if is_allowed_link:
            await _perform_download(update, context, urls[0])
        else:
            # If the link is not allowed, delete the message
            try:
                # Get chat settings to know the warning limit
                chat_id = update.effective_chat.id
                settings = get_chat_settings_db(session, chat_id)

                await update.message.delete()
                # Apply warning to user
                user.warnings += 1
                session.commit() # Save changes to DB

                current_warnings = user.warnings
                if current_warnings >= settings.warning_limit:
                    try:
                        await context.bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"{user.first_name} به دلیل ارسال لینک غیرمجاز و رسیدن به {settings.warning_limit} اخطار از گروه بن شد.",
                            parse_mode='HTML'
                        )
                        user.warnings = 0 # Reset warnings after ban
                        session.commit()
                    except Exception as e:
                        logger.error(f"Error banning user after warnings for link: {e}")
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text="ربات نتوانست کاربر را بن کند. (شاید ربات مجوز ندارد یا کاربر ادمین است)"
                        )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"پیام حاوی لینک غیرمجاز توسط {update.effective_user.mention_html()} حذف شد. {user.first_name} اخطار گرفت. تعداد اخطارهای فعلی: {current_warnings}/{settings.warning_limit}",
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Error deleting message or sending warning: {e}")
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="ربات نتوانست پیام حاوی لینک غیرمجاز را حذف کند یا اخطار بدهد. لطفاً مطمئن شوید ربات مجوزهای لازم را دارد."
                )
    except Exception as e:
        session.rollback()
        logger.error(f"Error in manage_group_links (outer try): {e}")
    finally:
        session.close()


# --- Reply Translation Handler ---

async def reply_translate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translates the replied message to Farsi if the reply text is 'ترجمه'."""
    # Ensure update.message.text is not None and matches "ترجمه" exactly after stripping whitespace
    if update.message.reply_to_message and update.message.text and update.message.text.strip() == "ترجمه":
        original_message_text = update.message.reply_to_message.text
        if not original_message_text:
            await update.message.reply_text("پیام ریپلای شده متنی برای ترجمه ندارد.")
            return

        translator = Translator()
        try:
            translated = translator.translate(original_message_text, dest='fa')
            await update.message.reply_text(f"ترجمه پیام اصلی: {translated.text}", reply_to_message_id=update.message.reply_to_message.message_id)
        except Exception as e:
            logger.error(f"Reply translation error: {e}")
            await update.message.reply_text("متاسفانه در حال حاضر امکان ترجمه وجود نداره. لطفاً بعداً امتحان کنید.")

# --- Welcome New Members ---

async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets new members joining the group."""
    session = Session()
    try:
        chat_id = update.effective_chat.id
        settings = get_chat_settings_db(session, chat_id)

        for member in update.message.new_chat_members:
            if member.id == context.bot.id: # If the bot itself was added
                await update.message.reply_text("ممنون که منو به گروهتون اضافه کردید! من DigitalBot هستم و آماده‌ام تا به شما کمک کنم.")
                continue

            group_name = update.effective_chat.title
            welcome_text_formatted = settings.welcome_text.format(
                user_name=member.mention_html(),
                group_name=group_name
            )

            if settings.welcome_media_id and settings.welcome_media_type:
                if settings.welcome_media_type == 'photo':
                    await update.message.reply_photo(
                        photo=settings.welcome_media_id,
                        caption=welcome_text_formatted,
                        parse_mode='HTML'
                    )
                elif settings.welcome_media_type == 'video':
                    await update.message.reply_video(
                        video=settings.welcome_media_id,
                        caption=welcome_text_formatted,
                        parse_mode='HTML'
                    )
            else:
                await update.message.reply_html(
                    f"خوش آمدید {member.mention_html()} به گروه **{group_name}**!",
                    parse_mode='HTML'
                )
    finally:
        session.close()
        # --- Admin Capabilities ---

async def admin_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles admin actions triggered by replying to a message."""
    session = Session()
    try:
        if not update.message.reply_to_message or not update.message.text:
            return # Not a reply or no text in the message

        # Check admin status first
        if not await is_admin_or_creator(update, context):
            return # Only admins can use these commands (is_admin_or_creator sends a message)

        target_user_id = update.message.reply_to_message.from_user.id
        # If the replied message is just a user ID, use that for target_user_id
        if update.message.reply_to_message.text and update.message.text.strip() == "رفع بن":
            try:
                target_user_id = int(update.message.reply_to_message.text.strip())
            except ValueError:
                await update.message.reply_text("برای رفع بن، لطفاً روی پیامی که حاوی آیدی عددی کاربر است ریپلای کنید.")
                return
        
        target_user_info = await context.bot.get_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id)
        # We need the user's name even if they are not in our DB yet.
        target_user_name = target_user_info.user.first_name if target_user_info.user.first_name else "کاربر"
        if target_user_info.user.last_name:
            target_user_name += f" {target_user_info.user.last_name}"
        if target_user_info.user.username:
            target_user_name += f" (@{target_user_info.user.username})"

        # Ensure target_user exists in our DB if we're going to modify it (like warnings)
        target_user_db = get_or_create_user_db(
            session,
            target_user_id,
            target_user_info.user.username,
            target_user_info.user.first_name,
            target_user_info.user.last_name
        )

        chat_id = update.effective_chat.id
        command = update.message.text.strip() # Strip whitespace for exact match
        settings = get_chat_settings_db(session, chat_id) # Get chat specific settings

        # Pin Message
        if command == "پین":
            try:
                await context.bot.pin_chat_message(
                    chat_id=chat_id,
                    message_id=update.message.reply_to_message.message_id,
                    disable_notification=False
                )
                await update.message.reply_text("پیام پین شد.")
            except Exception as e:
                logger.error(f"Error pinning message: {e}")
                await update.message.reply_text("متاسفانه نتوانستم پیام را پین کنم. (شاید ربات مجوز ندارد)")

        # Ban User
        elif command == "بن":
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
                await update.message.reply_text(f"{target_user_name} از گروه بن شد.", parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error banning user: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")

        # Unban User
        elif command == "رفع بن":
            try:
                # Ensure the user is actually banned before trying to unban
                chat_member_status = await context.bot.get_chat_member(chat_id, target_user_id)
                if chat_member_status.status == ChatMember.BANNED:
                    await context.bot.unban_chat_member(chat_id=chat_id, user_id=target_user_id)
                    await update.message.reply_text(f"{target_user_name} از بن خارج شد.", parse_mode='HTML')
                else:
                    await update.message.reply_text(f"{target_user_name} در حال حاضر بن نیست.")
            except Exception as e:
                logger.error(f"Error unbanning user: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را رفع بن کنم. (شاید ربات مجوز ندارد یا آیدی نامعتبر است)")

        # Warning System
        elif command == "اخطار":
            target_user_db.warnings += 1
            session.commit() # Save changes to DB
            current_warnings = target_user_db.warnings
            
            if current_warnings >= settings.warning_limit: # Use limit from DB
                try:
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user_id)
                    await update.message.reply_text(
                        f"{target_user_name} به دلیل رسیدن به {settings.warning_limit} اخطار از گروه بن شد.",
                        parse_mode='HTML'
                    )
                    target_user_db.warnings = 0 # Reset warnings after ban
                    session.commit()
                except Exception as e:
                    logger.error(f"Error banning user after warnings: {e}")
                    await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")
            else:
                await update.message.reply_text(
                    f"{target_user_name} اخطار گرفت. تعداد اخطارهای فعلی: {current_warnings}/{settings.warning_limit}",
                    parse_mode='HTML'
                )
        
        # Set Warning Limit
        elif command.startswith("تنظیم اخطار"):
            try:
                parts = command.split()
                if len(parts) < 3: # Check for "تنظیم", "اخطار", and the number
                    await update.message.reply_text("فرمت صحیح: تنظیم اخطار <عدد>")
                    return
                new_limit = int(parts[2])
                if new_limit > 0:
                    settings.warning_limit = new_limit
                    session.commit() # Save to DB
                    await update.message.reply_text(f"حد اخطار به {new_limit} تنظیم شد.")
                else:
                    await update.message.reply_text("عدد اخطار باید مثبت باشد.")
            except (ValueError, IndexError):
                await update.message.reply_text("فرمت صحیح: تنظیم اخطار <عدد>")
        
        # Mute User
        elif command.startswith("سکوت"):
            try:
                parts = command.split()
                if len(parts) < 2:
                    await update.message.reply_text("لطفاً مدت سکوت را به دقیقه وارد کنید. مثال: سکوت 30")
                    return
                
                mute_duration_minutes = int(parts[1])
                if mute_duration_minutes <= 0:
                    await update.message.reply_text("مدت سکوت باید مثبت باشد.")
                    return

                until_date = datetime.now() + timedelta(minutes=mute_duration_minutes)
                
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=target_user_id,
                    permissions=ChatMember.ALL_PERMISSIONS.with_can_send_messages(False), # Restrict sending messages
                    until_date=until_date
                )
                await update.message.reply_text(
                    f"{target_user_name} به مدت {mute_duration_minutes} دقیقه سکوت شد.",
                    parse_mode='HTML'
                )
            except (ValueError, IndexError):
                await update.message.reply_text("فرمت صحیح: سکوت <عدد به دقیقه>")
            except Exception as e:
                logger.error(f"Error muting user: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را سکوت کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")

        # Promote User to Admin
        elif command == "ادمین":
            try:
                # Bot needs to be admin with 'Add New Admins' permission
                # If target user is already admin, Telegram raises BadRequest
                chat_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=target_user_id)
                if chat_member.status in ["creator", "administrator"]:
                    await update.message.reply_text(f"{target_user_name} در حال حاضر ادمین است.")
                    return

                await context.bot.promote_chat_member(
                    chat_id=chat_id,
                    user_id=target_user_id,
                    can_change_info=True,
                    can_delete_messages=True,
                    can_invite_users=True,
                    can_restrict_members=True,
                    can_pin_messages=True,
                    can_promote_members=False, # Bot shouldn't give permission to promote members to new admins
                    can_manage_chat=True,
                    can_manage_video_chats=True,
                    can_post_messages=True,
                    can_edit_messages=True,
                    is_anonymous=False # Should not be anonymous by default
                )
                await update.message.reply_text(f"{target_user_name} به عنوان ادمین گروه اضافه شد.", parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error promoting user to admin: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را ادمین کنم. (شاید ربات مجوز 'افزودن مدیران جدید' را ندارد یا کاربر ادمین است)")

        # Set Welcome Message Text (Admin only)
        elif command == "تنظیم خوشامد متن":
            if update.message.reply_to_message and update.message.reply_to_message.text:
                settings.welcome_text = update.message.reply_to_message.text
                session.commit()
                await update.message.reply_text("متن خوشامدگویی با موفقیت تنظیم شد.")
            else:
                await update.message.reply_text("لطفاً روی پیامی که حاوی متن خوشامدگویی جدید است ریپلای کنید و 'تنظیم خوشامد متن' را بنویسید.")

        # Set Welcome Message Media (Admin only)
        elif command == "تنظیم خوشامد رسانه":
            if update.message.reply_to_message:
                if update.message.reply_to_message.photo:
                    settings.welcome_media_id = update.message.reply_to_message.photo[-1].file_id # Get largest photo
                    settings.welcome_media_type = 'photo'
                    session.commit()
                    await update.message.reply_text("تصویر خوشامدگویی با موفقیت تنظیم شد.")
                elif update.message.reply_to_message.video:
                    settings.welcome_media_id = update.message.reply_to_message.video.file_id
                    settings.welcome_media_type = 'video'
                    session.commit()
                    await update.message.reply_text("ویدیوی خوشامدگویی با موفقیت تنظیم شد.")
                else:
                    await update.message.reply_text("لطفاً روی یک تصویر یا ویدیو ریپلای کنید و 'تنظیم خوشامد رسانه' را بنویسید.")
            else:
                await update.message.reply_text("لطفاً روی یک تصویر یا ویدیو ریپلای کنید و 'تنظیم خوشامد رسانه' را بنویسید.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error in admin_actions_on_reply: {e}")
    finally:
        session.close()

# --- Group Owner Capabilities ---

async def owner_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles group owner actions triggered by replying to a message."""
    session = Session()
    try:
        if not update.message.reply_to_message or not update.message.text:
            return # Not a reply or no text in the message

        # Check if the user is the group creator OR the designated bot owner
        is_owner_or_bot_owner = await is_group_owner(update, context) or \
                                update.effective_user.id == get_bot_owner_id_db(session)
        
        if not is_owner_or_bot_owner:
            return # Only group owner or bot owner can use these commands (is_group_owner sends a message)

        target_user_id = update.message.reply_to_message.from_user.id
        target_user_info = await context.bot.get_chat_member(chat_id=update.effective_chat.id, user_id=target_user_id)
        target_user_name = target_user_info.user.first_name if target_user_info.user.first_name else "کاربر"
        if target_user_info.user.last_name:
            target_user_name += f" {target_user_info.user.last_name}"
        if target_user_info.user.username:
            target_user_name += f" (@{target_user_info.user.username})"

        # Ensure target_user exists in our DB if we're going to modify it
        target_user_db = get_or_create_user_db(
            session,
            target_user_id,
            target_user_info.user.username,
            target_user_info.user.first_name,
            target_user_info.user.last_name
        )

        command = update.message.text.strip() # Strip whitespace for exact match

        # Special User
        if command == "کاربر ویژه":
            target_user_db.is_special = True
            session.commit()
            await update.message.reply_text(f"{target_user_name} به عنوان کاربر ویژه اضافه شد. او اکنون می‌تواند لینک ارسال کند.", parse_mode='HTML')
        
        # Bot Owner (Only group creator can set bot owner initially)
        elif command == "مالک ربات":
            # Extra check to ensure only the actual group creator can assign bot owner
            # to prevent a non-creator bot owner from changing the bot owner
            if not await is_group_owner(update, context): 
                await update.message.reply_text("این دستور فقط توسط سازنده گروه قابل استفاده است تا مالک ربات را تعیین کند.")
                return

            set_bot_owner_id_db(session, target_user_id)
            await update.message.reply_text(f"{target_user_name} به عنوان مالک ربات تعیین شد. او اکنون قابلیت‌های مالک گروه را دارد.", parse_mode='HTML')
    except Exception as e:
        session.rollback()
        logger.error(f"Error in owner_actions_on_reply: {e}")
    finally:
        session.close()

# --- Statistics ---

async def update_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Updates user chat statistics."""
    # Ensure there's a message and it's from a user (not a channel, etc.)
    if not update.effective_user or not update.message:
        return

    session = Session()
    try:
        user_id = update.effective_user.id
        user = get_or_create_user_db(
            session,
            user_id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )
        
        user.total_messages += 1

        now = datetime.now()
        last_time = user.last_message_time if user.last_message_time else datetime.min

        # Reset daily if new day (or new month/year, covers all)
        if now.day != last_time.day or now.month != last_time.month or now.year != last_time.year:
            user.daily_messages = 0
        user.daily_messages += 1

        # Reset hourly if new hour (or new day, covers all)
        if now.hour != last_time.hour or now.day != last_time.day:
            user.hourly_messages = 0
        user.hourly_messages += 1

        # Reset weekly (using ISO week number, which resets at the start of a new ISO year)
        # Check for change in week number OR year
        if now.isocalendar()[1] != last_time.isocalendar()[1] or now.year != last_time.year:
            user.weekly_messages = 0
        user.weekly_messages += 1

        # Reset monthly if new month (or new year, covers all)
        if now.month != last_time.month or now.year != last_time.year:
            user.monthly_messages = 0
        user.monthly_messages += 1

        user.last_message_time = now
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating user stats: {e}")
    finally:
        session.close()

async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows personal chat statistics."""
    session = Session()
    try:
        user_id = update.effective_user.id
        user = session.query(User).filter_by(id=user_id).first()
        
        if not user:
            await update.message.reply_text("شما هنوز چتی در این گروه نداشته‌اید یا آمار شما ثبت نشده است.")
            return

        profile_text = f"""
**پروفایل شما:**
نام کاربری: {user.first_name} {user.last_name if user.last_name else ''} {f"(@{user.username})" if user.username else ''}
آیدی عددی: `{user.id}`
تعداد کل چت‌ها: {user.total_messages}
تعداد چت امروز: {user.daily_messages}
تعداد چت این ساعت: {user.hourly_messages}
تعداد چت این هفته: {user.weekly_messages}
تعداد چت این ماه: {user.monthly_messages}
"""
        await update.message.reply_html(profile_text)
    finally:
        session.close()

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows overall group chat statistics and ranking."""
    session = Session()
    try:
        users = session.query(User).order_by(User.total_messages.desc()).limit(10).all()
        
        if not users:
            await update.message.reply_text("هنوز آماری برای نمایش وجود ندارد.")
            return

        stats_text = "**آمار کلی چت گروه (بر اساس کل پیام‌ها):**\n\n"
        for i, user in enumerate(users):
            user_name = user.first_name if user.first_name else "ناشناس"
            if user.last_name:
                user_name += f" {user.last_name}"
            if user.username:
                user_name += f" (@{user.username})"

            stats_text += f"{i+1}. {user_name}: {user.total_messages} پیام\n"
        
        await update.message.reply_html(stats_text)
    finally:
        session.close()

# --- Main function to run the bot ---

def main() -> None:
    """Start the bot and run it continuously with error handling."""
    # This loop ensures the bot restarts if an error or disconnection occurs.
    while True:
        try:
            logger.info("Initializing DigitalBot...")
            application = Application.builder().token(TOKEN).build()

            # Command Handlers
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(CommandHandler("translate", translate_text))
            application.add_handler(CommandHandler("download", download_command_handler))
            application.add_handler(CommandHandler("myprofile", my_profile))
            application.add_handler(CommandHandler("stats", show_stats))

            # Message Handler for group link management
            application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS & filters.Regex(r'https?://[^\s]+'), manage_group_links))

            # Message Handler for reply translation (exact match for "ترجمه")
            application.add_handler(MessageHandler(filters.TEXT & filters.REPLY & filters.Regex(r'^\s*ترجمه\s*$'), reply_translate))

            # Message Handler for new members (welcome message)
            application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_new_members))

            # Message Handler for all text messages to update stats
            # IMPORTANT: This should be before other TEXT handlers if you want stats for all messages
            # But after specific TEXT & REPLY handlers if you only want stats for non-command messages.
            # Here, it's fine as is, because it explicitly excludes COMMANDs.
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_user_stats))

            # Message Handlers for admin/owner actions using regex for exact match or starts-with
            # Admin commands
            application.add_handler(MessageHandler(
                filters.TEXT & filters.REPLY & filters.ChatType.GROUPS &
                (
                    filters.Regex(r'^\s*پین\s*$') |
                    filters.Regex(r'^\s*بن\s*$') |
                    filters.Regex(r'^\s*رفع بن\s*$') | # New filter for unban
                    filters.Regex(r'^\s*اخطار\s*$') |
                    filters.Regex(r'^\s*سکوت\s+.*$') | 
                    filters.Regex(r'^\s*تنظیم اخطار\s+.*$') | 
                    filters.Regex(r'^\s*ادمین\s*$') | # New filter for admin
                    filters.Regex(r'^\s*تنظیم خوشامد متن\s*$') |
                    filters.Regex(r'^\s*تنظیم خوشامد رسانه\s*$')
                ),
                admin_actions_on_reply
            ))
            # Owner commands
            application.add_handler(MessageHandler(
                filters.TEXT & filters.REPLY & filters.ChatType.GROUPS &
                (
                    filters.Regex(r'^\s*کاربر ویژه\s*$') |
                    filters.Regex(r'^\s*مالک ربات\s*$')
                ),
                owner_actions_on_reply
            ))

            logger.info("DigitalBot started successfully. Listening for updates...")
            # Run the bot using polling. If an error occurs here, it will go to the except block.
            application.run_polling(allowed_updates=Update.ALL_TYPES) 

        except Exception as e:
            logger.error(f"An error occurred: {e}. Restarting bot in 5 seconds...", exc_info=True)
            time.sleep(5)
        finally:
            pass

# This is the main entry point of the program, running both the Telegram bot and Flask server.
if __name__ == "__main__":
    # Function to run the Flask server
    def run_flask_app():
        port = int(os.environ.get("PORT", 10000)) 
        app.run(host='0.0.0.0', port=port)

    # Start Flask in a separate thread.
    flask_thread = Thread(target=run_flask_app)
    flask_thread.start()

    # Run the Telegram bot directly in the main thread.
    main()

    flask_thread.join()
