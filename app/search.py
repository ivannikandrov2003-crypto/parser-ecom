"""Асинхронная доставка изменений из PostgreSQL в Elasticsearch."""

import logging

from elasticsearch import ApiError, BadRequestError, NotFoundError, TransportError

from config import NEWS_DUPLICATE_MIN_MATCHES, NEWS_DUPLICATE_SCORE, NEWS_RETENTION_DAYS, NEWS_SEARCH_INDEX

from .database import SEARCH_LOCK, try_lock_async

logger = logging.getLogger(__name__)


class SearchError(RuntimeError):
    """Поиск не смог надёжно определить наличие дубликата."""


async def ensure_index(db, elastic):
    if await elastic.indices.exists(index=NEWS_SEARCH_INDEX):
        return
    await db.execute(
        """
        INSERT INTO search_outbox (news_id, operation)
        SELECT n.id, 'reindex' FROM news n JOIN raw_news r ON r.id = n.raw_news_id
        WHERE r.checked ON CONFLICT (news_id) DO NOTHING
        """
    )
    try:
        await elastic.indices.create(
            index=NEWS_SEARCH_INDEX,
            settings={"number_of_shards": 1, "number_of_replicas": 0},
            mappings={
                "dynamic": "strict",
                "properties": {
                    "news_id": {"type": "long"},
                    "raw_news_id": {"type": "long"},
                    "keywords": {"type": "text", "analyzer": "russian", "similarity": "BM25"},
                    "created_at": {"type": "date"},
                },
            },
        )
    except BadRequestError as error:
        if error.error != "resource_already_exists_exception":
            raise


async def find_duplicate(db, elastic, keywords):
    if len(keywords) < NEWS_DUPLICATE_MIN_MATCHES:
        return None

    cursor = await db.execute("SELECT news_id FROM search_outbox WHERE operation IN ('index', 'delete')")
    excluded = [str(row["news_id"]) for row in await cursor.fetchall()]
    query = {
        "filter": [{"range": {"created_at": {"gte": f"now-{NEWS_RETENTION_DAYS}d"}}}],
        "should": [{"match_phrase": {"keywords": keyword}} for keyword in keywords],
        "minimum_should_match": NEWS_DUPLICATE_MIN_MATCHES,
    }
    if excluded:
        query["must_not"] = [{"ids": {"values": excluded}}]
    response = await elastic.search(
        index=NEWS_SEARCH_INDEX,
        query={"bool": query},
        min_score=NEWS_DUPLICATE_SCORE,
        source_includes=["news_id"],
        size=20,
        allow_partial_search_results=False,
        track_total_hits=False,
    )
    if response.get("timed_out"):
        raise SearchError("Elasticsearch не завершил поиск дубликатов")
    hits = response["hits"]["hits"]
    if not hits:
        return None

    ids = [hit["_source"]["news_id"] for hit in hits]
    cursor = await db.execute(
        "SELECT n.id FROM news n JOIN raw_news r ON r.id = n.raw_news_id WHERE r.checked AND n.id = ANY(%s)",
        (ids,),
    )
    active = {row["id"] for row in await cursor.fetchall()}
    for hit in hits:
        news_id = hit["_source"]["news_id"]
        if news_id in active:
            return news_id, hit["_score"]
    return None


async def mark_duplicate(db, raw_news_id, duplicate, *, news_id=None):
    async with db.transaction():
        if news_id is not None:
            await db.execute("DELETE FROM news WHERE id = %s", (news_id,))
            await db.execute(
                """
                UPDATE search_outbox SET operation = 'delete', attempts = 0, next_attempt_at = now()
                WHERE news_id = %s
                """,
                (news_id,),
            )
        await db.execute(
            """
            UPDATE raw_news SET checked = true, duplicate_of_news_id = %s, duplicate_score = %s
            WHERE id = %s
            """,
            (*duplicate, raw_news_id),
        )
    logger.info("Дубликат raw_news_id=%s, news_id=%s, оценка=%s", raw_news_id, *duplicate)


async def delete_document(db, elastic, news_id):
    try:
        await elastic.delete(index=NEWS_SEARCH_INDEX, id=str(news_id), refresh="wait_for")
    except NotFoundError:
        pass
    await db.execute("DELETE FROM search_outbox WHERE news_id = %s", (news_id,))


async def preparing_reindex(db):
    cursor = await db.execute("SELECT 1 FROM search_outbox WHERE operation = 'reindex' LIMIT 1")
    return await cursor.fetchone() is not None


