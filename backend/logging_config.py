from __future__ import annotations

import logging
import os

from logging.handlers import RotatingFileHandler

from .config import get_settings


def configure_logging() -> None:
    settings = get_settings()

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handlers = []

    # Vercel filesystem is read-only, skip file logging
    if os.environ.get("VERCEL") != "1":
        settings.log_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        file_handler = RotatingFileHandler(
            settings.log_path,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )

        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # Always show logs in console
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        force=True
    )