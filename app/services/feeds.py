"""Minimal RSS podcast feed parsing for episode synchronisation."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree as ET

from app.core.logging import get_logger
from app.services.dto import EpisodeDTO
from app.services.http import build_client, request_with_retry

logger = get_logger(__name__)

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
    async with build_client() as client:
        resp = await request_with_retry(client, "GET", rss_feed_url)
        resp.raise_for_status()
        return parse_feed(resp.text)
