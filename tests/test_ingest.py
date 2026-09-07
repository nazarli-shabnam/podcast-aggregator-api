from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import ChartSnapshot, Podcast
from app.schemas.common import ChartSource
from app.services import ingest as ingest_mod
from app.services.dto import EpisodeDTO, PodcastMetadataDTO
from app.services.exceptions import ConfigError
from app.services.ingest import (
    enrich_podcast,
    ingest_chart,
    list_tracked_podcast_ids,
    sync_episodes,
)


async def test_ingest_chart_is_idempotent(db_session, stub_spotify_scraper) -> None:
    ids1 = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    ids2 = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    assert ids1 == ids2

    count = await db_session.scalar(select(func.count()).select_from(ChartSnapshot))
    assert count == len(ids1)


async def test_ingest_chart_removes_stale_ranks_on_same_day_reingest(
    db_session, monkeypatch
) -> None:
    """Regression test: a same-day re-scrape that returns fewer entries
    than an earlier run must not leave stale rows at the dropped ranks -
    those would keep pointing at podcasts from the earlier, larger scrape.
    """
    from datetime import date

    from app.services.dto import ChartEntryDTO

    def _make_scraper(entries: list[ChartEntryDTO]):
        class _Stub:
            source = ChartSource.SPOTIFY

            async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
                return entries

        return _Stub()

    today = date.today()
    full_chart = [
        ChartEntryDTO(
            rank=i,
            source=ChartSource.SPOTIFY,
            country="us",
            category="technology",
            title=f"Show {i}",
            rss_feed_url=f"https://feeds.test/show-{i}",
        )
        for i in (1, 2, 3)
    ]
    monkeypatch.setattr(ingest_mod, "get_scraper", lambda _s: _make_scraper(full_chart))
    ids_full = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology", today)
    assert len(ids_full) == 3

    shrunk_chart = [full_chart[0]]  # only rank 1 this time
    monkeypatch.setattr(ingest_mod, "get_scraper", lambda _s: _make_scraper(shrunk_chart))
    await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology", today)

    remaining_ranks = (
        (
            await db_session.execute(
                select(ChartSnapshot.rank).where(
                    ChartSnapshot.source == "spotify",
                    ChartSnapshot.country == "us",
                    ChartSnapshot.category == "technology",
                    ChartSnapshot.snapshot_date == today,
                )
            )
        )
        .scalars()
        .all()
    )
    assert sorted(remaining_ranks) == [1]


async def test_ingest_chart_empty_source_returns_nothing(db_session, monkeypatch) -> None:
    class _Empty:
        source = ChartSource.SPOTIFY

        async def fetch(self, country: str, category: str):
            return []

    monkeypatch.setattr(ingest_mod, "get_scraper", lambda _s: _Empty())
    assert await ingest_chart(db_session, ChartSource.SPOTIFY, "zz", "none") == []


async def test_enrich_podcast_merges_metadata(db_session, stub_spotify_scraper) -> None:
    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    pid = ids[0]

    class _Client:
        name = "fake"

        async def enrich(self, *, title, rss_feed_url, external_ids):
            return PodcastMetadataDTO(
                description="Enriched!",
                categories=["news"],
                external_ids={"apple": "a99"},
            )

    changed = await enrich_podcast(db_session, pid, clients=[_Client()])
    assert changed is True
    podcast = await db_session.get(Podcast, pid)
    assert podcast.description == "Enriched!"
    assert "news" in podcast.categories
    assert podcast.external_ids["apple"] == "a99"


async def test_enrich_podcast_handles_config_error(db_session, stub_spotify_scraper) -> None:
    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")

    class _Broken:
        name = "broken"

        async def enrich(self, **_):
            raise ConfigError("no creds")

    assert await enrich_podcast(db_session, ids[0], clients=[_Broken()]) is False


async def test_enrich_missing_podcast_returns_false(db_session) -> None:
    import uuid

    assert await enrich_podcast(db_session, uuid.uuid4(), clients=[]) is False


async def test_sync_episodes_upserts_from_feed(
    db_session, monkeypatch, stub_spotify_scraper
) -> None:
    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")

    async def _fake_fetch(url: str):
        return [EpisodeDTO(guid="e1", title="One"), EpisodeDTO(guid="e2", title="Two")]

    monkeypatch.setattr(ingest_mod, "fetch_feed_episodes", _fake_fetch)
    assert await sync_episodes(db_session, ids[0]) == 2


async def test_sync_episodes_computes_release_frequency(
    db_session, monkeypatch, stub_spotify_scraper
) -> None:
    from datetime import UTC, datetime, timedelta

    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    base = datetime(2025, 1, 1, tzinfo=UTC)

    async def _fake_fetch(url: str):
        return [
            EpisodeDTO(guid="e1", title="One", published_at=base),
            EpisodeDTO(guid="e2", title="Two", published_at=base + timedelta(days=7)),
            EpisodeDTO(guid="e3", title="Three", published_at=base + timedelta(days=14)),
        ]

    monkeypatch.setattr(ingest_mod, "fetch_feed_episodes", _fake_fetch)
    await sync_episodes(db_session, ids[0])

    podcast = await db_session.get(Podcast, ids[0])
    assert podcast.release_frequency_days == 7


async def test_sync_episodes_frequency_stays_none_with_fewer_than_two_dated(
    db_session, monkeypatch, stub_spotify_scraper
) -> None:
    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")

    async def _fake_fetch(url: str):
        return [EpisodeDTO(guid="e1", title="One", published_at=None)]

    monkeypatch.setattr(ingest_mod, "fetch_feed_episodes", _fake_fetch)
    await sync_episodes(db_session, ids[0])

    podcast = await db_session.get(Podcast, ids[0])
    assert podcast.release_frequency_days is None


async def test_list_tracked_podcast_ids(db_session, stub_spotify_scraper) -> None:
    ids = await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    tracked = await list_tracked_podcast_ids(db_session)
    assert set(tracked) == set(ids)
