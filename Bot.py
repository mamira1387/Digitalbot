import logging
import os
import re
import datetime
from telegram import Update, ForceReply, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    ChatMemberHandler
)
from googletrans import Translator
import yt_dlp

# --- Database Setup (Conceptual - You need to implement this) ---
# This part requires a database like SQLite, PostgreSQL, etc.
# For simplicity, I'll use placeholders.
# In a real app, you'd define models for User, Chat, WelcomeSettings, etc.

# Example: A simple in-memory store for demonstration (NOT PERSISTENT!)
# For production, replace with a proper database.
user_stats = {} # {user_id: {'total_messages': 0, 'last_day_messages': 0, ...}}
warning_counts = {} # {user_id: count}
special_users = set() # {user_id}
bot_owner_id = None # Set this to your Telegram User ID (numeric)

# Welcome message settings (in-memory, needs DB for persistence)
welcome_message_text = "خوش آمدید به گروه {group_name}!"
welcome_message_media_id = None # File ID for photo/video
welcome_message_media_type = None # 'photo' or 'video'
default_warnings_limit = 5

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Bot Token ---
# It's highly recommended to load this from an environment variable
# For local testing, you can put it directly here, but REMOVE IT FOR PRODUCTION!
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN_HERE")
# If you use python-dotenv, you can load it like:
# from dotenv import load_dotenv
# load_dotenv()
# TOKEN = os.getenv("TOKEN")

# --- Helper Functions ---

async def is_admin_or_creator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is an administrator or creator in the chat."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status in ["creator", "administrator"]:
            return True
        else:
            await update.message.reply_text("این دستور فقط برای ادمین‌ها و سازنده گروه قابل استفاده است.")
            return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        await update.message.reply_text("خطایی در بررسی وضعیت ادمین رخ داد.")
        return False

async def is_group_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is the creator of the group."""
    if update.effective_chat.type not in ["group", "supergroup"]:
        await update.message.reply_text("این دستور فقط در گروه‌ها قابل استفاده است.")
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status == "creator":
            return True
        else:
            await update.message.reply_text("این دستور فقط برای سازنده گروه قابل استفاده است.")
            return False
    except Exception as e:
        logger.error(f"Error checking group owner status: {e}")
        await update.message.reply_text("خطایی در بررسی وضعیت سازنده گروه رخ داد.")
        return False

# --- Command Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"سلام {user.mention_html()}! من DigitalBot هستم. برای استفاده از قابلیت‌های من، می‌تونی از دستورات زیر استفاده کنی:
/help - راهنمای کامل
/translate <متن> - ترجمه متن به فارسی
/download <لینک> - دانلود محتوا از لینک
/myprofile - مشاهده آمار چت خودت
/stats - مشاهده آمار کلی گروه
",
        reply_markup=ForceReply(selective=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    await update.message.reply_text(f"""
راهنمای استفاده از DigitalBot (سازنده: armanloyalguy):

**دستورات عمومی:**
/start : شروع کار با ربات و معرفی.
/help : نمایش این راهنما.
/translate <متن> : متن مورد نظر شما رو به فارسی ترجمه می‌کنه.
/download <لینک> : لینک ویدیوی مورد نظر شما رو از سایت‌های پشتیبانی شده (یوتیوب، اینستاگرام، تیک‌تاک، پینترست و ...) دانلود می‌کنه.
/myprofile : آمار چت خودت رو نشون می‌ده.
/stats : آمار کلی چت گروه و رتبه‌بندی رو نشون می‌ده.

**قابلیت‌های گروه:**
- **مدیریت لینک:** لینک‌های اینستاگرام، یوتیوب، تیک‌تاک و پینترست رو دانلود می‌کنم. لینک‌های دیگه رو حذف می‌کنم.
- **ترجمه ریپلای:** با ریپلای روی یک پیام و نوشتن 'ترجمه'، اون پیام رو به فارسی ترجمه می‌کنم.
- **پیام خوشامدگویی:** به اعضای جدید خوشامد می‌گم.

