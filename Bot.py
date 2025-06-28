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

# ... (کدهای موجود شما در بالای digitalbot.py)

from sqlalchemy import create_engine, Column, Integer, String, BigInteger, DateTime, Text, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime, timedelta
import json # برای ذخیره تنظیمات پیچیده مثل خوشامدگویی

# --- Database Setup ---
# ایجاد موتور پایگاه داده SQLite. فایل 'digitalbot.db' ساخته میشه
engine = create_engine('sqlite:///digitalbot.db')
Base = declarative_base() # کلاس پایه برای مدل‌های ما
Session = sessionmaker(bind=engine) # سازنده Session


# تعریف مدل‌ها (جداول پایگاه داده)
class User(Base):
    __tablename__ = 'users'
    id = Column(BigInteger, primary_key=True) # User ID از تلگرام
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
    is_special = Column(Boolean, default=False) # کاربر ویژه
    
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
    user_id = Column(BigInteger, primary_key=True) # ID کاربر مالک ربات
    
    def __repr__(self):
        return f"<BotOwner(user_id={self.user_id})>"


# ایجاد تمامی جداول در پایگاه داده (اگر وجود نداشته باشند)
Base.metadata.create_all(engine)

# --- به روزرسانی متغیرهای سراسری (GLOBAL VARIABLES) ---
# متغیرهای سراسری قبلی رو که اطلاعات رو در حافظه نگه میداشتند، حذف یا تغییر میدیم.
# حالا به جای اونها با Session پایگاه داده کار میکنیم.

# تابع کمکی برای دریافت/ایجاد تنظیمات چت
def get_chat_settings(session, chat_id):
    settings = session.query(ChatSettings).filter_by(chat_id=chat_id).first()
    if not settings:
        settings = ChatSettings(chat_id=chat_id)
        session.add(settings)
        session.commit()
    return settings

# تابع کمکی برای دریافت/ایجاد کاربر
def get_or_create_user(session, user_id, username, first_name, last_name):
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

# تابع کمکی برای دریافت ID مالک ربات
def get_bot_owner_id(session):
    owner = session.query(BotOwner).first()
    return owner.user_id if owner else None

# تابع کمکی برای تنظیم ID مالک ربات
def set_bot_owner_id(session, user_id):
    session.query(BotOwner).delete() # حذف مالک قبلی
    owner = BotOwner(user_id=user_id)
    session.add(owner)
    session.commit()

# --- جایگزینی استفاده از متغیرهای سراسری با دیتابیس در هندلرها ---
# این بخش نیاز به تغییر در تمام هندلرها دارد تا به جای دیکشنری‌ها، از Session پایگاه داده استفاده کنند.

# مثال: تغییر در update_user_stats
async def update_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        user_id = update.effective_user.id
        user = get_or_create_user(
            session,
            user_id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )
        
        user.total_messages += 1

        now = datetime.now()
        last_time = user.last_message_time if user.last_message_time else datetime.min

        # Reset daily if new day
        if now.day != last_time.day or now.month != last_time.month or now.year != last_time.year:
            user.daily_messages = 0
        user.daily_messages += 1

        # Reset hourly if new hour
        if now.hour != last_time.hour or now.day != last_time.day:
            user.hourly_messages = 0
        user.hourly_messages += 1

        # Reset weekly
        # For simplicity, using isocalendar(). This might reset on Jan 1 for a new year
        if now.isocalendar()[1] != last_time.isocalendar()[1] or now.year != last_time.year:
            user.weekly_messages = 0
        user.weekly_messages += 1

        # Reset monthly
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

