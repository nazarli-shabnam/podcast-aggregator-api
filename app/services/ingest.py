"""Ingestion orchestration - pure business logic, no Celery dependency."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import ChartSnapshot, Podcast
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
    return await upsert_podcast(
        session,
        {
            "title": entry.title,
            "publisher": entry.publisher,
            "image_url": entry.image_url,
            "rss_feed_url": entry.rss_feed_url,
            "categories": [entry.category],
            "external_ids": entry.external_ids or {},
        },
    )


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
        if field_name == "categories":
            merged = sorted({*base.categories, *value})
            payload["categories"] = merged
        elif field_name == "external_ids":
            payload["external_ids"] = {**base.external_ids, **value}
        else:
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


async def sync_episodes(session: AsyncSession, podcast_id: uuid.UUID) -> int:
    """Fetch the podcast feed and UPSERT its episodes. Returns rows submitted."""
    podcast = await session.get(Podcast, podcast_id)
    if podcast is None:
        logger.warning("sync_episodes: podcast %s not found", podcast_id)
        return 0
    episodes = await fetch_feed_episodes(podcast.rss_feed_url)
    return await upsert_episodes(session, podcast_id, [asdict(ep) for ep in episodes])


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
