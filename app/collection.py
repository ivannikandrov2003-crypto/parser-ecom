"""Независимый сбор свежих исходных новостей."""

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urldefrag

from psycopg import Error
from psycopg.types.json import Jsonb
from trafilatura import extract

from config import LOG_LEVEL, REFRESH_INTERVAL_MINUTES, RSS_EXCERPT_SOURCES, SOURCES
from parser import FetchError, fetch_page, get_source_updates

from .database import COLLECTION_LOCK, connect_async, try_lock_async

logger = logging.getLogger(__name__)


@dataclass
class CollectionResult:
    collected: int = 0
    collected_excerpts: int = 0
    duplicates: int = 0
    skipped_date: int = 0
    failed_articles: int = 0
    failed_sources: int = 0
    deferred_sources: int = 0


async def collect_source(db, source, feed, now):
    result = CollectionResult()
    cutoff = now - timedelta(hours=24)
    cooldown = await db.execute(
        "SELECT retry_at FROM rss_retry_after WHERE source_url = %s AND retry_at > now()",
        (feed,),
    )
    deferred = await cooldown.fetchone()
    if deferred:
        result.deferred_sources = 1
        logger.info("Источник %s отложен до %s", source, deferred["retry_at"])
        return result

    try:
        entries = await asyncio.to_thread(get_source_updates, source, feed, filter_titles=False)
    except FetchError as error:
        if error.retry_at is not None:
            await db.execute(
                """
                INSERT INTO rss_retry_after (source_url, retry_at) VALUES (%s, %s)
                ON CONFLICT (source_url) DO UPDATE SET retry_at = greatest(rss_retry_after.retry_at, excluded.retry_at)
                """,
                (feed, error.retry_at),
            )
        result.failed_sources = 1
        logger.warning("Не удалось прочитать источник %s: %s", source, error)
        return result

    for entry in entries:
        if entry.published_at is None or not cutoff <= entry.published_at <= now:
            result.skipped_date += 1
            continue
        url = urldefrag(entry.url).url
        existing = await db.execute("SELECT 1 FROM raw_news WHERE source = %s", (url,))
        if await existing.fetchone():
            result.duplicates += 1
            continue
        is_feed_excerpt = False
        try:
            page = await asyncio.to_thread(fetch_page, url)
            text = await asyncio.to_thread(extract, page.content, url=page.url or url, include_comments=False)
            if not text or not text.strip():
                raise FetchError("Не удалось извлечь текст статьи")
        except FetchError as error:
            if source not in RSS_EXCERPT_SOURCES or not entry.excerpt or entry.excerpt.casefold() == entry.title.casefold():
                result.failed_articles += 1
                logger.warning("Не удалось собрать %s: %s", url, error)
                continue
            text = entry.excerpt
            is_feed_excerpt = True
            logger.info("Используем анонс RSS для %s: %s", url, error)
        inserted = await db.execute(
            """
            INSERT INTO raw_news (header, text, source, source_name, published_at, is_feed_excerpt)
            VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (source) DO NOTHING
            """,
            (entry.title, text.strip(), url, entry.source, entry.published_at, is_feed_excerpt),
        )
        if inserted.rowcount:
            result.collected += 1
            if is_feed_excerpt:
                result.collected_excerpts += 1
        else:
            result.duplicates += 1
    logger.info("Источник %s: сохранено %s, ошибок загрузки %s",
                source, result.collected, result.failed_articles)
    return result


async def collect(db):
    now = datetime.now(timezone.utc)
    slots = asyncio.Semaphore(4)

    async def collect_with_slot(source, feed):
        async with slots:
            return await collect_source(db, source, feed, now)

    results = await asyncio.gather(
        *(collect_with_slot(source, feed) for source, feed in SOURCES.items()),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return CollectionResult(
        collected=sum(result.collected for result in results),
        collected_excerpts=sum(result.collected_excerpts for result in results),
        duplicates=sum(result.duplicates for result in results),
        skipped_date=sum(result.skipped_date for result in results),
        failed_articles=sum(result.failed_articles for result in results),
        failed_sources=sum(result.failed_sources for result in results),
        deferred_sources=sum(result.deferred_sources for result in results),
    )


async def run_once(*, force=False):
    async with await connect_async() as db, try_lock_async(db, COLLECTION_LOCK) as acquired:
        if not acquired:
            return False
        cursor = await db.execute(
            """
            SELECT state, started_at IS NULL OR started_at <= now() - make_interval(mins => %s) AS due
            FROM collection_job WHERE id = 1
            """,
            (REFRESH_INTERVAL_MINUTES,),
        )
        job = await cursor.fetchone()
        if not (force or job["due"] or job["state"] in {"queued", "running"}):
            return False
        await db.execute(
            "UPDATE collection_job SET state = 'running', started_at = now(), result = NULL WHERE id = 1"
        )
        result = await collect(db)
        failed = bool(SOURCES) and result.failed_sources == len(SOURCES)
        await db.execute(
            "UPDATE collection_job SET state = %s, finished_at = now(), result = %s WHERE id = 1",
            ("failed" if failed else "done", Jsonb(asdict(result))),
        )
        logger.info("Сбор завершён: %s", result)
        return True


async def run():
    while True:
        try:
            await run_once()
        except Error:
            logger.exception("Ошибка PostgreSQL при сборе")
        await asyncio.sleep(5)


def main():
    logging.basicConfig(level=LOG_LEVEL)
    if REFRESH_INTERVAL_MINUTES <= 0:
        raise ValueError("REFRESH_INTERVAL_MINUTES должен быть положительным")
    asyncio.run(run())


if __name__ == "__main__":
    main()
