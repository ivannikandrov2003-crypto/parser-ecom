"""Планировщик регулярного обновления новостного индекса."""

import logging

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from config import LOG_LEVEL, REFRESH_INTERVAL_MINUTES

from .pipeline import RefreshInProgress, run_pipeline

logger = logging.getLogger(__name__)


def _scheduled_refresh() -> None:
    try:
        run_pipeline()
    except RefreshInProgress as error:
        logger.info("Запуск по расписанию пропущен: %s", error)


def schedule_refresh(scheduler: BaseScheduler) -> None:
    """Регистрирует обновление с интервалом из конфигурации."""
    if REFRESH_INTERVAL_MINUTES <= 0:
        raise ValueError("REFRESH_INTERVAL_MINUTES должен быть положительным")
    scheduler.add_job(
        _scheduled_refresh,
        "interval",
        minutes=REFRESH_INTERVAL_MINUTES,
        id="refresh_news",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )


def main() -> None:
    """Запускает планировщик в отдельном процессе."""
    logging.basicConfig(level=LOG_LEVEL)
    scheduler = BlockingScheduler()
    schedule_refresh(scheduler)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        if scheduler.running:
            scheduler.shutdown()


if __name__ == "__main__":
    main()
