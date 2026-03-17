import sqlite3

def init_db():
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sent_news (url TEXT PRIMARY KEY)''')
    # Добавляем таблицу для хранения пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_new(url):
    # ... (твой текущий код функции остается без изменений) ...
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM sent_news WHERE url = ?', (url,))
    result = cursor.fetchone()
    if not result:
        cursor.execute('INSERT INTO sent_news VALUES (?)', (url,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# Новая функция добавления пользователя
def add_user(chat_id):
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users VALUES (?)', (chat_id,))
    conn.commit()
    conn.close()

# Новая функция получения списка всех пользователей
def get_all_users():
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users