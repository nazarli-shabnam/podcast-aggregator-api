"""Pytest fixtures: migrated test database, rolled-back sessions, API client."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5433/podcasts_test",
    ),
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("API_KEYS", "test-key")

TEST_API_KEY = os.environ["API_KEYS"].split(",")[0].strip()


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    from app.core.config import settings

    sync_engine = create_engine(settings.sync_database_url)
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    sync_engine.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(TEST_DATABASE_URL)
    conn = await engine.connect()
    trans = await conn.begin()
    maker = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = maker()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.fixture
def stub_spotify_scraper(monkeypatch: pytest.MonkeyPatch):
    """Patch chart ingestion to a fast, offline, deterministic Spotify
    chart - both SpotifyChartScraper and PodchaserChartScraper make real
    network calls now, so any test exercising ingest_chart()/get_scraper()
    generically (not specifically testing a real scraper's own HTTP/parsing
    logic) should use this instead of hitting the live internet.
    """
    from app.schemas.common import ChartSource
    from app.services import ingest as ingest_mod
    from app.services.dto import ChartEntryDTO

    entries = [
        ChartEntryDTO(
            rank=1,
            source=ChartSource.SPOTIFY,
            country="us",
            category="technology",
            title="The Daily Tech Brief",
            rss_feed_url="https://feeds.test/daily-tech-brief",
            publisher="Aggregator Media",
        ),
        ChartEntryDTO(
            rank=2,
            source=ChartSource.SPOTIFY,
            country="us",
            category="technology",
            title="Founders & Funders",
            rss_feed_url="https://feeds.test/founders-and-funders",
            publisher="Startup Studio",
        ),
        ChartEntryDTO(
            rank=3,
            source=ChartSource.SPOTIFY,
            country="us",
            category="technology",
            title="Signal & Noise",
            rss_feed_url="https://feeds.test/signal-and-noise",
            publisher="Independent",
        ),
    ]

    class _Stub:
        source = ChartSource.SPOTIFY

        async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
            return entries

    monkeypatch.setattr(ingest_mod, "get_scraper", lambda _source: _Stub())
    return entries


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app.core.db import get_session
    from app.main import app

    async def _override() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-API-Key": TEST_API_KEY},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
