"""Подключение к PostgreSQL и применение версионных миграций."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import LOG_LEVEL

from .footnotes import extract_footnotes

COLLECTION_LOCK = 51001
SEARCH_LOCK = 51002
MIGRATION_LOCK = 51003


def connect():
    return psycopg.connect(
        os.getenv("DATABASE_URL", ""),
        autocommit=True,
        connect_timeout=5,
        row_factory=dict_row,
    )


async def connect_async():
    return await psycopg.AsyncConnection.connect(
        os.getenv("DATABASE_URL", ""),
        autocommit=True,
        connect_timeout=5,
        row_factory=dict_row,
    )


@asynccontextmanager
async def try_lock_async(db, key):
    cursor = await db.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (key,))
    acquired = (await cursor.fetchone())["acquired"]
    try:
        yield acquired
    finally:
        if acquired and not db.closed:
            await db.execute("SELECT pg_advisory_unlock(%s)", (key,))


def backfill_source_footnotes(db):
    articles = db.execute("SELECT id, header, text FROM raw_news WHERE strpos(text, '*') > 0")
    for row in articles:
        notes = extract_footnotes(row["text"], row["header"])
        if notes:
            db.execute("UPDATE raw_news SET source_footnotes = %s WHERE id = %s", (Jsonb(notes), row["id"]))


def migrate():
    with connect() as db, db.transaction():
        db.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK,))
        db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)")
        applied = {row["name"] for row in db.execute("SELECT name FROM schema_migrations")}
        for path in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            if path.name in applied:
                continue
            db.execute(path.read_text(encoding="utf-8"))
            if path.name == "005_source_footnotes.sql":
                backfill_source_footnotes(db)
            db.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            logging.info("Применена миграция %s", path.name)


if __name__ == "__main__":
    logging.basicConfig(level=LOG_LEVEL)
    migrate()
