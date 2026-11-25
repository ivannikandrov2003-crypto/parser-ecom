"""Асинхронная классификация и запуск очереди Elasticsearch."""

import asyncio
import logging
from contextlib import ExitStack, closing
from uuid import uuid4

from elasticsearch import AsyncElasticsearch
from psycopg import Error
from psycopg.types.json import Jsonb

from config import AI_POLL_SECONDS, ES_URL, LOG_LEVEL, NEWS_DUPLICATE_MIN_MATCHES, NEWS_MAX_KEYWORDS

from .database import connect_async
from .gigachat_client import GigaChatClient, GigaChatError, GigaChatResponseError
from .search import sync_next

logger = logging.getLogger(__name__)
MAX_INVALID_RESPONSES = 3


async def claim(db):
    cursor = await db.execute(
        """
        WITH candidate AS (
            SELECT id FROM raw_news r
            WHERE NOT checked AND classification_failed_at IS NULL AND next_attempt_at <= now()
              AND (claim_until IS NULL OR claim_until <= now())
              AND ai_summary IS NULL
            ORDER BY next_attempt_at, id
            LIMIT 1 FOR UPDATE SKIP LOCKED
        )
        UPDATE raw_news r SET claim_token = %s, claim_until = now() + interval '10 minutes',
            attempts = attempts + 1
        FROM candidate c WHERE r.id = c.id
        RETURNING r.id, header, text, claim_token, attempts, is_feed_excerpt
        """,
        (uuid4(),),
    )
    return await cursor.fetchone()


async def release_for_retry(db, article, *, invalid_response, minimum_delay=5):
    delay = max(minimum_delay, min(5 * 2 ** min(article["attempts"] - 1, 8), 900))
    cursor = await db.execute(
        """
        UPDATE raw_news SET claim_token = NULL, claim_until = NULL,
            next_attempt_at = now() + make_interval(secs => %s),
            classification_failures = classification_failures + %s,
            classification_failed_at = CASE WHEN classification_failures + %s >= %s THEN now() END
        WHERE id = %s AND claim_token = %s
        RETURNING classification_failed_at
        """,
        (delay, int(invalid_response), int(invalid_response), MAX_INVALID_RESPONSES,
         article["id"], article["claim_token"]),
    )
    row = await cursor.fetchone()
    if row and row["classification_failed_at"]:
        logger.warning("Классификация raw_news_id=%s требует проверки", article["id"])


async def save_classification(db, article, *, is_ecom, summary, keywords):
    updated = await db.execute(
        """
        UPDATE raw_news SET is_ecom = %s, keywords = %s, ai_summary = %s, checked = %s,
            claim_token = NULL, claim_until = NULL, next_attempt_at = now(),
            classification_failures = 0, classification_failed_at = NULL
        WHERE id = %s AND claim_token = %s AND claim_until > now()
        """,
        (is_ecom, Jsonb(keywords), summary, not is_ecom, article["id"], article["claim_token"]),
    )
    if not updated.rowcount:
        return
    logger.info("Классификация raw_news_id=%s, попытка=%s, ecom=%s",
                article["id"], article["attempts"], is_ecom)


async def classify_next(db, giga):
    article = await claim(db)
    if article is None:
        return False

    try:
        result = await asyncio.to_thread(
            giga.classify, article["header"], article["text"], is_feed_excerpt=article["is_feed_excerpt"],
        )
        await save_classification(
            db, article, is_ecom=result.is_ecom, summary=result.text, keywords=result.keywords,
        )
    except GigaChatError as error:
        logger.warning("Классификация raw_news_id=%s, попытка=%s: %s", article["id"], article["attempts"], error)
        provider_unavailable = error.status_code in {401, 402, 403, 429}
        await release_for_retry(
            db, article, invalid_response=isinstance(error, GigaChatResponseError),
            minimum_delay=60 if provider_unavailable else 5,
        )
        if provider_unavailable:
            raise
    return True


async def run_queue(run_next, *args):
    while True:
        delay = AI_POLL_SECONDS
        try:
            async with await connect_async() as db:
                while await run_next(db, *args):
                    pass
        except Error:
            logger.exception("Ошибка PostgreSQL в очереди %s", run_next.__name__)
        except GigaChatError:
            delay = max(delay, 30)
        await asyncio.sleep(delay)


async def run():
    with ExitStack() as resources:
        try:
            giga = resources.enter_context(closing(GigaChatClient()))
        except GigaChatError as error:
            logger.warning("%s", error)
            giga = None

        async with AsyncElasticsearch(ES_URL, request_timeout=5, max_retries=0) as elastic:
            if giga is None:
                await run_queue(sync_next, elastic)
            else:
                await asyncio.gather(run_queue(classify_next, giga), run_queue(sync_next, elastic))


def main():
    logging.basicConfig(level=LOG_LEVEL)
    if AI_POLL_SECONDS <= 0 or not 1 <= NEWS_DUPLICATE_MIN_MATCHES <= NEWS_MAX_KEYWORDS:
        raise ValueError("Проверьте настройки ожидания AI и количества ключевых слов")
    asyncio.run(run())


if __name__ == "__main__":
    main()
