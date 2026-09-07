"""Podcast response schemas."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import CursorPage
from app.schemas.episode import EpisodeRead


class PodcastBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    publisher: str | None = None
    image_url: str | None = None
    categories: list[str] = []
    rating_average: Decimal | None = None
    rating_count: int = 0


class PodcastListItem(PodcastBase):
    pass


class PodcastRead(PodcastBase):
    description: str | None = None
    rss_feed_url: str
    external_ids: dict[str, str] = {}
    release_frequency_days: Decimal | None = None


class PodcastDetail(PodcastRead):
    episodes: CursorPage[EpisodeRead]