**قابلیت‌های ادمین (فقط برای ادمین‌ها و سازنده گروه):**
- **پین کردن پیام:** روی پیامی ریپلای کن و بنویس 'پین'.
- **بن کردن کاربر:** روی پیامی از کاربر ریپلای کن و بنویس 'بن'.
- **اخطار دادن:** روی پیامی از کاربر ریپلای کن و بنویس 'اخطار'. (پیش‌فرض 5 اخطار تا بن)
- **تنظیم حد اخطار:** روی پیامی ریپلای کن و بنویس 'تنظیم اخطار <عدد>'.
- **سکوت کاربر:** روی پیامی از کاربر ریپلای کن و بنویس 'سکوت <عدد به دقیقه>'.
- **تنظیم پیام خوشامدگویی:**
    - برای تنظیم متن: روی پیامی ریپلای کن و بنویس 'تنظیم خوشامد متن'.
    - برای تنظیم تصویر/ویدیو: روی تصویر/ویدیوی مورد نظر ریپلای کن و بنویس 'تنظیم خوشامد رسانه'.

**قابلیت‌های مالک گروه (فقط برای سازنده گروه):**
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
    try:
        ydl_opts = {
            'format': 'best',
            'outtmpl': 'downloads/%(title)s.%(ext)s', # Save to a 'downloads' folder
            'noplaylist': True,
            'max_filesize': 50 * 1024 * 1024, # Limit to 50MB for Telegram upload ease
            'nocheckcertificate': True,
            'retries': 3,
            'no_warnings': True,
            'quiet': True,
        }
        os.makedirs('downloads', exist_ok=True) # Ensure downloads directory exists

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
            
            os.remove(filename)  # Clean up the file after sending
            if not os.listdir('downloads'): # Remove directory if empty
                os.rmdir('downloads')
        else:
            await update.message.reply_text("متاسفانه در دانلود محتوا مشکلی پیش آمد.")

    except yt_dlp.DownloadError as e:
        logger.error(f"Download error with yt-dlp for {url}: {e}")
        await update.message.reply_text(f"متاسفانه در دانلود محتوا مشکلی پیش آمد. دلیل احتمالی: {e.msg}")
    except Exception as e:
        logger.error(f"General download error for {url}: {e}")
        await update.message.reply_text("یک خطای ناشناخته در هنگام دانلود رخ داد. لطفاً مطمئن شوید لینک معتبر است.")

async def download_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /download command for private chats or explicit command usage."""
    if not context.args:
        await update.message.reply_text("لطفاً لینکی برای دانلود بعد از /download وارد کنید. مثال: /download https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    url = context.args[0]
    await update.message.reply_text("در حال پردازش و دانلود لینک شما، لطفاً منتظر بمانید...")
    await _perform_download(update, context, url)

async def manage_group_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing URLs in groups. Downloads content from allowed sites or deletes the message.
    """
    if update.effective_chat.type not in ["group", "supergroup"]:
        return # Only for groups

    message_text = update.message.text
    urls = re.findall(r'https?://[^\s]+', message_text)

    if not urls:
        return # No URL found in the message

    # Define allowed domains for direct download/keeping the message
    allowed_domains = [
        "youtube.com", "youtu.be", # YouTube
        "instagram.com", "tiktok.com", "pinterest.com", "pin.it"
    ]

    is_allowed_link = False
    for url in urls:
        if any(domain in url for domain in allowed_domains):
            is_allowed_link = True
            break
    
    # Check if the user is a special user and allowed to send any link
    if update.effective_user.id in special_users:
        is_allowed_link = True # Special users can send any link

    if is_allowed_link:
        await update.message.reply_text("لینک مجاز تشخیص داده شد. در حال پردازش و دانلود محتوا...")
        await _perform_download(update, context, urls[0])
    else:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"پیام حاوی لینک غیرمجاز توسط {update.effective_user.mention_html()} حذف شد.",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="ربات نتوانست پیام حاوی لینک غیرمجاز را حذف کند. لطفاً مطمئن شوید ربات مجوزهای لازم را دارد."
            )

# --- Reply Translation Handler ---

