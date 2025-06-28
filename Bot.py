import os
import re
import logging
import translators as ts
import requests # این ایمپورت اضافه است اگر استفاده نمیشود، حذف شود.
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, CallbackContext
from telegram.ext import filters # تغییر اصلی: ایمپورت filters با حرف کوچک
from telegram.constants import ChatMemberStatus # برای بررسی وضعیت ادمین

# ---------- تنظیمات اولیه ----------
# توکن باید از متغیر محیطی گرفته شود. نام متغیر محیطی را مثلاً BOT_TOKEN قرار دهید
TOKEN = os.environ.get("BOT_TOKEN") 
# توکن را مستقیماً اینجا نگذارید: "7465112074:AAFvmZgNFVWS5cdUEVmuFdgefKHB21SmblE" 
# اگر TOKEN خالی باشد، ربات کار نخواهد کرد
if not TOKEN:
    logging.error("Telegram BOT_TOKEN environment variable not set.")
    exit(1)

ADMINS = set()  # پر می‌شود هنگام اجرای ربات (اینجا موقت است)
WELCOME_IMAGE = None
WELCOME_CAPTION = "خوش آمدید به گروه!"
SPECIAL_USERS = set() # اینها اگر استفاده نمیشوند، حذف شوند.
SILENT_USERS = set() # اینها اگر استفاده نمیشوند، حذف شوند.
BANNED_USERS = set() # اینها اگر استفاده نمیشوند، حذف شوند.
MESSAGE_COUNT = {}
USER_ACTIVITY = {}

# ---------- لاگ ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- ابزار ----------
async def is_admin(update: Update, context: CallbackContext) -> bool:
    """بررسی می‌کند آیا کاربر ادمین گروه است یا خیر."""
    if not update.effective_chat:
        return False
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # برای اطمینان از اینکه ربات دسترسی دارد، بهتر است get_chat_member را امتحان کنیم
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def reply_error(update: Update, msg="خطا رخ داد."):
    """پاسخ خطا به کاربر."""
    try:
        await update.message.reply_text(msg)
    except Exception as e:
        logger.error(f"Failed to reply error message: {e}")

# ---------- مدیریت بن ----------
async def handle_ban(update: Update, context: CallbackContext):
    if not await is_admin(update, context): 
        await reply_error(update, "شما اجازه این کار را ندارید.")
        return
    
    try:
        text = update.message.text.strip().lower()
        user_id = None
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
        elif re.search(r"\d+", text):
            user_id = int(re.search(r"\d+", text).group())
        
        if user_id:
            BANNED_USERS.add(user_id) # این بن فقط در زمان اجرای ربات موقت است
            await update.message.reply_text("کاربر بن شد.")
            logger.info(f"User {user_id} has been banned.")
        else:
            await reply_error(update, "لطفاً روی پیام کاربر ریپلای کنید یا آیدی کاربر را بعد از دستور بن وارد کنید.")
    except Exception as e:
        logger.error(f"Error in handle_ban: {e}")
        await reply_error(update, "بن کردن با خطا مواجه شد.")

