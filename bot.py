import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler

from config import SOURCES, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT
from parser import get_updates
from database import init_db, is_new

# ---------- НАСТРОЙКИ SMTP ----------
# ---------- НАСТРОЙКИ SMTP (Яндекс) ----------
SMTP_SERVER = "smtp.yandex.ru"  # Сервер Яндекса
SMTP_PORT = 587                  # Порт с поддержкой TLS

def send_email(subject, body_html):
    """Отправляет письмо через Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT

    part = MIMEText(body_html, "html")
    msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print(f"[OK] Письмо отправлено: {subject}")
    except Exception as e:
        print(f"[ERROR] Ошибка отправки письма: {e}")

def send_news():
    """Основная функция, вызываемая по расписанию."""
    print("Запуск проверки новостей...")
    raw_news = get_updates(SOURCES)

    # Отбираем только новые ссылки
    new_items = []
    for item in raw_news:
        if is_new(item["link"]):
            new_items.append(item)

    if not new_items:
        print("Новых новостей не найдено.")
        return

    # Формируем HTML‑письмо
    subject = f"🔔 Ecom новости: {len(new_items)} новых публикаций"
    html_parts = ["<h2>Свежие новости по вашим ключевым словам:</h2><ul>"]
    for item in new_items:
        html_parts.append(
            f'<li><b>{item["source"]}</b>: '
            f'<a href="{item["link"]}">{item["title"]}</a></li>'
        )
    html_parts.append("</ul>")
    html_body = "\n".join(html_parts)

    send_email(subject, html_body)
    print(f"Отправлено {len(new_items)} новостей на {EMAIL_RECIPIENT}")

# ---------- ЗАПУСК ПЛАНИРОВЩИКА ----------
if __name__ == "__main__":
    init_db()                     # создаём таблицу sent_news, если её нет

    scheduler = BackgroundScheduler()
    scheduler.add_job(send_news, "cron", minute=0)   # каждый час в 00 минут
    scheduler.start()

    print("Планировщик запущен. Ожидание времени рассылки...")
    print(f"Новости будут отправляться на {EMAIL_RECIPIENT}")

    try:
        while True:
            time.sleep(60)       # держим скрипт активным
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("Планировщик остановлен.")