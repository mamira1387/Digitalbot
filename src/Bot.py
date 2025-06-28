import os
import re
import logging
import translators as ts
import requests
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# ---------- تنظیمات اولیه ----------
TOKEN = os.environ.get("7465112074:AAFvmZgNFVWS5cdUEVmuFdgefKHB21SmblE")  # توکن از محیط گرفته می‌شود
ADMINS = set()  # پر می‌شود هنگام اجرای ربات
WELCOME_IMAGE = None
WELCOME_CAPTION = "خوش آمدی به گروه!"
SPECIAL_USERS = set()
SILENT_USERS = set()
BANNED_USERS = set()
MESSAGE_COUNT = {}
USER_ACTIVITY = {}

# ---------- لاگ ----------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------- ابزار ----------
def is_admin(update: Update):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    member = update.effective_chat.get_member(user_id)
    return member.status in ["administrator", "creator"]

def reply_error(update: Update, msg="خطا رخ داد."):
    try:
        update.message.reply_text(msg)
    except Exception:
        pass

# ---------- مدیریت بن ----------
def handle_ban(update: Update, context: CallbackContext):
    if not is_admin(update): return
    try:
        text = update.message.text.strip().lower()
        user_id = None
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
        elif re.search(r"\d+", text):
            user_id = int(re.search(r"\d+", text).group())
        if user_id:
            BANNED_USERS.add(user_id)
            update.message.reply_text("کاربر بن شد.")
    except Exception:
        reply_error(update, "بن کردن با خطا مواجه شد.")

# ---------- ترجمه ----------
def handle_translate(update: Update, context: CallbackContext):
    if not update.message.reply_to_message:
        return update.message.reply_text("لطفاً روی یک پیام ریپلای کنید.")
    try:
        original = update.message.reply_to_message.text
        translated = ts.translate_text(original, to_language="fa")
        update.message.reply_text(f"🔸 ترجمه:\n{translated}")
    except Exception:
        reply_error(update, "در ترجمه خطایی رخ داد.")

# ---------- خوش‌آمدگویی ----------
def set_welcome_photo(update: Update, context: CallbackContext):
    if not is_admin(update): return
    if update.message.caption and "عکس خوش آمد گویی" in update.message.caption:
        global WELCOME_IMAGE
        WELCOME_IMAGE = update.message.photo[-1].file_id
        update.message.reply_text("عکس خوش آمدگویی ذخیره شد.")

def welcome_user(update: Update, context: CallbackContext):
    for member in update.message.new_chat_members:
        if WELCOME_IMAGE:
            context.bot.send_photo(chat_id=update.effective_chat.id, photo=WELCOME_IMAGE, caption=WELCOME_CAPTION)
        else:
            update.message.reply_text(f"{member.full_name} خوش آمدی!")

# ---------- پیام در گوشی ----------
def handle_private_note(update: Update, context: CallbackContext):
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        context.bot.send_message(chat_id=target_id, text=f"📩 پیام در گوشی:\n{update.message.text}")

# ---------- دانلودر ----------
def handle_download(update: Update, context: CallbackContext):
    if not update.message.reply_to_message: return
    text = update.message.reply_to_message.text
    if not re.search(r"https?://", text): return
    if "دانلود" in update.message.text:
        update.message.reply_text("⬇️ در حال دانلود... (نمایشی)")
        update.message.reply_text("✅ فایل با موفقیت ارسال شد (نمایشی)")
        context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)

# ---------- ضد لینک خالی ----------
def anti_empty_link(update: Update, context: CallbackContext):
    if re.fullmatch(r"https?://\S+", update.message.text):
        try:
            context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except:
            pass

# ---------- آمار ----------
def update_stats(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    MESSAGE_COUNT[uid] = MESSAGE_COUNT.get(uid, 0) + 1
    USER_ACTIVITY[uid] = USER_ACTIVITY.get(uid, []) + [update.message.date.hour]

def handle_stats(update: Update, context: CallbackContext):
    total_today = sum(MESSAGE_COUNT.values())
    active_users = len([u for u in MESSAGE_COUNT if MESSAGE_COUNT[u] > 0])
    text = f"📊 آمار امروز:\nپیام‌ها: {total_today}\nاعضای فعال: {active_users}"
    update.message.reply_text(text)

def handle_profile(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    count = MESSAGE_COUNT.get(uid, 0)
    hours = USER_ACTIVITY.get(uid, [])
    rank = sorted(MESSAGE_COUNT.items(), key=lambda x: x[1], reverse=True).index((uid, count)) + 1
    update.message.reply_text(f"👤 پروفایل شما:\nنام: {name}\nتعداد پیام‌ها: {count}\nساعات فعالیت: {set(hours)}\nرتبه: {rank}")

# ---------- فیلتر دستورات ----------
def handle_commands(update: Update, context: CallbackContext):
    text = update.message.text.lower()
    if "بن" in text: handle_ban(update, context)
    elif "آمار" in text: handle_stats(update, context)
    elif "پروفایل" in text: handle_profile(update, context)
    elif "در گوشی" in text: handle_private_note(update, context)
    elif "ترجمه" in text: handle_translate(update, context)
    elif "دانلود" in text: handle_download(update, context)

# ---------- راه‌اندازی ----------
def main():
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, welcome_user))
    dp.add_handler(MessageHandler(Filters.photo & Filters.caption, set_welcome_photo))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, update_stats))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, anti_empty_link))
    dp.add_handler(MessageHandler(Filters.text, handle_commands))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
