"""Загрузка и разбор RSS и Atom."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from re import sub
from subprocess import TimeoutExpired, run
from time import sleep
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag
from curl_cffi import requests
from curl_cffi.requests.exceptions import ConnectionError, RequestException, SSLError, Timeout

from config import KEYWORDS, RSS_STANDARD_HTTP_SOURCES

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FeedArticle:
    """Публикация из ленты."""

    source: str
    title: str
    url: str
    published_at: datetime | None
    excerpt: str = ""


class FetchError(RuntimeError):
    """Ошибка загрузки страницы или чтения ленты."""

    def __init__(self, message: str, *, retry_at: datetime | None = None):
        super().__init__(message)
        self.retry_at = retry_at


@dataclass(frozen=True)
class FeedResponse:
    content: bytes
    url: str


FETCH_TIMEOUT_SECONDS = 5


def fetch_page(url: str) -> requests.Response:
    """Скачивает RSS или статью одной попыткой с общим тайм-аутом."""
    try:
        response = requests.get(url, impersonate="chrome110", timeout=FETCH_TIMEOUT_SECONDS, max_redirects=5)
    except SSLError:
        raise FetchError(f"Ошибка проверки TLS для {url}") from None
    except Timeout:
        raise FetchError(f"Загрузка {url} заняла больше {FETCH_TIMEOUT_SECONDS} секунд") from None
    except ConnectionError:
        raise FetchError(f"Сетевой сбой при загрузке {url}") from None
    except RequestException as error:
        raise FetchError(f"Не удалось загрузить {url} (код curl {error.code})") from None

    _check_status(response.status_code, url, response.headers.get("Retry-After"))
    return response


def _check_status(status: int, url: str, retry_after: str | None):
    if status == 200:
        return
    retry_at = None
    if status == 429:
        now = datetime.now(timezone.utc)
        value = (retry_after or "").strip()
        try:
            if value.isascii() and value.isdecimal():
                retry_at = now + timedelta(seconds=int(value))
            elif value:
                date = parsedate_to_datetime(value)
                retry_at = date if date.tzinfo else date.replace(tzinfo=timezone.utc)
        except (OverflowError, ValueError):
            pass
        if retry_at is None:
            retry_at = now + timedelta(minutes=30)
    raise FetchError(f"HTTP {status} при загрузке {url}", retry_at=retry_at)


def _fetch_standard_rss(url: str) -> FeedResponse:
    """Обычный HTTP-запрос к публичной ленте через системный curl."""
    try:
        response = run(
            [
                "curl", "--disable", "--silent", "--show-error", "--location", "--max-redirs", "5",
                "--proto", "=http,https", "--proto-redir", "=http,https",
                "--max-time", str(FETCH_TIMEOUT_SECONDS),
                "--write-out", "%{stderr}%{http_code}\n%{url_effective}\n%header{retry-after}",
                "--", url,
            ],
            capture_output=True,
            timeout=FETCH_TIMEOUT_SECONDS + 1,
            check=False,
        )
    except TimeoutExpired:
        raise FetchError(f"Загрузка {url} заняла больше {FETCH_TIMEOUT_SECONDS} секунд") from None
    except OSError:
        raise FetchError("Для чтения RSS «Известий» нужен системный curl") from None

    if response.returncode == 28:
        raise FetchError(f"Загрузка {url} заняла больше {FETCH_TIMEOUT_SECONDS} секунд")
    if response.returncode:
        raise FetchError(f"Не удалось загрузить {url} (код curl {response.returncode})")
    try:
        status, final_url, retry_after = response.stderr.decode().split("\n", 2)
        status_code = int(status)
    except (UnicodeError, ValueError):
        raise FetchError(f"Не удалось прочитать HTTP-ответ для {url}") from None
    _check_status(status_code, url, retry_after)
    return FeedResponse(response.stdout, final_url or url)


def _text(item: Tag, name: str) -> str:
    tag = item.find(name, recursive=False)
    return tag.get_text().strip() if isinstance(tag, Tag) else ""


def _article_excerpt(item: Tag) -> str:
    tag = item.find(["description", "summary"], recursive=False)
    if not isinstance(tag, Tag):
        return ""
    value = tag.decode_contents() if tag.find(True) else tag.get_text()
    if "<" in value:
        value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return sub(r"\s+([.,!?;:])", r"\1", " ".join(value.split()))


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
    for name in ("pubDate", "published", "date"):
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


def get_source_updates(source: str, url: str, *, filter_titles: bool = True) -> list[FeedArticle]:
    """Возвращает подходящие публикации одной ленты в исходном порядке."""
    logger.info("Читаем RSS %s", source)
    response = _fetch_standard_rss(url) if source in RSS_STANDARD_HTTP_SOURCES else fetch_page(url)
    soup = BeautifulSoup(response.content, "xml")
    root = soup.find()
    if root is None or root.name not in {"rss", "feed", "RDF"}:
        raise FetchError(f"Источник {source} вернул ответ без RSS или Atom")

    articles = []
    for item in root.find_all("item") or root.find_all("entry"):
        title = _text(item, "title")
        if not title or (filter_titles and not any(word in title.lower() for word in KEYWORDS)):
            continue
        link = _article_url(item, response.url or url)
        if link:
            articles.append(FeedArticle(source, title, link, _publication_date(item), _article_excerpt(item)))
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
