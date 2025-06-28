import sqlite3
import json
import datetime

DATABASE_NAME = 'digitalbot.db'

def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Table for Welcome Settings
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS welcome_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_text TEXT,
            welcome_photo_id TEXT
        )
    ''')

    # Table for User Statistics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            chat_id INTEGER,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            message_count INTEGER DEFAULT 0,
            last_activity TEXT, -- YYYY-MM-DD
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    
    # Table for Daily User Activity (to track active/inactive days)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_activity (
            chat_id INTEGER,
            user_id INTEGER,
            activity_date TEXT, -- YYYY-MM-DD
            message_count_day INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id, activity_date)
        )
    ''')

    conn.commit()
    conn.close()

def get_welcome_settings(chat_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT welcome_text, welcome_photo_id FROM welcome_settings WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return result # (welcome_text, welcome_photo_id) or None

def set_welcome_settings(chat_id, welcome_text, welcome_photo_id=None):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO welcome_settings (chat_id, welcome_text, welcome_photo_id)
        VALUES (?, ?, ?)
    ''', (chat_id, welcome_text, welcome_photo_id))
    conn.commit()
    conn.close()

def update_user_stats(chat_id, user_id, username, full_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    today = datetime.date.today().isoformat() # YYYY-MM-DD
    
    # Update main user_stats table
    cursor.execute('''
        INSERT OR IGNORE INTO user_stats (chat_id, user_id, username, full_name, last_activity)
        VALUES (?, ?, ?, ?, ?)
    ''', (chat_id, user_id, username, full_name, today))
    
    cursor.execute('''
        UPDATE user_stats
        SET message_count = message_count + 1,
            last_activity = ?,
            username = ?,
            full_name = ?
        WHERE chat_id = ? AND user_id = ?
    ''', (today, username, full_name, chat_id, user_id))
    
    # Update daily_activity table
    cursor.execute('''
        INSERT OR IGNORE INTO daily_activity (chat_id, user_id, activity_date, message_count_day)
        VALUES (?, ?, ?, 0)
    ''', (chat_id, user_id, today))
    
    cursor.execute('''
        UPDATE daily_activity
        SET message_count_day = message_count_day + 1
        WHERE chat_id = ? AND user_id = ? AND activity_date = ?
    ''', (chat_id, user_id, today))

    conn.commit()
    conn.close()

def get_all_user_stats(chat_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, full_name, message_count, last_activity
        FROM user_stats
        WHERE chat_id = ?
        ORDER BY message_count DESC
    ''', (chat_id,))
    results = cursor.fetchall()
    conn.close()
    return results

def get_user_daily_activity(chat_id, user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT activity_date, message_count_day
        FROM daily_activity
        WHERE chat_id = ? AND user_id = ?
        ORDER BY activity_date DESC
    ''', (chat_id, user_id))
    results = cursor.fetchall()
    conn.close()
    return results

# Initialize the database when this module is imported
init_db()

