from __future__ import annotations

import pytest

from app.schemas.common import ChartSource
from app.services.charts import get_scraper
from app.services.feeds import parse_feed


async def test_podchaser_scraper_skips_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.podchaser_client_id", None, raising=False)
    monkeypatch.setattr("app.core.config.settings.podchaser_client_secret", None, raising=False)
    scraper = get_scraper(ChartSource.PODCHASER)
    entries = await scraper.fetch("us", "technology")
    assert entries == []


def test_parse_feed_extracts_episodes() -> None:
    xml = """<?xml version='1.0'?>
    <rss><channel>
      <item>
        <title>Episode One</title>
        <guid>guid-1</guid>
        <description>Hello</description>
        <pubDate>Mon, 01 Sep 2025 10:00:00 +0000</pubDate>
        <enclosure url='https://audio.test/1.mp3' type='audio/mpeg'/>
        <itunes:duration xmlns:itunes='http://www.itunes.com/dtds/podcast-1.0.dtd'>1:30:00</itunes:duration>
      </item>
    </channel></rss>"""
    episodes = parse_feed(xml)
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.guid == "guid-1"
    assert ep.audio_url == "https://audio.test/1.mp3"
    assert ep.duration_seconds == 5400
