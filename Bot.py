import logging
import os
import re
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from googletrans import Translator, LANGUAGES
import yt_dlp
# import requests # این ایمپورت استفاده نشده بود و حذف شد

# تنظیم لاگینگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات (از BotFather بگیرید و در متغیرهای محیطی Render تنظیم کنید)
# نام متغیر محیطی را به TELEGRAM_TOKEN تغییر دادم تا استانداردتر باشد.
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    logger.error("Telegram BOT_TOKEN environment variable not set. Please set it in Render environment variables.")
    exit(1) # اگر توکن نباشد، برنامه باید متوقف شود

# تنظیم مسیر برای ذخیره فایل‌های دانلود شده
DOWNLOAD_PATH = "downloads"
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# شیء مترجم
translator = Translator()

# تابع بررسی لینک رسانه
def is_media_url(url):
    # لیست دامنه ها را گسترش دادم تا پوشش بهتری داشته باشد
    media_domains = [
        "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
        "twitter.com", "x.com", "facebook.com"
    ]
    # بررسی کنید که آیا هر یک از دامنه ها در URL وجود دارد
    return any(domain in url.lower() for domain in media_domains)

# تابع شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من DigitalBot هستم. می‌تونم متن‌ها رو به فارسی ترجمه کنم و از یوتیوب، اینستاگرام و تیک‌تاک ویدیو دانلود کنم.\n"
        "دستورات:\n"
        "/start - شروع ربات\n"
        "/help - نمایش راهنما\n"
        "/translate <متن> - ترجمه متن به فارسی\n"
        "/download <لینک> - دانلود ویدیو\n"
        "یا فقط لینک بفرستید تا خودم تشخیص بدم!\n"
        "برای ترجمه پیام، روی پیام ریپلای کنید و بنویسید 'ترجمه'"
    )
    logger.info(f"Start command received from {update.effective_user.id}.")

# تابع راهنما
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات من:\n"
        "/start - شروع ربات\n"
        "/help - نمایش این راهنما\n"
        "/translate <متن> - ترجمه متن به فارسی\n"
        "/download <لینک> - دانلود ویدیو از یوتیوب، اینستا یا تیک‌تاک\n"
        "یا فقط لینک بفرستید تا خودم بررسی کنم.\n"
        "برای ترجمه پیام، روی پیام ریپلای کنید و بنویسید 'ترجمه'."
    )
    logger.info(f"Help command received from {update.effective_user.id}.")

# تابع ترجمه
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_to_translate = None

    # اگر آرگومان بعد از دستور بود (مثلا /translate Hello)
    if context.args:
        text_to_translate = " ".join(context.args)
    # اگر روی پیامی ریپلای شده بود و متن پیام "ترجمه" یا "/ترجمه" یا "/translate" بود
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        # مطمئن می شویم که پیام فعلی خودش هم یکی از کلمات کلیدی ترجمه باشد
        if update.message.text and update.message.text.lower() in ["ترجمه", "/ترجمه", "/translate"]:
            text_to_translate = update.message.reply_to_message.text
    
    if not text_to_translate:
        await update.message.reply_text("لطفاً متنی برای ترجمه وارد کنید یا روی پیام ریپلای کنید و بنویسید 'ترجمه'.\nمثال: /translate Hello")
        return

    try:
        translation = translator.translate(text_to_translate, dest="fa")
        await update.message.reply_text(
            f"متن: {translation.origin}\n"
            f"زبان مبدا: {LANGUAGES.get(translation.src, 'ناشناخته')}\n"
            f"ترجمه به فارسی: {translation.text}"
        )
        logger.info(f"Text translated for {update.effective_user.id}.")
    except Exception as e:
        logger.error(f"خطا در ترجمه برای کاربر {update.effective_user.id}: {e}")
        await update.message.reply_text("خطایی در ترجمه رخ داد. دوباره امتحان کنید.")

