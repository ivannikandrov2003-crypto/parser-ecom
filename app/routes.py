"""HTML-лента и API ручного обновления."""

import logging
from pathlib import Path
from typing import Annotated

from elasticsearch import ApiError, TransportError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from .cloudru_client import CloudRuError
from .elastic import read_news_page
from .gigachat_client import GigaChatError
from .models import NewsPage
from .pipeline import PipelineError, RefreshInProgress, RefreshResult, run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).with_name("templates"))
PAGE_SIZE = 12


@router.get("/", response_class=HTMLResponse)
def news_feed(
    request: Request,
    before_time: Annotated[int | None, Query(ge=-(2**63), le=2**63 - 1)] = None,
    before_url: Annotated[str | None, Query(min_length=1, max_length=8191)] = None,
) -> HTMLResponse:
    """Показывает страницу ленты, начиная с указанной позиции."""
    if (before_time is None) != (before_url is None):
        raise HTTPException(422, "Для перехода нужны дата и URL последней статьи")
    position = (before_time, before_url) if before_time is not None and before_url is not None else None

    error_message = None
    status_code = 200
    try:
        page = read_news_page(request.app.state.elastic, PAGE_SIZE, position)
    except (ApiError, TransportError, ValidationError):
        logger.exception("Не удалось загрузить ленту из Elasticsearch")
        page = NewsPage([])
        error_message = "Не удалось загрузить ленту. Попробуйте открыть её снова."
        status_code = 503

    feed_url = request.url_for("news_feed")
    next_url = None
    if page.next_position is not None:
        timestamp, url = page.next_position
        next_url = feed_url.include_query_params(before_time=timestamp, before_url=url)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "cards": page.cards,
            "first_page_url": feed_url if position else None,
            "next_page_url": next_url,
            "feed_url": feed_url,
            "error_message": error_message,
        },
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/refresh")
def refresh_news() -> RefreshResult:
    """Запускает обновление и возвращает итог после завершения прохода."""
    try:
        result = run_pipeline()
    except RefreshInProgress:
        raise HTTPException(409, "Обновление ленты уже выполняется. Попробуйте чуть позже.") from None
    except CloudRuError as error:
        logger.warning("Обновление остановлено: %s", error)
        raise HTTPException(402 if error.status_code == 402 else 503, str(error)) from None
    except GigaChatError as error:
        if error.status_code == 402:
            logger.warning("Обновление остановлено: %s", error)
            raise HTTPException(402, str(error)) from None
        logger.exception("Ошибка GigaChat при запуске обновления")
        raise HTTPException(503, "GigaChat недоступен. Проверьте его настройки в .env.") from None
    except (ApiError, TransportError):
        logger.exception("Ошибка Elasticsearch при обновлении")
        raise HTTPException(503, "Elasticsearch недоступен. Попробуйте обновить ленту позже.") from None
    except PipelineError as error:
        logger.warning("Ошибка обновления ленты: %s", error)
        raise HTTPException(502, str(error)) from None

    if result.failed_articles and result.failed_articles == result.matched - result.expired:
        raise HTTPException(502, "Не удалось обработать найденные статьи. Попробуйте обновить ленту позже.")
    return result
