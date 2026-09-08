"""Ingestion orchestration - pure business logic, no Celery dependency."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date, datetime
from statistics import median

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import ChartSnapshot, Episode, Podcast
from app.db.upsert import upsert_episodes, upsert_podcast
from app.schemas.common import ChartSource
from app.services.charts import get_scraper
from app.services.dto import ChartEntryDTO, PodcastMetadataDTO
from app.services.enrichment import default_enrichment_clients
from app.services.enrichment.base import EnrichmentClient
from app.services.exceptions import ConfigError
from app.services.feeds import fetch_feed_episodes

logger = get_logger(__name__)


async def _resolve_podcast_id(session: AsyncSession, entry: ChartEntryDTO) -> uuid.UUID:
    values: dict[str, object] = {
        "title": entry.title,
        "publisher": entry.publisher,
        "image_url": entry.image_url,
        "rss_feed_url": entry.rss_feed_url,
        "categories": [entry.category],
        "external_ids": entry.external_ids or {},
    }
    # Only sources that actually carry ratings (Podchaser) set these. Omitting
    # the keys when absent keeps rating_count (NOT NULL) valid on INSERT and
    # leaves any existing rating untouched on a later Spotify re-ingest of the
    # same feed - see upsert_podcast's "if col in values" update filter.
    if entry.rating_average is not None:
        values["rating_average"] = entry.rating_average
    if entry.rating_count is not None:
        values["rating_count"] = entry.rating_count
    return await upsert_podcast(session, values)


async def ingest_chart(
    session: AsyncSession,
    source: ChartSource,
    country: str,
    category: str,
    snapshot_date: date | None = None,
) -> list[uuid.UUID]:
    """Scrape one chart and persist podcasts + ranked snapshot rows.

    Returns the podcast ids that appeared in the chart (for downstream enrichment).
    """
    snapshot_date = snapshot_date or date.today()
    scraper = get_scraper(source)
    entries = await scraper.fetch(country, category)
    if not entries:
        logger.warning("no entries for %s %s/%s", source.value, country, category)
        return []

    podcast_ids: list[uuid.UUID] = []
    rows: list[dict[str, object]] = []
    for entry in entries:
        podcast_id = await _resolve_podcast_id(session, entry)
        podcast_ids.append(podcast_id)
        rows.append(
            {
                "podcast_id": podcast_id,
                "rank": entry.rank,
                "source": entry.source.value,
                "country": country.lower(),
                "category": category.lower(),
                "snapshot_date": snapshot_date,
            }
        )

    stmt = pg_insert(ChartSnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_chart_snapshots_slot",
        set_={"podcast_id": stmt.excluded.podcast_id, "updated_at": func.now()},
    )
    await session.execute(stmt)

    # A same-day re-scrape (e.g. a manual retry after a partial failure)
    # can return fewer entries than an earlier successful run that day.
    # The UPSERT above only touches ranks present in *this* scrape, so
    # without this cleanup, ranks that dropped out would keep pointing at
    # a podcast from the earlier run - a stale row silently mixing two
    # different scrapes into one "snapshot". Remove any leftover ranks
    # for this exact (source, country, category, snapshot_date) slot that
    # this scrape didn't reaffirm.
    #
    # Trade-off: SpotifyChartScraper resolves a feed URL per entry and
    # silently drops any rank it can't resolve (see spotify.py) - a
    # *second* same-day scrape that transiently fails to resolve a rank
    # the first scrape resolved successfully would prune that valid row
    # here. This is already narrowed by request_with_retry's own
    # backoff/retries inside the resolution call itself, so only a
    # persistent (not transient) resolution failure on a same-day re-scrape
    # can trigger it - accepted as a reasonable trade-off rather than
    # threading "seen but unresolved" ranks through the scraper interface.
    current_ranks = {entry.rank for entry in entries}
    await session.execute(
        delete(ChartSnapshot).where(
            ChartSnapshot.source == source.value,
            ChartSnapshot.country == country.lower(),
            ChartSnapshot.category == category.lower(),
            ChartSnapshot.snapshot_date == snapshot_date,
            ChartSnapshot.rank.notin_(current_ranks),
        )
    )

    logger.info(
        "ingested %d entries for %s %s/%s @ %s",
        len(rows),
        source.value,
        country,
        category,
        snapshot_date,
    )
    return podcast_ids


def _merge_metadata(base: Podcast, meta: PodcastMetadataDTO) -> dict[str, object]:
    # Seed NOT NULL columns so the INSERT arm of the UPSERT stays valid even
    # though this row already exists (Postgres validates it before ON CONFLICT).
    payload: dict[str, object] = {
        "rss_feed_url": base.rss_feed_url,
        "title": base.title,
    }
    for field_name, value in asdict(meta).items():
        if value in (None, [], {}) or field_name == "rss_feed_url":
            continue
        # ``categories`` and ``external_ids`` are unioned with the existing row
        # inside upsert_podcast, so pass the incoming values through as-is.
        payload[field_name] = value
    return payload


async def enrich_podcast(
    session: AsyncSession,
    podcast_id: uuid.UUID,
    clients: list[EnrichmentClient] | None = None,
) -> bool:
    """Apply best-effort metadata enrichment. Returns True if anything changed."""
    podcast = await session.get(Podcast, podcast_id)
    if podcast is None:
        logger.warning("enrich: podcast %s not found", podcast_id)
        return False

    clients = clients or default_enrichment_clients()
    changed = False
    for client in clients:
        try:
            meta = await client.enrich(
                title=podcast.title,
                rss_feed_url=podcast.rss_feed_url,
                external_ids=podcast.external_ids,
            )
        except ConfigError as exc:
            logger.info("enrich: skipping %s (%s)", client.name, exc)
            continue
        if meta is None:
            continue
        await upsert_podcast(session, _merge_metadata(podcast, meta))
        await session.refresh(podcast)
        changed = True
    return changed


async def _compute_release_frequency_days(
    session: AsyncSession, podcast_id: uuid.UUID, sample_size: int = 10
) -> float | None:
    """Median days between the most recent dated episodes, or None with
    fewer than 2 to compare. No enrichment source publishes this value
    directly - it's derived from the episode history we already have.
    """
    stmt = (
        select(Episode.published_at)
        .where(Episode.podcast_id == podcast_id, Episode.published_at.is_not(None))
        .order_by(Episode.published_at.desc())
        .limit(sample_size)
    )
    dates: list[datetime] = [row[0] for row in (await session.execute(stmt)).all()]
    if len(dates) < 2:
        return None
    gaps = [(dates[i] - dates[i + 1]).total_seconds() / 86400.0 for i in range(len(dates) - 1)]
    return float(median(gaps))


async def sync_episodes(session: AsyncSession, podcast_id: uuid.UUID) -> int:
    """Fetch the podcast feed, UPSERT its episodes, and refresh the
    podcast's derived release_frequency_days. Returns rows submitted.
    """
    podcast = await session.get(Podcast, podcast_id)
    if podcast is None:
        logger.warning("sync_episodes: podcast %s not found", podcast_id)
        return 0
    episodes = await fetch_feed_episodes(podcast.rss_feed_url)
    submitted = await upsert_episodes(session, podcast_id, [asdict(ep) for ep in episodes])
    podcast.release_frequency_days = await _compute_release_frequency_days(session, podcast_id)
    return submitted


async def list_tracked_podcast_ids(session: AsyncSession, limit: int = 500) -> list[uuid.UUID]:
    """Podcasts that have appeared in a chart, most recently charted first."""
    stmt = (
        select(Podcast.id)
        .join(ChartSnapshot, ChartSnapshot.podcast_id == Podcast.id)
        .group_by(Podcast.id)
        .order_by(func.max(ChartSnapshot.snapshot_date).desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
