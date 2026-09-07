"""Spotify podcast charts scraper.

Spotify exposes no official public charts API. This scraper ships with a
stable interface and fixture-backed data; the real endpoint integration
is a Phase 2 concern.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.charts.base import load_fixture_entries
from app.services.dto import ChartEntryDTO

logger = get_logger(__name__)


class SpotifyChartScraper:
    source = ChartSource.SPOTIFY

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        # TODO(phase-2): replace with authenticated call to the Spotify charts endpoint.
        entries = load_fixture_entries(self.source, country.lower(), category.lower())
        logger.info(
            "spotify charts fetched country=%s category=%s entries=%d",
            country,
            category,
            len(entries),
        )
        return entries
