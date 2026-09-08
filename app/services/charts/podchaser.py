"""Podchaser podcast charts scraper - real GraphQL integration.

Queries ``topCharts`` on Podchaser's GraphQL API. Auth, the numeric-coercion
helper and the endpoint URLs are shared with the enrichment client via
:mod:`app.services.podchaser_api`.

Without credentials configured, :meth:`PodchaserChartScraper.fetch` logs a
warning and returns an empty list rather than raising - callers (see
``app/services/ingest.py``) already treat an empty chart as a no-op, so a
missing key degrades gracefully instead of failing the scrape task.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.dto import ChartEntryDTO
from app.services.exceptions import ConfigError
from app.services.http import build_client, request_with_retry
from app.services.podchaser_api import GRAPHQL_URL, coerce_number, fetch_access_token

logger = get_logger(__name__)

_TOP_CHARTS_QUERY = """
query TopCharts($country: String!, $category: String!, $first: Int!) {
  topCharts(filters: { country: $country, categoryName: $category }, first: $first) {
    data {
      rank
      podcast {
        title
        author
        imageUrl
        rssUrl
        webUrl
        id
        ratingAverage
        ratingCount
      }
    }
  }
}
"""


def _map_entry(rank_entry: dict[str, Any], country: str, category: str) -> ChartEntryDTO | None:
    """Map one ``topCharts`` entry to a DTO, or None if it's unusable.

    Malformed upstream data (a missing rank, title, or feed URL) skips
    just this one entry rather than raising - one bad row in an otherwise
    valid chart response must not crash the whole scrape task.
    """
    if not isinstance(rank_entry, dict):
        logger.warning("podchaser charts: skipping non-object entry %r", rank_entry)
        return None
    rank = rank_entry.get("rank")
    podcast = rank_entry.get("podcast") or {}
    if not isinstance(podcast, dict):
        logger.warning("podchaser charts: skipping entry with malformed podcast %r", rank_entry)
        return None
    rss_url = podcast.get("rssUrl")
    title = podcast.get("title")
    if not isinstance(rank, int) or not rss_url or not title:
        logger.warning("podchaser charts: skipping malformed entry %r", rank_entry)
        return None
    return ChartEntryDTO(
        rank=rank,
        source=ChartSource.PODCHASER,
        country=country,
        category=category,
        title=title,
        rss_feed_url=rss_url,
        publisher=podcast.get("author"),
        image_url=podcast.get("imageUrl"),
        rating_average=coerce_number(podcast.get("ratingAverage"), float),
        rating_count=coerce_number(podcast.get("ratingCount"), int),
        external_ids={"podchaser": str(podcast["id"])} if podcast.get("id") else {},
    )


class PodchaserChartScraper:
    source = ChartSource.PODCHASER

    async def fetch(self, country: str, category: str) -> list[ChartEntryDTO]:
        try:
            token = await fetch_access_token()
        except ConfigError as exc:
            logger.warning("podchaser charts skipped: %s", exc)
            return []

        async with build_client(headers={"Authorization": f"Bearer {token}"}) as client:
            resp = await request_with_retry(
                client,
                "POST",
                GRAPHQL_URL,
                json={
                    "query": _TOP_CHARTS_QUERY,
                    "variables": {"country": country.upper(), "category": category, "first": 50},
                },
            )
            resp.raise_for_status()
            payload = resp.json()

        if payload.get("errors"):
            logger.warning("podchaser charts graphql errors: %s", payload["errors"])
            return []

        raw_entries = ((payload.get("data") or {}).get("topCharts") or {}).get("data") or []
        entries = [e for e in (_map_entry(r, country, category) for r in raw_entries) if e]
        logger.info(
            "podchaser charts fetched country=%s category=%s entries=%d",
            country,
            category,
            len(entries),
        )
        return entries