async def stage_candidate(db, elastic, candidate):
    await ensure_index(db, elastic)
    if await preparing_reindex(db):
        return None

    raw_news_id = candidate["id"]
    duplicate = await find_duplicate(db, elastic, candidate["keywords"])
    if duplicate:
        await mark_duplicate(db, raw_news_id, duplicate)
        return None

    cursor = await db.execute(
        """
        WITH candidate AS (
            INSERT INTO news (text, raw_news_id) VALUES (%s, %s) RETURNING id
        )
        INSERT INTO search_outbox (news_id, operation) SELECT id, 'index' FROM candidate
        RETURNING news_id, operation, attempts
        """,
        (candidate["ai_summary"], raw_news_id),
    )
    return await cursor.fetchone()


async def index_document(db, elastic, job, *, fresh):
    news_id = job["news_id"]
    if not fresh:
        await ensure_index(db, elastic)
        if job["operation"] == "index" and await preparing_reindex(db):
            return

    cursor = await db.execute(
        """
        SELECT n.id AS news_id, n.raw_news_id, r.keywords, n.created_at
        FROM news n JOIN raw_news r ON r.id = n.raw_news_id WHERE n.id = %s
        """,
        (news_id,),
    )
    document = await cursor.fetchone()
    if document is None:
        await delete_document(db, elastic, news_id)
        return

    if job["operation"] == "index" and not fresh:
        duplicate = await find_duplicate(db, elastic, document["keywords"])
        if duplicate:
            await mark_duplicate(db, document["raw_news_id"], duplicate, news_id=news_id)
            return

    await elastic.index(index=NEWS_SEARCH_INDEX, id=str(news_id), document=document, refresh="wait_for")
    async with db.transaction():
        if job["operation"] == "index":
            await db.execute("UPDATE raw_news SET checked = true WHERE id = %s", (document["raw_news_id"],))
        await db.execute("DELETE FROM search_outbox WHERE news_id = %s", (news_id,))
    logger.info("Индекс: %s для news_id=%s", job["operation"], news_id)


def retry_delay(attempts):
    return min(5 * 2 ** min(attempts, 8), 900)


async def stage_next(db, elastic):
    cursor = await db.execute(
        """
        SELECT id, ai_summary, keywords, attempts FROM raw_news r
        WHERE NOT checked AND ai_summary IS NOT NULL AND next_attempt_at <= now()
          AND NOT EXISTS (SELECT FROM news WHERE raw_news_id = r.id)
          AND NOT EXISTS (SELECT FROM search_outbox WHERE operation = 'reindex')
        ORDER BY next_attempt_at, id LIMIT 1
        """
    )
    candidate = await cursor.fetchone()
    if candidate is None:
        return False, None

    try:
        return True, await stage_candidate(db, elastic, candidate)
    except (ApiError, TransportError, SearchError) as error:
        delay = retry_delay(candidate["attempts"])
        await db.execute(
            """
            UPDATE raw_news SET attempts = attempts + 1, next_attempt_at = now() + make_interval(secs => %s)
            WHERE id = %s
            """,
            (delay, candidate["id"]),
        )
        logger.warning("Поиск raw_news_id=%s, повтор через %s с: %s", candidate["id"], delay, error)
        return True, None


async def sync_next(db, elastic):
    async with try_lock_async(db, SEARCH_LOCK) as acquired:
        if not acquired:
            return False

        cursor = await db.execute(
            """
            SELECT news_id, operation, attempts
            FROM search_outbox WHERE next_attempt_at <= now()
              AND (operation <> 'index' OR NOT EXISTS (
                  SELECT FROM search_outbox WHERE operation = 'reindex'
              ))
            ORDER BY next_attempt_at, news_id LIMIT 1
            """
        )
        job = await cursor.fetchone()
        fresh = job is None
        if fresh:
            processed, job = await stage_next(db, elastic)
            if job is None:
                return processed

        news_id = job["news_id"]
        try:
            if job["operation"] == "delete":
                await delete_document(db, elastic, news_id)
            else:
                await index_document(db, elastic, job, fresh=fresh)
        except (ApiError, TransportError, SearchError) as error:
            delay = retry_delay(job["attempts"])
            await db.execute(
                """
                UPDATE search_outbox SET attempts = attempts + 1,
                    next_attempt_at = now() + make_interval(secs => %s) WHERE news_id = %s
                """,
                (delay, news_id),
            )
            logger.warning("Индекс: %s для news_id=%s, попытка=%s, повтор через %s с: %s",
                           job["operation"], news_id, job["attempts"] + 1, delay, error)
        return True
