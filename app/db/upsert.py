"""Concurrency-safe UPSERT helpers for podcasts and episodes."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.normalize import normalize_categories
from app.db.models import Episode, Podcast

# ``categories`` is merged (union, de-duplicated) rather than overwritten - see
# _categories_union - so it is handled separately from the plain-overwrite columns.
_PODCAST_UPDATE_COLUMNS = (
    "title",
    "description",
    "image_url",
    "publisher",
    "rating_average",
    "rating_count",
)


def _categories_union(insert_stmt: Any) -> Any:
    """ON CONFLICT expression: existing ``categories`` ∪ incoming, de-duplicated.

    A chart scrape only knows the one chart category, so a blind overwrite would
    wipe the richer list a prior enrichment stored. Union instead, so a re-ingest
    only ever *adds*.
    """
    combined = Podcast.categories.op("||")(insert_stmt.excluded.categories)
    element = func.jsonb_array_elements_text(combined).column_valued("value")
    # Fold to the same canonical form callers use (app.core.normalize) so a
    # pre-normalisation row already in the table still converges on re-ingest.
    normalized = func.lower(func.btrim(element))
    return select(
        func.coalesce(func.jsonb_agg(normalized.distinct()), cast([], JSONB))
    ).scalar_subquery()


async def upsert_podcast(session: AsyncSession, values: dict[str, Any]) -> uuid.UUID:
    """Insert or update a podcast keyed by ``rss_feed_url``; returns its id.

    ``external_ids`` and ``categories`` are merged (existing values preserved)
    rather than replaced; every other column is overwritten. ``categories`` are
    canonicalised here (app.core.normalize) so every write path - chart ingest,
    enrichment, tests - stores the same form.
    """
    if "categories" in values:
        values = {**values, "categories": normalize_categories(values["categories"])}
    insert_stmt = pg_insert(Podcast).values(**values)
    set_: dict[str, Any] = {
        col: insert_stmt.excluded[col] for col in _PODCAST_UPDATE_COLUMNS if col in values
    }
    set_["external_ids"] = Podcast.external_ids.op("||")(insert_stmt.excluded.external_ids)
    if "categories" in values:
        set_["categories"] = _categories_union(insert_stmt)
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
