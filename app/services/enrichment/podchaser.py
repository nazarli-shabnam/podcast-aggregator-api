"""Podchaser GraphQL enrichment client.

Covers podcasts that never appear on a Podchaser chart (e.g. Spotify-only shows)
so they still receive ratings and metadata. Requires ``PODCHASER_CLIENT_ID`` /
``PODCHASER_CLIENT_SECRET``; :meth:`enrich` raises :class:`ConfigError` when they
are absent so :func:`app.services.ingest.enrich_podcast` skips it.

The GraphQL field names below match Podchaser's public schema at the time of
writing; a schema drift yields no match (``None``), never an ingestion failure.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.dto import PodcastMetadataDTO
from app.services.http import build_client, request_with_retry
from app.services.podchaser_api import (
    GRAPHQL_URL,
    coerce_number,
    fetch_access_token,
    reset_token_cache,
)

logger = get_logger(__name__)

_BY_RSS_QUERY = """
query PodcastByRss($url: String!) {
  podcast(identifier: { type: RSS, id: $url }) {
    title
    description
    author
    imageUrl
    rssUrl
    ratingAverage
    ratingCount
    categories { text }
  }
}
"""

_BY_TITLE_QUERY = """
query PodcastByTitle($term: String!) {
  podcasts(searchTerm: $term, first: 1) {
    data {
      title
      description
      author
      imageUrl
      rssUrl
      ratingAverage
      ratingCount
      categories { text }
    }
  }
}
"""


def _map_podcast(node: dict[str, Any]) -> PodcastMetadataDTO:
    categories = [
        c["text"] for c in (node.get("categories") or []) if isinstance(c, dict) and c.get("text")
    ]
    return PodcastMetadataDTO(
        title=node.get("title"),
        description=node.get("description"),
        image_url=node.get("imageUrl"),
        publisher=node.get("author"),
        rss_feed_url=node.get("rssUrl"),
        categories=categories,
        rating_average=coerce_number(node.get("ratingAverage"), float),
        rating_count=coerce_number(node.get("ratingCount"), int),
    )


class PodchaserEnrichmentClient:
    name = "podchaser"

    async def enrich(
        self, *, title: str, rss_feed_url: str | None, external_ids: dict[str, str]
    ) -> PodcastMetadataDTO | None:
        token = await fetch_access_token()  # raises ConfigError when unconfigured

        if rss_feed_url:
            query, variables = _BY_RSS_QUERY, {"url": rss_feed_url}
        else:
            query, variables = _BY_TITLE_QUERY, {"term": title}

        async with build_client(headers={"Authorization": f"Bearer {token}"}) as client:
            resp = await request_with_retry(
                client, "POST", GRAPHQL_URL, json={"query": query, "variables": variables}
            )
            if resp.status_code in (401, 403):
                # Cached token rejected (revoked / rotated). Clear it so the next
                # run re-exchanges instead of replaying it until TTL.
                reset_token_cache()
                logger.error(
                    "podchaser enrichment: auth rejected (HTTP %d) - cleared cached "
                    "access token so the next run re-exchanges",
                    resp.status_code,
                )
                return None
            resp.raise_for_status()
            payload = resp.json()

        if payload.get("errors"):
            logger.warning("podchaser enrichment graphql errors: %s", payload["errors"])
            return None

        data = payload.get("data") or {}
        node = data.get("podcast")
        if node is None:
            rows = ((data.get("podcasts") or {}).get("data")) or []
            node = rows[0] if rows else None
        if not isinstance(node, dict) or not node.get("rssUrl"):
            return None
        return _map_podcast(node)
