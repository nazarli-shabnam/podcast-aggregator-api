"""Plain data-transfer objects passed between scrapers, enrichment and ingest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.schemas.common import ChartSource


@dataclass(slots=True)
class ChartEntryDTO:
    # ``category`` is carried through to podcasts.categories on ingest; the
    # country is taken from the ingest call's own argument, so it is not a
    # field here.
    rank: int
    source: ChartSource
    category: str
    title: str
    rss_feed_url: str
    publisher: str | None = None
    image_url: str | None = None
    rating_average: float | None = None
    rating_count: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PodcastMetadataDTO:
    title: str | None = None
    description: str | None = None
    image_url: str | None = None
    publisher: str | None = None
    rss_feed_url: str | None = None
    categories: list[str] = field(default_factory=list)
    rating_average: float | None = None
    rating_count: int | None = None
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class EpisodeDTO:
    guid: str
    title: str
    description: str | None = None
    published_at: datetime | None = None
    audio_url: str | None = None
    duration_seconds: int | None = None
