"""Веб-приложение для чтения и обновления новостной ленты."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg import Error

from config import LOG_LEVEL

from .routes import router

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

app = FastAPI(title="Новости e-commerce")
app.mount("/static", StaticFiles(directory=Path(__file__).with_name("static")), name="static")
app.include_router(router)


@app.exception_handler(Error)
async def database_failure(request: Request, error: Error) -> JSONResponse:
    logger.error("Ошибка PostgreSQL при запросе %s", request.url.path, exc_info=error)
    return JSONResponse({"detail": "Хранилище новостей недоступно"}, status_code=503)