# مثال: تغییر در my_profile
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        user_id = update.effective_user.id
        user = session.query(User).filter_by(id=user_id).first()
        
        if not user:
            await update.message.reply_text("شما هنوز چتی در این گروه نداشته‌اید یا آمار شما ثبت نشده است.")
            return

        profile_text = f"""
**پروفایل شما:**
نام کاربری: {user.first_name} {user.last_name if user.last_name else ''} (@{user.username} )
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

# مثال: تغییر در show_stats
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

# مثال: تغییر در greet_new_members
async def greet_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        chat_id = update.effective_chat.id
        settings = get_chat_settings(session, chat_id)

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

# مثال: تغییر در admin_actions_on_reply
async def admin_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        if not update.message.reply_to_message:
            return # Not a reply

        if not await is_admin_or_creator(update, context):
            return # Only admins can use these commands

        target_user_id = update.message.reply_to_message.from_user.id
        target_user = get_or_create_user(
            session,
            target_user_id,
            update.message.reply_to_message.from_user.username,
            update.message.reply_to_message.from_user.first_name,
            update.message.reply_to_message.from_user.last_name
        )
        chat_id = update.effective_chat.id
        command = update.message.text.strip()
        settings = get_chat_settings(session, chat_id) # Get chat specific settings

        # Pin Message
        if command == "پین":
            # ... (بقیه کد پین کردن مثل قبل)
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
            # ... (بقیه کد بن کردن مثل قبل)
            try:
                await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user.id)
                await update.message.reply_text(f"{target_user.first_name} از گروه بن شد.", parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error banning user: {e}")
                await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")


        # Warning System
        elif command == "اخطار":
            target_user.warnings += 1
            session.commit() # Save changes to DB
            current_warnings = target_user.warnings
            
            if current_warnings >= settings.warning_limit: # Use limit from DB
                try:
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=target_user.id)
                    await update.message.reply_text(
                        f"{target_user.first_name} به دلیل رسیدن به {settings.warning_limit} اخطار از گروه بن شد.",
                        parse_mode='HTML'
                    )
                    target_user.warnings = 0 # Reset warnings after ban
                    session.commit()
                except Exception as e:
                    logger.error(f"Error banning user after warnings: {e}")
                    await update.message.reply_text("متاسفانه نتوانستم کاربر را بن کنم. (شاید ربات مجوز ندارد یا کاربر ادمین است)")
            else:
                await update.message.reply_text(
                    f"{target_user.first_name} اخطار گرفت. تعداد اخطارهای فعلی: {current_warnings}/{settings.warning_limit}",
                    parse_mode='HTML'
                )
        
        # Set Warning Limit
        elif command.startswith("تنظیم اخطار"):
            try:
                new_limit = int(command.split()[2])
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
                    user_id=target_user.id,
                    permissions=ChatMember.ALL_PERMISSIONS.with_can_send_messages(False),
                    until_date=until_date
                )
                await update.message.reply_text(
                    f"{target_user.first_name} به مدت {mute_duration_minutes} دقیقه سکوت شد.",
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
        session.rollback() # Rollback in case of error
        logger.error(f"Error in admin_actions_on_reply: {e}")
    finally:
        session.close()

# مثال: تغییر در owner_actions_on_reply
async def owner_actions_on_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = Session()
    try:
        if not update.message.reply_to_message:
            return # Not a reply

        if not await is_group_owner(update, context):
            # Check if the user is the bot's owner
            bot_owner_id_db = get_bot_owner_id(session)
            if update.effective_user.id != bot_owner_id_db:
                return # Only group owner or bot owner can use these commands

        target_user_id = update.message.reply_to_message.from_user.id
        target_user = get_or_create_user(
            session,
            target_user_id,
            update.message.reply_to_message.from_user.username,
            update.message.reply_to_message.from_user.first_name,
            update.message.reply_to_message.from_user.last_name
        )
        command = update.message.text.strip()

        # Special User
        if command == "کاربر ویژه":
            target_user.is_special = True
            session.commit()
            await update.message.reply_text(f"{target_user.first_name} به عنوان کاربر ویژه اضافه شد. او اکنون می‌تواند لینک ارسال کند.", parse_mode='HTML')
        
        # Bot Owner (Only group owner can set bot owner)
        elif command == "مالک ربات":
            if not await is_group_owner(update, context): # Double check only group creator can set this
                await update.message.reply_text("این دستور فقط توسط سازنده گروه قابل استفاده است.")
                return

            set_bot_owner_id(session, target_user.id)
            await update.message.reply_text(f"{target_user.first_name} به عنوان مالک ربات تعیین شد. او اکنون قابلیت‌های مالک گروه را دارد.", parse_mode='HTML')
    except Exception as e:
        session.rollback()
        logger.error(f"Error in owner_actions_on_reply: {e}")
    finally:
        session.close()

# ... (کدهای بقیه هندلرها و main مثل قبل)


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
