"""Podcast Index API enrichment client.

Requires ``PODCASTINDEX_API_KEY`` / ``PODCASTINDEX_API_SECRET``. When they
are absent, :meth:`enrich` raises :class:`ConfigError` and callers skip it.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.dto import PodcastMetadataDTO
from app.services.exceptions import ConfigError
from app.services.http import build_client, request_with_retry

logger = get_logger(__name__)

_BASE_URL = "https://api.podcastindex.org/api/1.0"


def _auth_headers() -> dict[str, str]:
    key = settings.podcastindex_api_key
    secret = settings.podcastindex_api_secret
    if not key or not secret:
        raise ConfigError("PODCASTINDEX_API_KEY / PODCASTINDEX_API_SECRET not configured")
    now = str(int(time.time()))
    digest = hashlib.sha1(f"{key}{secret}{now}".encode()).hexdigest()  # noqa: S324 - API spec
    return {
        "User-Agent": "podcast-aggregator/0.1",
        "X-Auth-Key": key,
        "X-Auth-Date": now,
        "Authorization": digest,
    }


def _map_feed(feed: dict[str, Any]) -> PodcastMetadataDTO:
    categories = list((feed.get("categories") or {}).values())
    return PodcastMetadataDTO(
        title=feed.get("title"),
        description=feed.get("description"),
        image_url=feed.get("image") or feed.get("artwork"),
        publisher=feed.get("author"),
        rss_feed_url=feed.get("url"),
        categories=[str(c) for c in categories],
        external_ids={"podcastindex": str(feed["id"])} if feed.get("id") else {},
    )


class PodcastIndexEnrichmentClient:
    name = "podcastindex"

    async def enrich(
        self, *, title: str, rss_feed_url: str | None, external_ids: dict[str, str]
    ) -> PodcastMetadataDTO | None:
        headers = _auth_headers()
        async with build_client(base_url=_BASE_URL, headers=headers) as client:
            if rss_feed_url:
                resp = await request_with_retry(
                    client, "GET", "/podcasts/byfeedurl", params={"url": rss_feed_url}
                )
            else:
                resp = await request_with_retry(
                    client, "GET", "/search/byterm", params={"q": title, "max": 1}
                )
            resp.raise_for_status()
            payload = resp.json()

        feed = payload.get("feed")
        if isinstance(feed, list):
            feed = feed[0] if feed else None
        if not feed:
            return None
        return _map_feed(feed)
