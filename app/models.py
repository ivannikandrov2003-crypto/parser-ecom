"""Данные карточек веб-ленты."""

from zoneinfo import ZoneInfo

from pydantic import AnyHttpUrl, AwareDatetime, BaseModel, Field

from .footnotes import Footnote

MOSCOW = ZoneInfo("Europe/Moscow")


class NewsCard(BaseModel):
    """Поля статьи, которые выводятся в ленте."""

    url: AnyHttpUrl
    title: str
    source: str
    published_at: AwareDatetime
    summary: str
    footnotes: list[Footnote] = Field(default_factory=list)
    is_feed_excerpt: bool = False

    @property
    def display_date(self) -> str:
        """Форматирует дату публикации по московскому времени."""
        return self.published_at.astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M МСК")
