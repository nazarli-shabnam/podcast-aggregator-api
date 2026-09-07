"""Enrichment client registry."""

from __future__ import annotations

from app.services.enrichment.apple import AppleEnrichmentClient
from app.services.enrichment.base import EnrichmentClient
from app.services.enrichment.podcastindex import PodcastIndexEnrichmentClient

__all__ = [
    "AppleEnrichmentClient",
    "EnrichmentClient",
    "PodcastIndexEnrichmentClient",
    "default_enrichment_clients",
]


def default_enrichment_clients() -> list[EnrichmentClient]:
    """Ordered clients tried during enrichment (best-effort, keyless first)."""
    return [AppleEnrichmentClient(), PodcastIndexEnrichmentClient()]