# ---------- ترجمه ----------
async def handle_translate(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        return await update.message.reply_text("لطفاً روی یک پیام ریپلای کنید.")
    
    try:
        original = update.message.reply_to_message.text
        if not original:
            return await update.message.reply_text("پیام ریپلای شده متنی نیست.")
            
        translated = ts.translate_text(original, to_language="fa")
        await update.message.reply_text(f"🔸 ترجمه:\n{translated}")
    except Exception as e:
        logger.error(f"Error in handle_translate: {e}")
        await reply_error(update, "در ترجمه خطایی رخ داد. (ممکن است API مترجم در دسترس نباشد)")

# ---------- خوش‌آمدگویی ----------
async def set_welcome_photo(update: Update, context: CallbackContext):
    if not await is_admin(update, context): 
        await reply_error(update, "شما اجازه این کار را ندارید.")
        return
    
    # اطمینان از وجود عکس و کپشن
    if update.message.photo and update.message.caption and "عکس خوش آمد گویی" in update.message.caption:
        global WELCOME_IMAGE
        WELCOME_IMAGE = update.message.photo[-1].file_id
        await update.message.reply_text("عکس خوش آمدگویی ذخیره شد.")
        logger.info(f"Welcome photo set: {WELCOME_IMAGE}")
    else:
        await reply_error(update, "لطفاً عکسی را با کپشن 'عکس خوش آمد گویی' ارسال کنید.")

async def welcome_user(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if member.id in BANNED_USERS:
            try:
                await context.bot.kick_chat_member(update.effective_chat.id, member.id)
                logger.info(f"Banned user {member.full_name} ({member.id}) tried to join and was kicked.")
                continue # به کاربر بن شده خوش‌آمد گفته نمیشود
            except Exception as e:
                logger.error(f"Failed to kick banned user {member.id}: {e}")
        
        if WELCOME_IMAGE:
            try:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=WELCOME_IMAGE, caption=WELCOME_CAPTION)
                logger.info(f"Welcome photo sent for {member.full_name}.")
            except Exception as e:
                logger.error(f"Failed to send welcome photo: {e}")
                await update.message.reply_text(f"{member.full_name} خوش آمدی! (خطا در ارسال عکس خوش‌آمدگویی)")
        else:
            await update.message.reply_text(f"{member.full_name} خوش آمدی!")
            logger.info(f"Welcome message sent for {member.full_name}.")

# ---------- پیام در گوشی ----------
async def handle_private_note(update: Update, context: CallbackContext):
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        message_text = update.message.text.replace("در گوشی", "").strip() # حذف "در گوشی" از متن
        if message_text:
            try:
                await context.bot.send_message(chat_id=target_id, text=f"📩 پیام در گوشی:\n{message_text}")
                await update.message.reply_text("پیام در گوشی ارسال شد.")
                logger.info(f"Private note sent from {update.effective_user.id} to {target_id}.")
            except Exception as e:
                logger.error(f"Failed to send private note: {e}")
                await reply_error(update, "خطا در ارسال پیام در گوشی.")
        else:
            await reply_error(update, "لطفاً متن پیام در گوشی را بعد از 'در گوشی' وارد کنید.")
    else:
        await reply_error(update, "برای ارسال پیام در گوشی، روی پیام شخص مورد نظر ریپلای کنید.")

# ---------- دانلودر (نمایشی) ----------
async def handle_download(update: Update, context: CallbackContext):
    if not update.message.reply_to_message: 
        return await reply_error(update, "لطفاً برای دانلود، روی پیام حاوی لینک ریپلای کنید.")
    
    text = update.message.reply_to_message.text
    if not text or not re.search(r"https?://", text): 
        return await reply_error(update, "پیام ریپلای شده حاوی لینک معتبری برای دانلود نیست.")
    
    # این بخش فقط نمایشی است و واقعاً دانلود نمی‌کند.
    if "دانلود" in update.message.text:
        await update.message.reply_text("⬇️ در حال دانلود... (نمایشی)")
        await update.message.reply_text("✅ فایل با موفقیت ارسال شد (نمایشی)")
        # بهتر است این حذف پیام را در یک بلوک try-except قرار دهید
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
            logger.info(f"Message {update.message.reply_to_message.message_id} deleted after mock download.")
        except Exception as e:
            logger.warning(f"Could not delete message after mock download: {e}")

# ---------- ضد لینک خالی ----------
async def anti_empty_link(update: Update, context: CallbackContext):
    if update.message.text and re.fullmatch(r"https?://\S+", update.message.text):
        if await is_admin(update, context): # ادمین‌ها لینک خالی می‌توانند بگذارند
            return
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
            logger.info(f"Empty link message from {update.effective_user.id} deleted.")
        except Exception as e:
            logger.warning(f"Could not delete empty link message: {e}")

# ---------- آمار ----------
async def update_stats(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    MESSAGE_COUNT[uid] = MESSAGE_COUNT.get(uid, 0) + 1
    # User activity should track per chat if multiple chats are supported
    USER_ACTIVITY[uid] = USER_ACTIVITY.get(uid, [])
    if update.message.date.hour not in USER_ACTIVITY[uid]:
        USER_ACTIVITY[uid].append(update.message.date.hour)
    logger.info(f"Stats updated for user {uid}. Message count: {MESSAGE_COUNT[uid]}")


async def handle_stats(update: Update, context: CallbackContext):
    total_today = sum(MESSAGE_COUNT.values())
    active_users = len([u for u in MESSAGE_COUNT if MESSAGE_COUNT[u] > 0])
    text = f"📊 آمار امروز:\nپیام‌ها: {total_today}\nاعضای فعال: {active_users}"
    await update.message.reply_text(text)
    logger.info(f"Stats requested by {update.effective_user.id}.")

async def handle_profile(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    count = MESSAGE_COUNT.get(uid, 0)
    hours = USER_ACTIVITY.get(uid, [])
    
    # محاسبه رتبه
    sorted_users = sorted(MESSAGE_COUNT.items(), key=lambda x: x[1], reverse=True)
    rank = 0
    for i, (user_id, msg_count) in enumerate(sorted_users):
        if user_id == uid:
            rank = i + 1
            break

    await update.message.reply_text(f"👤 پروفایل شما:\nنام: {name}\nتعداد پیام‌ها: {count}\nساعات فعالیت: {sorted(list(set(hours)))}\nرتبه: {rank}")
    logger.info(f"Profile requested by {uid}.")

# ---------- راه‌اندازی ----------
def main():
    # Updater بدون use_context=True در نسخه های جدید
    updater = Updater(token=TOKEN) 
    dp = updater.dispatcher

    # Handler ها باید به ترتیب دقیق باشند و از filters.TEXT به جای Filters.text استفاده شود.
    # و از CommandHandler برای دستورات مشخص استفاده شود.

    # CommandHandler ها برای دستورات /start, /ban, /stats, /profile, /translate, /download, /private_note
    dp.add_handler(CommandHandler("ban", handle_ban)) # /ban
    dp.add_handler(CommandHandler("stats", handle_stats)) # /stats
    dp.add_handler(CommandHandler("profile", handle_profile)) # /profile
    dp.add_handler(CommandHandler("translate", handle_translate)) # /translate
    dp.add_handler(CommandHandler("download", handle_download)) # /download
    dp.add_handler(CommandHandler("note", handle_private_note)) # /note (نام دستور را به /note تغییر دادم)

    # MessageHandler برای خوش‌آمدگویی اعضای جدید
    dp.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_user))
    
    # MessageHandler برای تنظیم عکس خوش‌آمدگویی با کپشن
    dp.add_handler(MessageHandler(filters.PHOTO & filters.CAPTION, set_welcome_photo))
    
    # MessageHandler برای به‌روزرسانی آمار پیام‌ها (غیر از دستورات)
    dp.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_stats))
    
    # MessageHandler برای حذف لینک‌های خالی (غیر از دستورات)
    # این باید بعد از update_stats باشد تا پیام قبل از حذف شدن در آمار ثبت شود
    dp.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_empty_link))
    
    # اگر دستورات دیگری دارید که با `in text` بررسی می‌شوند، باید آن‌ها را به CommandHandler تبدیل کنید
    # یا مطمئن شوید که تداخلی با CommandHandler های بالا ندارند.
    # توصیه می‌شود از CommandHandler برای همه دستورات استفاده کنید.

    logger.info("Bot started polling...")
    updater.start_polling()
    updater.idle()
    logger.info("Bot stopped.")

if __name__ == '__main__':
    main()

