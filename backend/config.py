from functools import lru_cache
from pathlib import Path
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "AI Trading Signal Engine"
    environment: str = "development"
    database_type: str = "sqlite"

    firebase_credentials_path: Path = BASE_DIR / "firebase-credentials.json"
    firebase_credentials_json: str | None = None

    database_path: Path = BASE_DIR / "backend" / "database" / "signals.sqlite3"
    log_path: Path = BASE_DIR / "logs" / "backend.log"

    cors_origins: list[str] = ["*"]

    market_provider: str = "auto"

    external_market_api_url: str | None = None
    external_market_api_key: str | None = None

    quotex_api_url: str | None = None
    quotex_api_key: str | None = None
    quotex_ssid: str | None = None

    xm_api_url: str | None = None
    xm_api_key: str | None = None

    binance_api_url: str = "https://api.binance.com"
    binance_api_key: str | None = None
    binance_secret_key: str | None = None

    max_quotex_data_age_seconds: int = 180

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRADING_"
    )


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