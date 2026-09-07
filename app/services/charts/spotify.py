"""Spotify podcast charts scraper.

Spotify publishes no official or public podcast-charts API - unlike
Podchaser (see ``app/services/charts/podchaser.py``), there is no
documented, key-authenticated endpoint to integrate against. A "real"
Spotify integration would mean scraping their unofficial charts webpage:
fragile, outside their published API surface, and liable to break
silently on markup changes. This scraper therefore stays fixture-backed
by design, not as a pending TODO - see the chart-integration design notes
in PR history for the tradeoff discussion.
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
        entries = load_fixture_entries(self.source, country.lower(), category.lower())
        logger.info(
            "spotify charts fetched country=%s category=%s entries=%d",
            country,
            category,
            len(entries),
        )
        return entries
