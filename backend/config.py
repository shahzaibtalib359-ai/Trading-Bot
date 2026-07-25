from functools import lru_cache
from pathlib import Path
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # Vercel filesystem is read-only
    if os.environ.get("VERCEL") != "1":
        settings.database_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        settings.log_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

    return settings