"""Обновление индекса новостей из настроенных RSS- и Atom-лент."""

import logging
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from elasticsearch import ApiError, Elasticsearch, TransportError
from filelock import FileLock, Timeout as FileLockTimeout
from trafilatura import extract

from config import LOG_LEVEL, NEWS_RETENTION_DAYS, SEMANTIC_SIMILARITY_THRESHOLD, SOURCES
from config import PIPELINE_LOCK_PATH as LOCK_PATH
from parser import FeedArticle, FetchError, fetch_page, get_source_updates

from .cloudru_client import CloudRuEmbeddingClient, CloudRuError
from .elastic import create_article, create_client, ensure_news_index, has_similar_article, has_url
from .gigachat_client import GigaChatClient, GigaChatError

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Ошибка обновления ленты."""


class RefreshInProgress(PipelineError):
    """Другая копия пайплайна уже удерживает локальную блокировку."""


@dataclass
class RefreshResult:
    """Счётчики завершённого прохода по источникам."""

    matched: int = 0
    indexed: int = 0
    duplicates: int = 0
    failed_articles: int = 0
    failed_sources: int = 0
    expired: int = 0


def _index_article(
    entry: FeedArticle, elastic: Elasticsearch, gigachat: GigaChatClient, embedder: CloudRuEmbeddingClient
) -> bool:
    """Проверяет дубликаты, обогащает статью и сохраняет её в индексе."""
    if has_url(elastic, entry.url):
        return False

    page = fetch_page(entry.url)
    text = extract(page.content, url=page.url or entry.url, include_comments=False)
    if not text or not text.strip():
        raise FetchError("Trafilatura не смогла извлечь текст статьи")
    raw_text = text.strip()
    embedding = embedder.embed(raw_text)
    if has_similar_article(elastic, embedding):
        return False

    summary = gigachat.summarize(raw_text)
    created_at = datetime.now(timezone.utc)
    return create_article(
        elastic,
        {
            "url": entry.url,
            "title": entry.title,
            "source": entry.source,
            "published_at": entry.published_at or created_at,
            "summary": summary,
            "raw_text": raw_text,
            "embedding": embedding,
            "created_at": created_at,
            "content_hash": sha256(" ".join(raw_text.split()).encode()).hexdigest(),
        },
    )


def _refresh(elastic: Elasticsearch, gigachat: GigaChatClient, embedder: CloudRuEmbeddingClient) -> RefreshResult:
    result = RefreshResult()
    cutoff = datetime.now(timezone.utc) - timedelta(days=NEWS_RETENTION_DAYS)
    for source, url in SOURCES.items():
        try:
            entries = get_source_updates(source, url)
        except FetchError as error:
            result.failed_sources += 1
            logger.warning("Не удалось прочитать RSS %s: %s", source, error)
            continue

        result.matched += len(entries)
        for entry in entries:
            if entry.published_at is not None and entry.published_at < cutoff:
                result.expired += 1
                continue
            try:
                indexed = _index_article(entry, elastic, gigachat, embedder)
            except (FetchError, GigaChatError) as error:
                if isinstance(error, GigaChatError) and error.status_code == 402:
                    raise
                result.failed_articles += 1
                logger.warning("Не удалось обработать статью %s: %s", entry.url, error)
                continue
            if indexed:
                result.indexed += 1
            else:
                result.duplicates += 1

    if SOURCES and result.failed_sources == len(SOURCES):
        raise PipelineError("Не удалось прочитать ни одну RSS-ленту")
    return result


def run_pipeline() -> RefreshResult:
    """Запускает один проход под общей для планировщика и CLI блокировкой."""
    if not 0 <= SEMANTIC_SIMILARITY_THRESHOLD <= 1:
        raise PipelineError("SEMANTIC_SIMILARITY_THRESHOLD должен быть от 0 до 1")
    try:
        with (
            FileLock(LOCK_PATH, timeout=0),
            closing(CloudRuEmbeddingClient()) as embedder,
            closing(GigaChatClient()) as gigachat,
            create_client() as elastic,
        ):
            ensure_news_index(elastic)
            result = _refresh(elastic, gigachat, embedder)
    except FileLockTimeout:
        raise RefreshInProgress("Обновление ленты уже выполняется") from None

    logger.info("Обновление ленты завершено: %s", result)
    return result


def main() -> int:
    """Точка входа для ручного обновления из терминала."""
    logging.basicConfig(level=LOG_LEVEL)
    try:
        result = run_pipeline()
    except (PipelineError, CloudRuError, GigaChatError, ApiError, TransportError) as error:
        logger.error("Ошибка обновления ленты: %s", error)
        return 1
    return int(result.failed_articles > 0 or result.failed_sources > 0)


if __name__ == "__main__":
    raise SystemExit(main())