async def reply_translate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Translates the replied message to Farsi if the reply text is 'ترجمه'."""
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
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: # If the bot itself was added
            await update.message.reply_text("ممنون که منو به گروهتون اضافه کردید! من DigitalBot هستم و آماده‌ام تا به شما کمک کنم.")
            continue

        group_name = update.effective_chat.title
        welcome_text_formatted = welcome_message_text.format(
            user_name=member.mention_html(),
            group_name=group_name
        )

        if welcome_message_media_id and welcome_message_media_type:
            if welcome_message_media_type == 'photo':
                await update.message.reply_photo(
                    photo=welcome_message_media_id,
                    caption=welcome_text_formatted,
                    parse_mode='HTML'
                )
            elif welcome_message_media_type == 'video':
                await update.message.reply_video(
                    video=welcome_message_media_id,
                    caption=welcome_text_formatted,
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_html(
                f"خوش آمدید {member.mention_html()} به گروه **{group_name}**!",
                parse_mode='HTML'
            )

# --- Admin Capabilities ---

async def admin_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles admin actions triggered by replying to a message."""
    if not update.message.reply_to_message:
        return # Not a reply

    if not await is_admin_or_creator(update, context):
        return # Only admins can use these commands

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    command = update.message.text.strip()

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
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user.id)
            await update.message.reply_text(f"{target_user.mention_html()} از گروه بن شد.", parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")

    # Warning System
    elif command == "اخطار":
        warning_counts[target_user.id] = warning_counts.get(target_user.id, 0) + 1
        current_warnings = warning_counts[target_user.id]
        
        if current_warnings >= default_warnings_limit:
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user.id)
                await update.message.reply_text(
                    f"{target_user.mention_html()} به دلیل رسیدن به {default_warnings_limit} اخطار از گروه بن شد.",
                    parse_mode='HTML'
                )
                del warning_counts[target_user.id] # Reset warnings after ban
            except Exception as e:
                logger.error(f"Error banning user after warnings: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")
        else:
            await update.message.reply_text(
                f"{target_user.mention_html()} اخطار گرفت. تعداد اخطارهای فعلی: {current_warnings}/{default_warnings_limit}",
                parse_mode='HTML'
            )
    
    # Set Warning Limit
    elif command.startswith("تنظیم اخطار"):
        try:
            new_limit = int(command.split()[2])
            if new_limit > 0:
                global default_warnings_limit
                default_warnings_limit = new_limit
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

            until_date = datetime.datetime.now() + datetime.timedelta(minutes=mute_duration_minutes)
            
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user.id,
                permissions=ChatMember.ALL_PERMISSIONS.with_can_send_messages(False), # Restrict sending messages
                until_date=until_date
            )
            await update.message.reply_text(
                f"{target_user.mention_html()} به مدت {mute_duration_minutes} دقیقه سکوت شد.",
                parse_mode='HTML'
            )
        except (ValueError, IndexError):
            await update.message.reply_text("فرمت صحیح: سکوت <عدد به دقیقه>")
        except Exception as e:
            logger.error(f"Error muting user: {e}")
            await update.message.reply_text("متاسفانه نتوانستم کاربر را سکوت کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")

    # Set Welcome Message Text (Admin only)
    elif command == "تنظیم خوشامد متن":
        if update.message.reply_to_message and update.message.reply_to_message.text:
            global welcome_message_text
            welcome_message_text = update.message.reply_to_message.text
            await update.message.reply_text("متن خوشامدگویی با موفقیت تنظیم شد.")
        else:
            await update.message.reply_text("لطفاً روی پیامی که حاوی متن خوشامدگویی جدید است ریپلای کنید و 'تنظیم خوشامد متن' را بنویسید.")

    # Set Welcome Message Media (Admin only)
    elif command == "تنظیم خوشامد رسانه":
        if update.message.reply_to_message:
            global welcome_message_media_id, welcome_message_media_type
            if update.message.reply_to_message.photo:
                welcome_message_media_id = update.message.reply_to_message.photo[-1].file_id # Get largest photo
                welcome_message_media_type = 'photo'
                await update.message.reply_text("تصویر خوشامدگویی با موفقیت تنظیم شد.")
            elif update.message.reply_to_message.video:
                welcome_message_media_id = update.message.reply_to_message.video.file_id
                welcome_message_media_type = 'video'
                await update.message.reply_text("ویدیوی خوشامدگویی با موفقیت تنظیم شد.")
            else:
                await update.message.reply_text("لطفاً روی یک تصویر یا ویدیو ریپلای کنید و 'تنظیم خوشامد رسانه' را بنویسید.")
        else:
            await update.message.reply_text("لطفاً روی یک تصویر یا ویدیو ریپلای کنید و 'تنظیم خوشامد رسانه' را بنویسید.")

# --- Group Owner Capabilities ---

async def owner_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles group owner actions triggered by replyin
