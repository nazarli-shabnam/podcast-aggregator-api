"""Chart scraper protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.common import ChartSource
from app.services.dto import ChartEntryDTO


@runtime_checkable
class ChartScraper(Protocol):
    source: ChartSource

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        """Return the ranked chart for a country/category."""
        ...
