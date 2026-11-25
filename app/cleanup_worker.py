"""Удаление просроченных данных с сохранением исходников действующих новостей."""

import asyncio
import logging

from psycopg import Error

from config import LOG_LEVEL, NEWS_CLEANUP_INTERVAL_MINUTES, NEWS_RETENTION_DAYS

from .database import SEARCH_LOCK, connect_async, try_lock_async

logger = logging.getLogger(__name__)


async def clean(db):
    async with try_lock_async(db, SEARCH_LOCK) as acquired:
        if not acquired:
            return False
        async with db.transaction():
            removed = await db.execute(
                """
                WITH deleted AS (
                    DELETE FROM news WHERE created_at <= now() - make_interval(days => %s) RETURNING id
                )
                INSERT INTO search_outbox (news_id, operation)
                SELECT id, 'delete' FROM deleted
                ON CONFLICT (news_id) DO UPDATE SET operation = 'delete',
                    attempts = 0, next_attempt_at = now()
                """,
                (NEWS_RETENTION_DAYS,),
            )
            raw = await db.execute(
                """
                DELETE FROM raw_news r
                WHERE r.created_at <= now() - make_interval(days => %s)
                  AND NOT EXISTS (SELECT FROM news n WHERE n.raw_news_id = r.id)
                  AND (r.claim_until IS NULL OR r.claim_until <= now())
                """,
                (NEWS_RETENTION_DAYS,),
            )
        logger.info("Очистка: news=%s, raw_news=%s", removed.rowcount, raw.rowcount)
        return True


async def run():
    while True:
        try:
            async with await connect_async() as db:
                complete = await clean(db)
        except Error:
            logger.exception("Ошибка PostgreSQL при очистке")
            complete = False
        await asyncio.sleep(NEWS_CLEANUP_INTERVAL_MINUTES * 60 if complete else 10)


def main():
    logging.basicConfig(level=LOG_LEVEL)
    if NEWS_CLEANUP_INTERVAL_MINUTES <= 0:
        raise ValueError("NEWS_CLEANUP_INTERVAL_MINUTES должен быть положительным")
    asyncio.run(run())


if __name__ == "__main__":
    main()
