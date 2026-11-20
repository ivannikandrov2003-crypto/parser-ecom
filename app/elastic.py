"""Подключение к Elasticsearch и инициализация индекса новостей."""

import logging
from datetime import datetime, time, timedelta, timezone
from hashlib import sha1
from typing import Any, TypedDict

from elasticsearch import (
    ApiError,
    BadRequestError,
    ConflictError,
    ConnectionError,
    ConnectionTimeout,
    Elasticsearch,
    NotFoundError,
)
from tenacity import before_sleep_log, retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import (
    EMBEDDING_DIMENSIONS,
    ES_INDEX,
    ES_URL,
    LOG_LEVEL,
    NEWS_RETENTION_DAYS,
    SEMANTIC_SIMILARITY_THRESHOLD,
)

from .models import NewsCard, NewsPage

logger = logging.getLogger(__name__)
DAILY_INDEX_PREFIX = f"{ES_INDEX}-day-"
NEWS_INDICES = [ES_INDEX, f"{DAILY_INDEX_PREFIX}*"]
QWEN_INDEX_PREFIX = f"{DAILY_INDEX_PREFIX}qwen-"
RETENTION_POLICY_NAME = "news-retention"
RETENTION_POLICY = {
    "phases": {
        "delete": {
            "min_age": f"{NEWS_RETENTION_DAYS}d",
            "actions": {"delete": {"delete_searchable_snapshot": False}},
        },
    },
}
RECENT_ARTICLES = {"range": {"published_at": {"gte": f"now-{NEWS_RETENTION_DAYS}d"}}}

NEWS_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "url": {"type": "keyword"},
        "title": {"type": "text"},
        "source": {"type": "keyword"},
        "published_at": {"type": "date"},
        "summary": {"type": "text"},
        "raw_text": {"type": "text"},
        "embedding": {
            "type": "dense_vector",
            "dims": EMBEDDING_DIMENSIONS,
            "index": True,
            "similarity": "cosine",
            "index_options": {"type": "hnsw"},
        },
        "created_at": {"type": "date"},
        "content_hash": {"type": "keyword"},
    },
}


class NewsDocument(TypedDict):
    """Документ индекса news."""

    url: str
    title: str
    source: str
    published_at: datetime
    summary: str
    raw_text: str
    embedding: list[float]
    created_at: datetime
    content_hash: str


def create_client() -> Elasticsearch:
    """Создаёт клиент Elasticsearch с настройками из окружения."""
    return Elasticsearch(ES_URL, request_timeout=10, max_retries=0)


def _is_transient_error(error: BaseException) -> bool:
    """Определяет ошибки Elasticsearch, при которых стоит повторить запрос."""
    return isinstance(error, (ConnectionError, ConnectionTimeout)) or (
        isinstance(error, ApiError) and error.status_code in {408, 429, 500, 502, 503, 504}
    )