# تابع دانلود
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE, url=None):
    # اگر url از طریق آرگومان context.args یا پارامتر url داده نشده بود
    if not url and context.args:
        url = context.args[0]
    elif not url and not context.args: # اگر هیچ لینکی داده نشد
        await update.message.reply_text("لطفاً لینک ویدیو رو وارد کنید. مثال:\n/download https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    if not is_media_url(url):
        await update.message.reply_text("این لینک رسانه‌ای نیست و نمی‌تونم دانلودش کنم. لطفاً لینک معتبر از یوتیوب، اینستاگرام، تیک‌تاک، توییتر یا فیس‌بوک بده.")
        return

    message_to_edit = await update.message.reply_text("⬇️ در حال دانلود... لطفاً صبر کنید.")
    
    try:
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_PATH}/%(title)s.%(ext)s",
            "format": "best",
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True, # برای حل مشکلات SSL در برخی سایت ها
            "postprocessors": [{ # برای تبدیل به mp4 اگر فرمت دیگری بود
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        # اطمینان از اینکه فایل وجود دارد و اندازه آن صفر نیست
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise Exception("فایل دانلود نشد یا خالی است.")

        with open(file_path, "rb") as file:
            await update.message.reply_document(document=file, caption="ویدیو دانلود شد!")
        
        os.remove(file_path)  # حذف فایل بعد از ارسال
        await message_to_edit.edit_text("✅ دانلود و ارسال با موفقیت انجام شد.")
        logger.info(f"Video downloaded and sent for {update.effective_user.id} from URL: {url}")
    except Exception as e:
        logger.error(f"خطا در دانلود برای کاربر {update.effective_user.id} از لینک {url}: {e}")
        await message_to_edit.edit_text("خطایی در دانلود رخ داد. مطمئن بشید لینک معتبره یا فایل خیلی بزرگه.")
        # اگر فایل جزئی دانلود شده بود، آن را حذف کنید
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)


# تابع شناسایی خودکار لینک و مدیریت پیام های متنی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    if not message_text: # اگر پیام متنی نبود (مثلا عکس یا استیکر)
        return

    # بررسی برای ترجمه ریپلای شده
    if update.message.reply_to_message and message_text.lower() in ["ترجمه", "/ترجمه", "/translate"]:
        await translate(update, context)
        return

    # بررسی برای کماندهای فارسی شبیه سازی شده
    if message_text.lower() == "/شروع":
        await start(update, context)
        return
    if message_text.lower() == "/راهنما":
        await help_command(update, context)
        return
    if message_text.lower() == "/ترجمه": # اگر فقط /ترجمه بدون متن بود
        await translate(update, context)
        return
    if message_text.lower() == "/دانلود": # اگر فقط /دانلود بدون لینک بود
        await download(update, context)
        return

    # جستجوی لینک در پیام
    urls = re.findall(r'(https?://[^\s]+)', message_text)
    if urls:
        for url in urls:
            if is_media_url(url):
                await download(update, context, url=url)
                return # فقط اولین لینک رسانه ای را پردازش کن
            else:
                await update.message.reply_text("این لینک رسانه‌ای نیست و نمی‌تونم دانلودش کنم.")
                return # فقط اولین لینک غیر رسانه ای را گزارش کن
    
    # اگر نه دستور بود، نه ریپلای ترجمه، و نه لینک
    await update.message.reply_text("لطفاً لینک رسانه یا دستور معتبر بفرستید. برای راهنما: /help")


# تابع مدیریت خطاها
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا: {context.error}", exc_info=True) # exc_info=True برای نمایش کامل traceback
    if update and update.message:
        await update.message.reply_text("یه مشکلی پیش اومد! لطفاً دوباره امتحان کنید.")
    elif update and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="یه مشکلی پیش اومد! لطفاً دوباره امتحان کنید.")


# تابع اصلی
def main():
    application = Application.builder().token(TOKEN).build()

    # ثبت دستورات لاتین
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("translate", translate))
    application.add_handler(CommandHandler("download", download))
    
    # ثبت MessageHandler برای پیام های متنی که دستور نیستند (شامل کماندهای فارسی شبیه سازی شده و لینک ها)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # مدیریت خطاها
    application.add_error_handler(error_handler)

    # شروع ربات
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot stopped.")

if __name__ == "__main__":
    main()
    
