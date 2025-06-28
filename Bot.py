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
import requests

# تنظیم لاگینگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات (از BotFather بگیرید و در متغیرهای محیطی Render تنظیم کنید)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# تنظیم مسیر برای ذخیره فایل‌های دانلود شده
DOWNLOAD_PATH = "downloads"
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# شیء مترجم
translator = Translator()

# تابع بررسی لینک رسانه
def is_media_url(url):
    media_domains = [
        "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
        "twitter.com", "x.com", "facebook.com"
    ]
    return any(domain in url.lower() for domain in media_domains)

# تابع شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من DigitalBot هستم. می‌تونم متن‌ها رو به فارسی ترجمه کنم و از یوتیوب، اینستاگرام و تیک‌تاک ویدیو دانلود کنم.\n"
        "دستورات:\n"
        "/شروع یا /start - شروع ربات\n"
        "/راهنما یا /help - نمایش راهنما\n"
        "/ترجمه یا /translate <متن> - ترجمه متن به فارسی\n"
        "/دانلود یا /download <لینک> - دانلود ویدیو\n"
        "یا فقط لینک بفرستید تا خودم تشخیص بدم!\n"
        "برای ترجمه پیام، روی پیام ریپلای کنید و بنویسید 'ترجمه'"
    )

# تابع راهنما
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات من:\n"
        "/شروع یا /start - شروع ربات\n"
        "/راهنما یا /help - نمایش این راهنما\n"
        "/ترجمه یا /translate <متن> - ترجمه متن به فارسی\n"
        "/دانلود یا /download <لینک> - دانلود ویدیو از یوتیوب، اینستا یا تیک‌تاک\n"
        "یا فقط لینک بفرستید تا خودم بررسی کنم.\n"
        "برای ترجمه پیام، روی پیام ریپلای کنید و بنویسید 'ترجمه'."
    )

# تابع ترجمه
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        text = " ".join(context.args)
    elif update.message.reply_to_message and update.message.text.lower() in ["ترجمه", "/ترجمه", "/translate"]:
        if update.message.reply_to_message.text:
            text = update.message.reply_to_message.text
        else:
            await update.message.reply_text("پیام ریپلای‌شده متن نداره!")
            return
    else:
        await update.message.reply_text("لطفاً متنی برای ترجمه وارد کنید یا روی پیام ریپلای کنید و بنویسید 'ترجمه'.\nمثال: /ترجمه Hello")
        return

    try:
        translation = translator.translate(text, dest="fa")
        await update.message.reply_text(
            f"متن: {translation.origin}\n"
            f"زبان مبدا: {LANGUAGES.get(translation.src, 'ناشناخته')}\n"
            f"ترجمه به فارسی: {translation.text}"
        )
    except Exception as e:
        logger.error(f"خطا در ترجمه: {e}")
        await update.message.reply_text("خطایی در ترجمه رخ داد. دوباره امتحان کنید.")

# تابع دانلود
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE, url=None):
    if not url and not context.args:
        await update.message.reply_text("لطفاً لینک ویدیو رو وارد کنید. مثال:\n/دانلود https://www.youtube.com/watch?v=example")
        return

    url = url or context.args[0]
    try:
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_PATH}/%(title)s.%(ext)s",
            "format": "best",
            "quiet": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        with open(file_path, "rb") as file:
            await update.message.reply_document(document=file, caption="ویدیو دانلود شد!")
        
        os.remove(file_path)  # حذف فایل بعد از ارسال
    except Exception as e:
        logger.error(f"خطا در دانلود: {e}")
        await update.message.reply_text("خطایی در دانلود رخ داد. مطمئن بشید لینک معتبره.")

# تابع شناسایی خودکار لینک
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    if update.message.reply_to_message and message_text.lower() in ["ترجمه", "/ترجمه", "/translate"]:
        await translate(update, context)
        return

    # جستجوی لینک در پیام
    urls = re.findall(r'(https?://[^\s]+)', message_text)
    if urls:
        for url in urls:
            if is_media_url(url):
                await download(update, context, url=url)
            else:
                await update.message.reply_text("این لینک رسانه‌ای نیست و نمی‌تونم دانلودش کنم.")
    elif message_text.lower() not in ["ترجمه", "/ترجمه", "/translate"]:
        await update.message.reply_text("لطفاً لینک رسانه یا دستور معتبر بفرستید. برای راهنما: /راهنما")

# تابع مدیریت خطاها
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا: {context.error}")
    if update and update.message:
        await update.message.reply_text("یه مشکلی پیش اومد! لطفاً دوباره امتحان کنید.")

# تابع اصلی
def main():
    application = Application.builder().token(TOKEN).build()

    # ثبت دستورات
    application.add_handler(CommandHandler(["start", "شروع"], start))
    application.add_handler(CommandHandler(["help", "راهنما"], help_command))
    application.add_handler(CommandHandler(["translate", "ترجمه"], translate))
    application.add_handler(CommandHandler(["download", "دانلود"], download))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # مدیریت خطاها
    application.add_error_handler(error_handler)

    # شروع ربات
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
