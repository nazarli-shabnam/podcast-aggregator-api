"""Apple Podcasts (iTunes Search API) enrichment client - keyless."""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.services.dto import PodcastMetadataDTO
from app.services.http import build_client, request_with_retry

logger = get_logger(__name__)

_SEARCH_URL = "https://itunes.apple.com/search"
_LOOKUP_URL = "https://itunes.apple.com/lookup"


def _map_result(result: dict[str, Any]) -> PodcastMetadataDTO:
    genres = [g for g in result.get("genres", []) if g and g != "Podcasts"]
    apple_id = result.get("collectionId") or result.get("trackId")
    return PodcastMetadataDTO(
        title=result.get("collectionName") or result.get("trackName"),
        publisher=result.get("artistName"),
        image_url=result.get("artworkUrl600") or result.get("artworkUrl100"),
        rss_feed_url=result.get("feedUrl"),
        categories=genres,
        external_ids={"apple": str(apple_id)} if apple_id else {},
    )


class AppleEnrichmentClient:
    name = "apple"

    async def enrich(
        self, *, title: str, rss_feed_url: str | None, external_ids: dict[str, str]
    ) -> PodcastMetadataDTO | None:
        async with build_client() as client:
            apple_id = external_ids.get("apple")
            if apple_id:
                resp = await request_with_retry(
                    client, "GET", _LOOKUP_URL, params={"id": apple_id, "entity": "podcast"}
                )
            else:
                resp = await request_with_retry(
                    client,
                    "GET",
                    _SEARCH_URL,
                    params={"term": title, "entity": "podcast", "limit": 5},
                )
            resp.raise_for_status()
            payload = resp.json()

        results: list[dict[str, Any]] = payload.get("results", [])
        if not results:
            return None

        if rss_feed_url:
            for result in results:
                if result.get("feedUrl") == rss_feed_url:
                    return _map_result(result)
        return _map_result(results[0])
