"""Загрузка и разбор RSS и Atom с фильтрацией по заголовку."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import sleep
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import KEYWORDS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedArticle:
    """Публикация, подходящая по ключевым словам."""

    source: str
    title: str
    url: str
    published_at: datetime | None


class FetchError(RuntimeError):
    """Ошибка загрузки страницы или чтения ленты."""


class _TemporaryFetchError(FetchError):
    """Временный сбой при загрузке страницы."""


@retry(
    retry=retry_if_exception_type(_TemporaryFetchError),
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=1, max=8),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def fetch_page(url: str) -> requests.Response:
    """Скачивает RSS или страницу статьи с повторами временных сбоев."""
    try:
        response = requests.get(url, impersonate="chrome110", timeout=30, max_redirects=5)
    except SSLError:
        raise FetchError(f"Ошибка проверки TLS для {url}") from None
    except (Timeout, ConnectionError):
        raise _TemporaryFetchError(f"Сетевой сбой при загрузке {url}") from None
    except RequestException as error:
        raise FetchError(f"Не удалось загрузить {url} (код curl {error.code})") from None

    status = response.status_code
    if status in {408, 429} or 500 <= status < 600:
        raise _TemporaryFetchError(f"HTTP {status} при загрузке {url}")
    if status != 200:
        raise FetchError(f"HTTP {status} при загрузке {url}")
    return response


def _text(item: Tag, name: str) -> str:
    tag = item.find(name, recursive=False)
    return tag.get_text().strip() if isinstance(tag, Tag) else ""


def _article_url(item: Tag, feed_url: str) -> str | None:
    links = [
        link.get_text().strip() or link.get("href")
        for link in item.find_all("link", recursive=False)
        if link.get("rel") in (None, "alternate")
    ]
    for value in [*links, _text(item, "guid")]:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            url = urljoin(feed_url, value.strip())
            parsed = urlsplit(url)
            if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.username is None:
                return url
        except ValueError:
            continue
    return None


def _publication_date(item: Tag) -> datetime | None:
    for name in ("pubDate", "published", "date", "updated"):
        value = _text(item, name)
        if not value:
            continue
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                date = parsedate_to_datetime(value)
            except (ValueError, OverflowError):
                continue
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc)
    return None


def get_source_updates(source: str, url: str) -> list[FeedArticle]:
    """Возвращает подходящие публикации одной ленты в исходном порядке."""
    logger.info("Читаем RSS %s", source)
    response = fetch_page(url)
    soup = BeautifulSoup(response.content, "xml")
    root = soup.find()
    if root is None or root.name not in {"rss", "feed", "RDF"}:
        raise FetchError(f"Источник {source} вернул ответ без RSS или Atom")

    articles = []
    for item in root.find_all("item") or root.find_all("entry"):
        title = _text(item, "title")
        if not title or not any(word in title.lower() for word in KEYWORDS):
            continue
        link = _article_url(item, response.url or url)
        if link:
            articles.append(FeedArticle(source, title, link, _publication_date(item)))
    return articles


def get_updates(sources: Mapping[str, str]) -> list[dict[str, str]]:
    """Возвращает совпадения в прежнем формате со ссылкой в поле link."""
    news = []
    for source, url in sources.items():
        try:
            articles = get_source_updates(source, url)
        except FetchError as error:
            logger.warning("Ошибка при чтении RSS %s: %s", source, error)
            continue
        news.extend({"source": article.source, "title": article.title, "link": article.url} for article in articles)
        sleep(2)
    return news
