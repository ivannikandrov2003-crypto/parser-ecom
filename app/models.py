"""Данные карточек веб-ленты."""

from zoneinfo import ZoneInfo

from pydantic import AnyHttpUrl, AwareDatetime, BaseModel

MOSCOW = ZoneInfo("Europe/Moscow")


class NewsCard(BaseModel):
    """Поля статьи, которые выводятся в ленте."""

    url: AnyHttpUrl
    title: str
    source: str
    published_at: AwareDatetime
    summary: str
    is_feed_excerpt: bool = False

    @property
    def display_date(self) -> str:
        """Форматирует дату публикации по московскому времени."""
        return self.published_at.astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M МСК")
