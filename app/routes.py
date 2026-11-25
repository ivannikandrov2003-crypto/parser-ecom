"""Публичная веб-лента и API, работающие с PostgreSQL."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from psycopg import Error
from pydantic import AnyHttpUrl, AwareDatetime, BaseModel

from .database import connect_async
from .models import NewsCard
from .telegram_worker import MODE as TELEGRAM_MODE

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).with_name("templates"))
PAGE_SIZE = 12
NEWS_SELECT = """
    SELECT n.id, r.header, r.source, r.source_name, r.published_at, n.text, r.is_feed_excerpt
    FROM news n JOIN raw_news r ON r.id = n.raw_news_id
    WHERE r.checked
"""


class NewsItem(BaseModel):
    id: int
    header: str
    text: str
    source: AnyHttpUrl
    published_at: AwareDatetime
    is_feed_excerpt: bool = False


@router.get("/healthz", include_in_schema=False)
async def healthcheck() -> Response:
    async with await connect_async() as db:
        await db.execute("SELECT 1 FROM collection_job WHERE id = 1")
    return Response(status_code=204)


@router.get("/", response_class=HTMLResponse)
async def news_feed(
    request: Request,
    before_time: Annotated[int | None, Query(ge=-(2**63), le=2**63 - 1)] = None,
    before_url: Annotated[str | None, Query(min_length=1, max_length=8191)] = None,
) -> HTMLResponse:
    if (before_time is None) != (before_url is None):
        raise HTTPException(422, "Для перехода нужны дата и URL последней статьи")
    position = None
    if before_time is not None:
        try:
            position = datetime.fromtimestamp(before_time / 1000, timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise HTTPException(422, "Дата вне допустимого диапазона") from None

    error_message = None
    status_code = 200
    try:
        async with await connect_async() as db:
            if position is None:
                cursor = await db.execute(
                    NEWS_SELECT + " ORDER BY r.published_at DESC, r.source ASC LIMIT %s",
                    (PAGE_SIZE + 1,),
                )
            else:
                cursor = await db.execute(
                    NEWS_SELECT + """
                    AND (r.published_at < %s OR (r.published_at = %s AND r.source > %s))
                    ORDER BY r.published_at DESC, r.source ASC LIMIT %s
                    """,
                    (position, position, before_url, PAGE_SIZE + 1),
                )
            rows = await cursor.fetchall()
    except Error:
        logger.exception("Не удалось загрузить ленту из PostgreSQL")
        rows = []
        error_message = "Не удалось загрузить ленту. Попробуйте открыть её снова."
        status_code = 503

    cards = [
        NewsCard(url=row["source"], title=row["header"], source=row["source_name"],
                 published_at=row["published_at"], summary=row["text"], is_feed_excerpt=row["is_feed_excerpt"])
        for row in rows[:PAGE_SIZE]
    ]
    feed_url = request.url_for("news_feed").path
    next_url = None
    if len(rows) > PAGE_SIZE:
        last = rows[PAGE_SIZE - 1]
        query = urlencode({
            "before_time": round(last["published_at"].timestamp() * 1000),
            "before_url": last["source"],
        })
        next_url = f"{feed_url}?{query}"

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "cards": cards,
            "first_page_url": feed_url if position is not None else None,
            "next_page_url": next_url,
            "feed_url": feed_url,
            "error_message": error_message,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/news", response_model=list[NewsItem])
async def list_news(
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=2**31 - 1)] = 0,
):
    async with await connect_async() as db:
        cursor = await db.execute(
            NEWS_SELECT + " ORDER BY r.published_at DESC, n.id DESC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        return await cursor.fetchall()


@router.get("/api/news/{news_id}", response_model=NewsItem)
async def get_news(news_id: int):
    if not 0 < news_id < 2**63:
        raise HTTPException(404, "Новость не найдена")
    async with await connect_async() as db:
        cursor = await db.execute(NEWS_SELECT + " AND n.id = %s", (news_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, "Новость не найдена")
    return row


@router.get("/api/refresh", name="refresh_status")
async def refresh_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    async with await connect_async() as db:
        cursor = await db.execute(
            """
            SELECT job.state, job.result, stats.*
            FROM collection_job job CROSS JOIN LATERAL (
                SELECT
                    count(*) FILTER (WHERE r.classification_failed_at IS NULL) AS pending,
                    count(*) FILTER (WHERE r.classification_failed_at IS NOT NULL) AS needs_review,
                    count(*) FILTER (
                        WHERE r.classification_failed_at IS NULL
                          AND greatest(r.next_attempt_at, o.next_attempt_at) > now()
                    ) AS retrying
                FROM raw_news r
                LEFT JOIN news n ON n.raw_news_id = r.id
                LEFT JOIN search_outbox o ON o.news_id = n.id AND o.operation = 'index'
                WHERE NOT r.checked
            ) stats
            WHERE job.id = 1
            """
        )
        return (await cursor.fetchone()) | {"telegram": TELEGRAM_MODE}


@router.post("/api/refresh", status_code=202)
async def refresh_news(request: Request):
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(403, "Запустите обновление со страницы ленты")
    async with await connect_async() as db:
        await db.execute(
            "UPDATE collection_job SET state = 'queued' WHERE id = 1 AND state NOT IN ('queued', 'running')"
        )
        cursor = await db.execute("SELECT state FROM collection_job WHERE id = 1")
        return await cursor.fetchone()
