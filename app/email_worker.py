"""Почасовая рассылка исходных новостей через SMTP."""

import asyncio
import logging
import smtplib
import ssl
from contextlib import suppress
from email.message import EmailMessage
from email.utils import formatdate
from html import escape

from psycopg import Error

from config import EMAIL_PASSWORD, EMAIL_RECIPIENT, EMAIL_SENDER, KEYWORDS, LOG_LEVEL, SMTP_PORT, SMTP_SERVER

from .database import connect_async, try_lock_async

logger = logging.getLogger(__name__)
EMAIL_LOCK = 51005
POLL_SECONDS = 60


def format_digest(rows):
    message = EmailMessage()
    message["Subject"] = f"🔔 Ecom новости: {len(rows)} новых публикаций"
    message["From"] = EMAIL_SENDER
    message["To"] = EMAIL_RECIPIENT
    message["Date"] = formatdate()
    heading = "Свежие новости по вашим ключевым словам"
    plain = [heading]
    html = [f"<h2>{heading}</h2>"]
    for row in rows:
        plain.append(f'{row["source_name"]} — {row["header"]}\n{row["source"]}\n\n{row["text"]}')
        source_name = escape(row["source_name"])
        title = escape(row["header"])
        url = escape(row["source"])
        text = escape(row["text"]).replace("\n", "<br>\n")
        html.append(f'<h3>{source_name} — <a href="{url}">{title}</a></h3><p>{text}</p>')
    message.set_content("\n\n".join(plain))
    message.add_alternative("\n".join(html), subtype="html")
    return message


def send_digest(rows):
    message = format_digest(rows)
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20)
    try:
        server.starttls(context=ssl.create_default_context())
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(message, from_addr=EMAIL_SENDER, to_addrs=[EMAIL_RECIPIENT])
        # Если SMTP уже принял письмо, ошибка команды QUIT не должна вызвать повторную отправку.
        with suppress(OSError):
            server.quit()
    finally:
        server.close()


async def publish_digest(db):
    cursor = await db.execute(
        """
        SELECT id, header, text, source, source_name
        FROM raw_news
        WHERE email_sent_at IS NULL
          AND published_at BETWEEN now() - interval '24 hours' AND now()
          AND created_at < date_trunc('hour', now(), 'UTC')
          AND EXISTS (
              SELECT FROM unnest(%s::text[]) AS keywords(word)
              WHERE strpos(lower(raw_news.header), word) > 0
          )
        ORDER BY published_at DESC, id
        """,
        (KEYWORDS,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return

    await asyncio.to_thread(send_digest, rows)
    await db.execute(
        "UPDATE raw_news SET email_sent_at = now() WHERE id = ANY(%s)",
        ([row["id"] for row in rows],),
    )
    logger.info("Письмо с исходными новостями отправлено, публикаций: %s", len(rows))


async def run():
    while True:
        try:
            async with await connect_async() as db:
                async with try_lock_async(db, EMAIL_LOCK) as acquired:
                    if acquired:
                        await publish_digest(db)
        except Error:
            logger.exception("Ошибка PostgreSQL при рассылке новостей")
        except OSError as error:
            logger.warning("Не удалось отправить письмо (%s). Повтор через минуту.", type(error).__name__)
        await asyncio.sleep(POLL_SECONDS)


def main():
    logging.basicConfig(level=LOG_LEVEL)
    settings = (EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT)
    if not any(settings):
        logger.info("Для рассылки задайте EMAIL_SENDER, EMAIL_PASSWORD и EMAIL_RECIPIENT.")
        return
    if not all(settings):
        raise SystemExit("Для рассылки нужны EMAIL_SENDER, EMAIL_PASSWORD и EMAIL_RECIPIENT.")
    asyncio.run(run())


if __name__ == "__main__":
    main()
