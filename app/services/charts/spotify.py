"""Spotify podcast charts scraper - real integration.

Spotify publishes no official partner API for charts, but
https://podcastcharts.byspotify.com/{country}/{category} is a public page
backed by an unauthenticated JSON endpoint that page itself calls:
``GET https://podcastcharts.byspotify.com/api/charts/{category}?region={cc}&limit=N``
(``category`` is ``top-podcasts`` for the overall chart, or a slug like
``technology`` / ``true-crime`` / ``health-fitness`` for genre charts;
verified against the live site, including non-US regions).

That response has no RSS feed URL - only a Spotify ``showUri`` - because
many charted shows (Spotify-exclusive/licensed ones especially) have no
public feed at all. Each entry's feed is resolved via the existing,
keyless Apple iTunes Search enrichment client
(:mod:`app.services.enrichment.apple`); a show with no resolvable feed is
skipped (logged), not treated as a scrape failure.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.dto import ChartEntryDTO
from app.services.enrichment.apple import AppleEnrichmentClient
from app.services.http import build_client, request_with_retry

logger = get_logger(__name__)

_CHARTS_URL = "https://podcastcharts.byspotify.com/api/charts/{category}"
_CHART_LIMIT = 50


async def _resolve_feed_url(show_name: str, publisher: str | None) -> str | None:
    try:
        meta = await AppleEnrichmentClient().enrich(
            title=show_name, rss_feed_url=None, external_ids={}
        )
    except Exception as exc:  # noqa: BLE001 - one bad lookup must not abort the scrape
        logger.warning("spotify charts: feed lookup failed for %r: %s", show_name, exc)
        return None
    if meta is None or not meta.rss_feed_url:
        logger.warning(
            "spotify charts: no public RSS feed found for %r (publisher=%r) - skipping",
            show_name,
            publisher,
        )
        return None
    return meta.rss_feed_url


def _is_usable_entry(item: object) -> bool:
    return isinstance(item, dict) and bool(item.get("showName"))


class SpotifyChartScraper:
    source = ChartSource.SPOTIFY

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        slug = "top-podcasts" if category.lower() in ("", "top-podcasts") else category.lower()
        async with build_client() as client:
            resp = await request_with_retry(
                client,
                "GET",
                _CHARTS_URL.format(category=slug),
                params={"region": country.lower(), "limit": _CHART_LIMIT},
            )
            resp.raise_for_status()
            raw_items = resp.json()

        if not isinstance(raw_items, list):
            logger.warning("spotify charts: unexpected response shape for %s/%s", country, slug)
            return []

        entries: list[ChartEntryDTO] = []
        for rank, item in enumerate(raw_items, start=1):
            if not _is_usable_entry(item):
                logger.warning("spotify charts: skipping malformed entry %r", item)
                continue
            item_dict: dict[str, Any] = item
            show_name = item_dict["showName"]
            publisher = item_dict.get("showPublisher")

            feed_url = await _resolve_feed_url(show_name, publisher)
            if not feed_url:
                continue

            show_uri = item_dict.get("showUri")
            entries.append(
                ChartEntryDTO(
                    rank=rank,
                    source=self.source,
                    country=country,
                    category=category,
                    title=show_name,
                    rss_feed_url=feed_url,
                    publisher=publisher,
                    image_url=item_dict.get("showImageUrl"),
                    external_ids={"spotify": show_uri} if show_uri else {},
                )
            )

        logger.info(
            "spotify charts fetched country=%s category=%s entries=%d/%d",
            country,
            category,
            len(entries),
            len(raw_items),
        )
        return entries
