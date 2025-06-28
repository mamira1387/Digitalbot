import logging
import os
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

# توکن ربات (از BotFather بگیرید و اینجا قرار بدید)
TOKEN = os.getenv("TELEGRAM_TOKEN")  # برای Render، توکن رو در متغیرهای محیطی تنظیم کنید

# تنظیم مسیر برای ذخیره فایل‌های دانلود شده
DOWNLOAD_PATH = "downloads"
if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH)

# شیء مترجم
translator = Translator()

# تابع شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! من DigitalBot هستم. می‌تونم متن‌ها رو به فارسی ترجمه کنم و ویدیو از یوتیوب، اینستاگرام و تیک‌تاک دانلود کنم.\n"
        "دستورات:\n"
        "/translate <متن> - ترجمه متن به فارسی\n"
        "/download <لینک> - دانلود ویدیو از یوتیوب، اینستا یا تیک‌تاک\n"
        "/help - راهنما"
    )

# تابع راهنما
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات من:\n"
        "/start - شروع ربات\n"
        "/translate <متن> - ترجمه متن به فارسی (زبان مبدا خودکار تشخیص داده می‌شه)\n"
        "/download <لینک> - دانلود ویدیو از یوتیوب، اینستاگرام یا تیک‌تاک\n"
        "مثال:\n"
        "/translate Hello, how are you?\n"
        "/download https://www.youtube.com/watch?v=example"
    )

# تابع ترجمه
async def translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفاً متنی برای ترجمه وارد کنید. مثال:\n/translate Hello")
        return

    text = " ".join(context.args)
    try:
        # ترجمه به فارسی
        translation = translator.translate(text, dest="fa")
        await update.message.reply_text(
            f"متن: {translation.origin}\n"
            f"زبان مبدا: {LANGUAGES.get(translation.src, 'ناشناخته')}\n"
            f"ترجمه به فارسی: {translation.text}"
        )
    except Exception as e:
        logger.error(f"خطا در ترجمه: {e}")
        await update.message.reply_text("خطایی در ترجمه رخ داد. لطفاً دوباره امتحان کنید.")

# تابع دانلود
async def download(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("لطفاً لینک ویدیو رو وارد کنید. مثال:\n/download https://www.youtube.com/watch?v=example")
        return

    url = context.args[0]
    try:
        # تنظیمات yt-dlp
        ydl_opts = {
            "outtmpl": f"{DOWNLOAD_PATH}/%(title)s.%(ext)s",
            "format": "best",
            "quiet": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        # ارسال فایل به کاربر
        with open(file_path, "rb") as file:
            await update.message.reply_document(document=file, caption="ویدیو دانلود شد!")
        
        # حذف فایل بعد از ارسال (برای صرفه‌جویی در فضا)
        os.remove(file_path)
    except Exception as e:
        logger.error(f"خطا در دانلود: {e}")
        await update.message.reply_text("خطایی در دانلود رخ داد. مطمئن بشید لینک معتبره و دوباره امتحان کنید.")

# تابع مدیریت خطاها
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطا: {context.error}")
    if update and update.message:
        await update.message.reply_text("یه مشکلی پیش اومد! لطفاً دوباره امتحان کنید.")

# تابع اصلی برای اجرا
def main():
    # ایجاد اپلیکیشن ربات
    application = Application.builder().token(TOKEN).build()

    # ثبت دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("translate", translate))
    application.add_handler(CommandHandler("download", download))

    # مدیریت خطاها
    application.add_error_handler(error_handler)

    # شروع ربات
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
