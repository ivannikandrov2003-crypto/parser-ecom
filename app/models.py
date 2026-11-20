"""Данные карточек и постраничной выдачи."""

from dataclasses import dataclass
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

    @property
    def display_date(self) -> str:
        """Форматирует дату публикации по московскому времени."""
        return self.published_at.astimezone(MOSCOW).strftime("%d.%m.%Y, %H:%M МСК")


@dataclass(frozen=True)
class NewsPage:
    """Одна страница ленты и позиция для чтения следующей."""

    cards: list[NewsCard]
    next_position: tuple[int, str] | None = None
