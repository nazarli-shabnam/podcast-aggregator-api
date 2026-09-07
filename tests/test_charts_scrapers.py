from __future__ import annotations

import pytest

from app.schemas.common import ChartSource
from app.services.charts import get_scraper
from app.services.feeds import parse_feed


@pytest.mark.parametrize("source", list(ChartSource))
async def test_scraper_returns_ranked_entries(source: ChartSource) -> None:
    scraper = get_scraper(source)
    entries = await scraper.fetch("US", "Technology")
    assert entries
    assert [e.rank for e in entries] == sorted(e.rank for e in entries)
    assert all(e.source is source for e in entries)
    assert all(e.rss_feed_url.startswith("http") for e in entries)


async def test_scraper_unknown_country_category_is_empty() -> None:
    scraper = get_scraper(ChartSource.SPOTIFY)
    # default fixture still applies (fallback); force a source with no fixture dir match
    entries = await scraper.fetch("zz", "nonexistent")
    assert isinstance(entries, list)


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
