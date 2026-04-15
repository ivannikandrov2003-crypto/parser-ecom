import sqlite3

def init_db():
    conn = sqlite3.connect('news.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS sent_news (url TEXT PRIMARY KEY)''')
    conn.commit()
    conn.close()

def is_new(url):
    """Проверяет, не было ли ссылки уже отправлено. Если нет – добавляет в БД и возвращает True."""
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