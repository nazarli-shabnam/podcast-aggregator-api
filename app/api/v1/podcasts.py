"""Podcast list & detail endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.cursor import decode_cursor, encode_cursor
from app.api.deps import PageParams, page_params
from app.core.db import get_session
from app.db.models import Episode, Podcast
from app.schemas.common import CursorPage, Page
from app.schemas.episode import EpisodeRead
from app.schemas.podcast import PodcastDetail, PodcastListItem

router = APIRouter(tags=["podcasts"])


@router.get("/podcasts", response_model=Page[PodcastListItem])
async def list_podcasts(
    params: PageParams = Depends(page_params),
    q: str | None = Query(None, description="Title/publisher search (ILIKE)"),
    category: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> Page[PodcastListItem]:
    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Podcast.title.ilike(pattern), Podcast.publisher.ilike(pattern)))
    if category:
        filters.append(Podcast.categories.contains([category]))

    total = await session.scalar(select(func.count()).select_from(Podcast).where(*filters))
    rows = (
        (
            await session.execute(
                select(Podcast)
                .where(*filters)
                .order_by(Podcast.rating_count.desc(), Podcast.title)
                .offset(params.offset)
                .limit(params.page_size)
            )
        )
        .scalars()
        .all()
    )

    return Page[PodcastListItem](
        items=[PodcastListItem.model_validate(row) for row in rows],
        total=total or 0,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/podcasts/{podcast_id}", response_model=PodcastDetail)
async def get_podcast(
    podcast_id: uuid.UUID,
    cursor: str | None = Query(None, description="Opaque episode pagination cursor"),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PodcastDetail:
    podcast = await session.get(Podcast, podcast_id)
    if podcast is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="podcast not found")

    # Sort/keyset key: NULL published_at coalesces to "now" so undated
    # episodes surface first. The cursor MUST encode this same coalesced
    # value (not the raw, possibly-NULL published_at) - otherwise a page
    # boundary landing on an undated episode encodes a NULL-derived
    # sentinel that doesn't match what was actually used to order it,
    # and the next page's filter silently excludes every remaining row.
    sort_key = func.coalesce(Episode.published_at, func.now()).label("sort_key")
    stmt = select(Episode, sort_key).where(Episode.podcast_id == podcast_id)
    if cursor:
        ts, last_id = decode_cursor(cursor)
        stmt = stmt.where(or_(sort_key < ts, and_(sort_key == ts, Episode.id < last_id)))
    stmt = stmt.order_by(sort_key.desc(), Episode.id.desc()).limit(limit + 1)

    rows = list((await session.execute(stmt)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    episodes = [row[0] for row in rows]
    next_cursor = encode_cursor(rows[-1][1], rows[-1][0].id) if has_more and rows else None

    return PodcastDetail(
        **PodcastListItem.model_validate(podcast).model_dump(),
        description=podcast.description,
        rss_feed_url=podcast.rss_feed_url,
        external_ids=podcast.external_ids,
        episodes=CursorPage[EpisodeRead](
            items=[EpisodeRead.model_validate(ep) for ep in episodes],
            next_cursor=next_cursor,
            limit=limit,
        ),
    )