_retry_es = retry(
    retry=retry_if_exception(_is_transient_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=4),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


@_retry_es
def ensure_news_index(client: Elasticsearch) -> None:
    """Готовит ILM, текущий суточный индекс и доступ к прежнему news."""
    try:
        policies = client.ilm.get_lifecycle(name=RETENTION_POLICY_NAME)
    except NotFoundError:
        policies = {}
    if policies.get(RETENTION_POLICY_NAME, {}).get("policy") != RETENTION_POLICY:
        client.ilm.put_lifecycle(name=RETENTION_POLICY_NAME, policy=RETENTION_POLICY)

    resolved = client.indices.resolve_index(name=NEWS_INDICES, ignore_unavailable=True, allow_no_indices=True)
    names = {index["name"] for index in resolved.get("indices", [])}
    legacy = ES_INDEX in names
    if legacy:
        settings = client.indices.get_settings(index=ES_INDEX, flat_settings=True)[ES_INDEX]["settings"]
        if not settings.get("index.lifecycle.name"):
            # Дать статьям из старого индекса пройти полное окно хранения после перехода.
            client.indices.put_settings(index=ES_INDEX, settings=_lifecycle_settings(datetime.now(timezone.utc)))
    else:
        aliased = next(
            (set(alias["indices"]) for alias in resolved.get("aliases", []) if alias["name"] == ES_INDEX), set()
        )
        missing = sorted(name for name in names - aliased if name.startswith(DAILY_INDEX_PREFIX))
        if missing:
            client.indices.put_alias(index=missing, name=ES_INDEX, is_write_index=False)
    _ensure_daily_index(client, datetime.now(timezone.utc), attach_alias=not legacy)


def _lifecycle_settings(origination: datetime) -> dict[str, int | str]:
    return {
        "index.lifecycle.name": RETENTION_POLICY_NAME,
        "index.lifecycle.origination_date": int(origination.timestamp() * 1000),
    }


def _ensure_daily_index(client: Elasticsearch, published_at: datetime, attach_alias: bool | None = None) -> str:
    day = published_at.astimezone(timezone.utc).date()
    index = f"{QWEN_INDEX_PREFIX}{day.isoformat()}"
    if client.indices.exists(index=index):
        return index

    if attach_alias is None:
        resolved = client.indices.resolve_index(name=ES_INDEX, ignore_unavailable=True, allow_no_indices=True)
        attach_alias = all(item["name"] != ES_INDEX for item in resolved.get("indices", []))
    next_midnight = datetime.combine(day + timedelta(days=1), time.min, tzinfo=timezone.utc)
    try:
        client.indices.create(
            index=index,
            mappings=NEWS_MAPPING,
            settings={"number_of_shards": 1, "number_of_replicas": 0, **_lifecycle_settings(next_midnight)},
            aliases={ES_INDEX: {"is_write_index": False}} if attach_alias else None,
        )
    except BadRequestError as error:
        if error.error != "resource_already_exists_exception":
            raise
    return index


def _document_id(url: str) -> str:
    return sha1(url.encode(), usedforsecurity=False).hexdigest()


@_retry_es
def has_url(client: Elasticsearch, url: str) -> bool:
    """Проверяет ID статьи во всех суточных индексах и в прежнем news."""
    return bool(_search_news(client, query={"ids": {"values": [_document_id(url)]}}, size=1, source=False))


@_retry_es
def has_similar_article(client: Elasticsearch, embedding: list[float]) -> bool:
    """Проверяет наличие близкого вектора по порогу косинусного сходства."""
    hits = _search_news(
        client,
        index=f"{QWEN_INDEX_PREFIX}*",
        knn={
            "field": "embedding",
            "query_vector": embedding,
            "k": 1,
            "num_candidates": 100,
            "similarity": SEMANTIC_SIMILARITY_THRESHOLD,
            "filter": RECENT_ARTICLES,
        },
        size=1,
        source=False,
    )
    return bool(hits)


def _search_news(
    client: Elasticsearch, *, index: str | list[str] = NEWS_INDICES, **keywords: Any
) -> list[dict[str, Any]]:
    try:
        response = client.search(
            index=index,
            ignore_unavailable=True,
            allow_no_indices=True,
            allow_partial_search_results=False,
            track_total_hits=False,
            **keywords,
        )
    except NotFoundError as error:
        if error.error != "index_not_found_exception":
            raise
        return []
    if response.get("timed_out"):
        raise ConnectionTimeout("Elasticsearch не завершил поиск новостей за отведённое время")
    return response["hits"]["hits"]


@_retry_es
def create_article(client: Elasticsearch, article: NewsDocument) -> bool:
    """Создаёт документ один раз и ждёт, когда его увидит следующий kNN-запрос."""
    index = _ensure_daily_index(client, article["published_at"])
    try:
        client.create(
            index=index,
            id=_document_id(article["url"]),
            document=article,
            refresh="wait_for",
        )
    except ConflictError:
        return False
    return True


@_retry_es
def read_news_page(
    client: Elasticsearch, page_size: int, after: tuple[int, str] | None = None
) -> NewsPage:
    """Читает карточки от новых к старым с устойчивым порядком при равных датах."""
    hits = _search_news(
        client,
        query=RECENT_ARTICLES,
        source_includes=["url", "title", "source", "published_at", "summary"],
        sort=[{"published_at": "desc"}, {"url": "asc"}],
        search_after=after,
        size=page_size + 1,
    )
    cards = [NewsCard.model_validate(hit["_source"]) for hit in hits[:page_size]]
    if len(hits) <= page_size:
        return NewsPage(cards)

    timestamp, url = hits[page_size - 1]["sort"]
    return NewsPage(cards, (int(timestamp), url))


if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    with create_client() as client:
        ensure_news_index(client)
    logger.info("Хранилище новостей %s готово", ES_INDEX)
