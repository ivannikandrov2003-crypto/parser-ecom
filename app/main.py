"""Веб-приложение для чтения и обновления новостной ленты."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from config import LOG_LEVEL

from .elastic import create_client
from .routes import router
from .scheduler import schedule_refresh


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управляет клиентом Elasticsearch и планировщиком веб-процесса."""
    logging.basicConfig(level=LOG_LEVEL)
    scheduler = BackgroundScheduler()
    schedule_refresh(scheduler)
    with create_client() as elastic:
        app.state.elastic = elastic
        scheduler.start()
        try:
            yield
        finally:
            await run_in_threadpool(scheduler.shutdown)


app = FastAPI(title="Новости e-commerce", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")
app.include_router(router)
