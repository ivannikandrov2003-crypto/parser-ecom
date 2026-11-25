"""Совместимая точка входа для ручного сбора новостей."""

import asyncio
import logging

from app.collection import run_once
from config import LOG_LEVEL

def main():
    logging.basicConfig(level=LOG_LEVEL)
    asyncio.run(run_once(force=True))


if __name__ == "__main__":
    main()
