"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Podcast Aggregator API"
    environment: str = "local"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5433/podcasts"
    redis_url: str = "redis://localhost:6379/0"

    chart_countries: list[str] = Field(default_factory=lambda: ["us"])
    chart_categories: list[str] = Field(default_factory=lambda: ["technology"])

    podcastindex_api_key: str | None = None
    podcastindex_api_secret: str | None = None

    # HTTP client tuning
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 3
    http_rate_limit_per_second: float = 5.0

    @field_validator("chart_countries", "chart_categories", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def sync_database_url(self) -> str:
        """psycopg-compatible URL for tooling that needs a sync driver."""
        return self.database_url.replace("+asyncpg", "+psycopg")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
