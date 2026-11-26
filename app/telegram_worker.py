"""Публикация свежих обработанных новостей через Telegram Bot API."""

import asyncio
import logging
from html import escape
from re import fullmatch

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    ClientDecodeError,
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.types import LinkPreviewOptions
from aiogram.utils.token import TokenValidationError
from aiohttp import ClientConnectorError
from psycopg import Error

from config import LOG_LEVEL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_CHANNEL_NAME, TELEGRAM_CHANNEL_URL

from .database import connect_async, try_lock_async
from .footnotes import attach_footnotes

logger = logging.getLogger(__name__)
TELEGRAM_LOCK = 51004
POLL_SECONDS = 5
RETRY_SECONDS = 60


def format_post(row):
    text, notes = attach_footnotes(row["text"], row["source_footnotes"])
    source = f'<a href="{escape(row["source"])}">{escape(row["source_name"])}</a>'
    name = escape(TELEGRAM_CHANNEL_NAME)
    if TELEGRAM_CHANNEL_URL:
        name = f'<a href="{escape(TELEGRAM_CHANNEL_URL)}">{name}</a>'
    paragraphs = [f"{escape(text.rstrip('.'))}, — {source}."]
    if notes:
        paragraphs.append("\n".join(f'{escape(note["marker"])} {escape(note["text"])}' for note in notes))
    paragraphs.append(f"⚡️ {name}")
    return "\n\n".join(paragraphs)


async def claim(db):
    cursor = await db.execute(
        """
        WITH candidate AS (
            SELECT n.id, n.text, r.source, r.source_name, r.source_footnotes
            FROM news n JOIN raw_news r ON r.id = n.raw_news_id
            WHERE r.checked AND r.is_ecom AND NOT n.is_posted
              AND n.telegram_next_attempt_at <= now()
              AND r.published_at BETWEEN now() - interval '24 hours' AND now()
            ORDER BY n.id LIMIT 1 FOR UPDATE OF n SKIP LOCKED
        )
        UPDATE news n SET telegram_next_attempt_at = NULL
        FROM candidate c WHERE n.id = c.id RETURNING c.*
        """
    )
    return await cursor.fetchone()


async def defer(db, news_id, delay):
    await db.execute(
        "UPDATE news SET telegram_next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s",
        (delay, news_id),
    )
    return delay


async def publish_next(db, bot, channel):
    row = await claim(db)
    if row is None:
        return POLL_SECONDS

    news_id = row["id"]
    try:
        message = await bot.send_message(
            chat_id=channel,
            text=format_post(row),
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramRetryAfter as error:
        logger.warning("Telegram ограничил частоту отправки для news_id=%s", news_id)
        return await defer(db, news_id, max(1, error.retry_after))
    except (TelegramUnauthorizedError, TelegramForbiddenError, TelegramNotFound):
        logger.warning("Telegram отклонил доступ. Проверьте токен, канал и права бота на публикацию.")
        return await defer(db, news_id, RETRY_SECONDS)
    except TelegramBadRequest as error:
        if "chat not found" in error.message.lower():
            logger.warning("Telegram не нашёл канал. Проверьте TELEGRAM_CHANNEL_ID и доступ бота.")
            return await defer(db, news_id, RETRY_SECONDS)
        logger.warning("Telegram отклонил публикацию news_id=%s. Запись требует проверки.", news_id)
        return 0
    except (TelegramAPIError, ClientDecodeError) as error:
        if isinstance(error, TelegramNetworkError) and isinstance(error.__cause__, ClientConnectorError):
            logger.warning("Не удалось подключиться к Telegram для news_id=%s", news_id)
            return await defer(db, news_id, RETRY_SECONDS)
        logger.warning("Исход отправки news_id=%s неизвестен (%s). Запись требует проверки.",
                       news_id, type(error).__name__)
        return POLL_SECONDS

    logger.info("Telegram подтвердил news_id=%s, message_id=%s", news_id, message.message_id)
    await db.execute(
        "UPDATE news SET is_posted = true, telegram_message_id = %s WHERE id = %s",
        (message.message_id, news_id),
    )
    return 0


async def run(bot, channel):
    async with bot:
        while True:
            delay = POLL_SECONDS
            try:
                async with await connect_async() as db:
                    async with try_lock_async(db, TELEGRAM_LOCK) as acquired:
                        if acquired:
                            delay = await publish_next(db, bot, channel)
            except Error:
                logger.exception("Ошибка PostgreSQL при публикации в Telegram")
            await asyncio.sleep(delay)


def main():
    logging.basicConfig(level=LOG_LEVEL)
    if not TELEGRAM_BOT_TOKEN and not TELEGRAM_CHANNEL_ID:
        logger.info("Для публикации задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID.")
        return
    if not TELEGRAM_BOT_TOKEN or not fullmatch(r"@[a-zA-Z0-9_]{1,32}|-[1-9][0-9]{0,15}", TELEGRAM_CHANNEL_ID):
        raise SystemExit("Укажите токен бота и TELEGRAM_CHANNEL_ID в формате @username или отрицательного ID.")
    channel = int(TELEGRAM_CHANNEL_ID) if TELEGRAM_CHANNEL_ID.startswith("-") else TELEGRAM_CHANNEL_ID
    try:
        bot = Bot(TELEGRAM_BOT_TOKEN, session=AiohttpSession(timeout=15))
    except TokenValidationError:
        raise SystemExit("Некорректный формат TELEGRAM_BOT_TOKEN.") from None
    asyncio.run(run(bot, channel))


if __name__ == "__main__":
    main()
