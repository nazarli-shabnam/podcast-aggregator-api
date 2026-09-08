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

import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.dto import ChartEntryDTO
from app.services.enrichment.apple import AppleEnrichmentClient
from app.services.http import build_client, request_with_retry

logger = get_logger(__name__)

_CHARTS_URL = "https://podcastcharts.byspotify.com/api/charts/{category}"
_CHART_LIMIT = 50
_SLUG_NONWORD = re.compile(r"[^a-z0-9]+")


def _category_slug(category: str) -> str:
    """Map a configured category to Spotify's chart URL slug.

    Spotify uses hyphenated slugs (``true-crime``, ``society-culture``). By
    default we lower-case, drop ``&``/``and`` and collapse any run of
    non-alphanumerics to a single hyphen; ``settings.spotify_category_slugs``
    can override individual categories that don't follow that rule.

    A blank / ``top-podcasts`` category maps to the overall chart. Any *other*
    category that has no alphanumerics left after slugification (punctuation- or
    non-ASCII-only) returns ``""`` - the caller must treat that as an
    unresolvable category and fail loudly rather than silently scraping the
    overall chart under the wrong label.
    """
    key = category.strip().lower()
    if not key or key == "top-podcasts":
        return "top-podcasts"
    if key in settings.spotify_category_slugs:
        return settings.spotify_category_slugs[key]
    without_and = re.sub(r"\band\b|&", " ", key)
    return _SLUG_NONWORD.sub("-", without_and).strip("-")


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
        slug = _category_slug(category)
        if not slug:
            # A non-blank category that slugified to nothing (punctuation- or
            # non-ASCII-only). Scraping "top-podcasts" here would silently ingest
            # the overall chart tagged with this category - fail loudly instead.
            logger.error(
                "spotify charts: category %r has no usable slug; set "
                "SPOTIFY_CATEGORY_SLUGS['%s'] to its Spotify chart slug",
                category,
                category.strip().lower(),
            )
            return []
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
            # Most often an unknown genre slug - Spotify answers with a
            # non-list body. ERROR so a mis-configured CHART_CATEGORIES entry
            # isn't lost in warning noise.
            logger.error(
                "spotify charts: unexpected response shape for region=%s slug=%s "
                "(check the category slug / SPOTIFY_CATEGORY_SLUGS)",
                country,
                slug,
            )
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
