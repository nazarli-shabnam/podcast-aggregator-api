"""Chart scraper protocol and shared fixture loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.schemas.common import ChartSource
from app.services.dto import ChartEntryDTO

_FIXTURE_DIR = Path(__file__).parent / "_fixtures"


@runtime_checkable
class ChartScraper(Protocol):
    source: ChartSource

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        """Return the ranked chart for a country/category."""
        ...


def load_fixture_entries(source: ChartSource, country: str, category: str) -> list[ChartEntryDTO]:
    """Load bundled fixture data for a source.

    Falls back to the source's default fixture when a specific
    country/category file is not present.
    """
    candidates = [
        _FIXTURE_DIR / f"{source.value}_{country}_{category}.json",
        _FIXTURE_DIR / f"{source.value}_default.json",
    ]
    path = next((c for c in candidates if c.exists()), None)
    if path is None:
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        ChartEntryDTO(
            rank=item["rank"],
            source=source,
            country=country,
            category=category,
            title=item["title"],
            rss_feed_url=item["rss_feed_url"],
            publisher=item.get("publisher"),
            image_url=item.get("image_url"),
            external_ids=item.get("external_ids", {}),
        )
        for item in raw["entries"]
    ]
