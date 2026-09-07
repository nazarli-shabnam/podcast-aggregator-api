"""Concurrency-safe UPSERT helpers for podcasts and episodes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Episode, Podcast

_PODCAST_UPDATE_COLUMNS = (
    "title",
    "description",
    "image_url",
    "publisher",
    "rating_average",
    "rating_count",
    "categories",
)


async def upsert_podcast(session: AsyncSession, values: dict[str, Any]) -> uuid.UUID:
    """Insert or update a podcast keyed by ``rss_feed_url``; returns its id.

    ``external_ids`` is merged (existing keys preserved) rather than replaced.
    """
    insert_stmt = pg_insert(Podcast).values(**values)
    set_: dict[str, Any] = {
        col: insert_stmt.excluded[col] for col in _PODCAST_UPDATE_COLUMNS if col in values
    }
    set_["external_ids"] = Podcast.external_ids.op("||")(insert_stmt.excluded.external_ids)
    set_["updated_at"] = func.now()
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["rss_feed_url"],
        set_=set_,
    ).returning(Podcast.id)
    result = await session.execute(stmt)
    return uuid.UUID(str(result.scalar_one()))


async def upsert_episodes(
    session: AsyncSession, podcast_id: uuid.UUID, episodes: list[dict[str, Any]]
) -> int:
    """Bulk insert/update episodes for a podcast keyed by ``(podcast_id, guid)``.

    Returns the number of rows submitted.
    """
    if not episodes:
        return 0
    rows = [{**ep, "podcast_id": podcast_id} for ep in episodes]
    insert_stmt = pg_insert(Episode).values(rows)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["podcast_id", "guid"],
        set_={
            "title": insert_stmt.excluded.title,
            "description": insert_stmt.excluded.description,
            "published_at": insert_stmt.excluded.published_at,
            "audio_url": insert_stmt.excluded.audio_url,
            "duration_seconds": insert_stmt.excluded.duration_seconds,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return len(rows)
