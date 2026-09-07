"""Enrichment client protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.dto import PodcastMetadataDTO


@runtime_checkable
class EnrichmentClient(Protocol):
    name: str

    async def enrich(
        self, *, title: str, rss_feed_url: str | None, external_ids: dict[str, str]
    ) -> PodcastMetadataDTO | None:
        """Return supplemental metadata, or ``None`` when nothing was found.

        Implementations raise :class:`app.services.exceptions.ConfigError`
        when required credentials are absent so callers can skip them.
        """
        ...
