"""Podchaser podcast charts scraper.

Fixture-backed stub with a stable interface. Phase 2 swaps in the real
Podchaser GraphQL charts query.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.charts.base import load_fixture_entries
from app.services.dto import ChartEntryDTO

logger = get_logger(__name__)


class PodchaserChartScraper:
    source = ChartSource.PODCHASER

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        # TODO(phase-2): replace with Podchaser GraphQL `topCharts` query.
        entries = load_fixture_entries(self.source, country.lower(), category.lower())
        logger.info(
            "podchaser charts fetched country=%s category=%s entries=%d",
            country,
            category,
            len(entries),
        )
        return entries
