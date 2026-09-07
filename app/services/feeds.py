"""Minimal RSS podcast feed parsing for episode synchronisation."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from defusedxml import ElementTree as ET

from app.core.logging import get_logger
from app.services.dto import EpisodeDTO
from app.services.exceptions import ConfigError
from app.services.http import build_client, request_with_retry
from app.services.url_safety import resolve_safe_url

logger = get_logger(__name__)

_MAX_REDIRECTS = 5
_ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _parse_duration(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    try:
        if ":" in value:
            parts = [int(p) for p in value.split(":")]
            seconds = 0
            for part in parts:
                seconds = seconds * 60 + part
            return seconds
        return int(float(value))
    except ValueError:
        return None


def parse_feed(xml_text: str) -> list[EpisodeDTO]:
    root = ET.fromstring(xml_text)
    episodes: list[EpisodeDTO] = []
    for item in root.iterfind(".//item"):
        guid_el = item.find("guid")
        link_el = item.find("link")
        enclosure = item.find("enclosure")
        guid = (guid_el.text if guid_el is not None else None) or (
            link_el.text if link_el is not None else None
        )
        if not guid:
            continue
        title_el = item.find("title")
        desc_el = item.find("description")
        pub_el = item.find("pubDate")
        dur_el = item.find(f"{_ITUNES}duration")
        episodes.append(
            EpisodeDTO(
                guid=guid.strip(),
                title=(title_el.text or "").strip() if title_el is not None else "Untitled",
                description=desc_el.text if desc_el is not None else None,
                published_at=_parse_datetime(pub_el.text if pub_el is not None else None),
                audio_url=enclosure.get("url") if enclosure is not None else None,
                duration_seconds=_parse_duration(dur_el.text if dur_el is not None else None),
            )
        )
    return episodes


async def fetch_feed_episodes(rss_feed_url: str) -> list[EpisodeDTO]:
    """Fetch and parse a podcast RSS feed.

    Both the initial URL and every redirect hop are resolved and validated
    via :func:`resolve_safe_url` (public http/https hosts only), and the
    HTTP request connects to that *pinned* IP directly rather than letting
    the client re-resolve the hostname - closing the DNS-rebinding gap
    where a short-TTL hostname could pass validation but resolve to a
    private/internal address by the time the connection actually opens.
    The ``Host`` header and TLS SNI still use the original hostname (via
    the ``sni_hostname`` request extension), so certificate validation for
    HTTPS feeds is unaffected.
    """
    current_url = rss_feed_url
    async with build_client(follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            pinned = resolve_safe_url(current_url)
            headers = {"Host": pinned.hostname}
            extensions = {"sni_hostname": pinned.hostname} if pinned.scheme == "https" else None

            resp = await request_with_retry(
                client, "GET", pinned.request_url, headers=headers, extensions=extensions
            )
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise ConfigError(f"redirect from {current_url!r} missing Location header")
                current_url = urljoin(current_url, location)
                continue
            resp.raise_for_status()
            return parse_feed(resp.text)
    raise ConfigError(f"too many redirects fetching feed {rss_feed_url!r}")
