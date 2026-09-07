"""Chart scraper registry."""

from __future__ import annotations

from app.schemas.common import ChartSource
from app.services.charts.base import ChartScraper
from app.services.charts.podchaser import PodchaserChartScraper
from app.services.charts.spotify import SpotifyChartScraper

_REGISTRY: dict[ChartSource, type[ChartScraper]] = {
    ChartSource.SPOTIFY: SpotifyChartScraper,
    ChartSource.PODCHASER: PodchaserChartScraper,
}


def get_scraper(source: ChartSource) -> ChartScraper:
    return _REGISTRY[source]()


__all__ = ["ChartScraper", "get_scraper", "PodchaserChartScraper", "SpotifyChartScraper"]
