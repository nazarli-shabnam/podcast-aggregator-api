from __future__ import annotations

import pytest

from app.schemas.common import ChartSource
from app.services.charts import spotify as spotify_mod
from app.services.charts.spotify import SpotifyChartScraper
from app.services.dto import PodcastMetadataDTO


class _FakeResp:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


async def test_fetch_maps_entries_and_resolves_feed_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_payload = [
        {
            "showUri": "spotify:show:abc123",
            "showName": "Founders & Funders",
            "showPublisher": "Startup Studio",
            "showImageUrl": "https://img/f.jpg",
            "showDescription": "Startups.",
        },
        {
            "showUri": "spotify:show:def456",
            "showName": "Exclusive Only Show",
            "showPublisher": "Spotify Studios",
            "showImageUrl": "https://img/e.jpg",
            "showDescription": "No public feed.",
        },
    ]

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        assert "podcastcharts.byspotify.com" in url
        assert kwargs["params"] == {"region": "us", "limit": spotify_mod._CHART_LIMIT}
        return _FakeResp(chart_payload)

    async def _fake_enrich(self, *, title, rss_feed_url, external_ids):  # noqa: ANN001
        if title == "Founders & Funders":
            return PodcastMetadataDTO(rss_feed_url="https://feeds.example.com/founders")
        return None  # simulates a Spotify-exclusive show with no public RSS feed

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)
    monkeypatch.setattr(spotify_mod.AppleEnrichmentClient, "enrich", _fake_enrich)

    entries = await SpotifyChartScraper().fetch("us", "technology")

    assert len(entries) == 1
    entry = entries[0]
    assert entry.rank == 1  # original chart position, not renumbered after the skip
    assert entry.source is ChartSource.SPOTIFY
    assert entry.title == "Founders & Funders"
    assert entry.rss_feed_url == "https://feeds.example.com/founders"
    assert entry.external_ids == {"spotify": "spotify:show:abc123"}


async def test_fetch_skips_entry_without_apple_match(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_payload = [
        {"showUri": "spotify:show:x", "showName": "Exclusive Show", "showPublisher": "Spotify"}
    ]

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        return _FakeResp(chart_payload)

    async def _fake_enrich(self, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)
    monkeypatch.setattr(spotify_mod.AppleEnrichmentClient, "enrich", _fake_enrich)

    assert await SpotifyChartScraper().fetch("us", "technology") == []


async def test_fetch_skips_malformed_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    chart_payload = ["not a dict", {"showPublisher": "no name field"}, None]

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        return _FakeResp(chart_payload)

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)

    assert await SpotifyChartScraper().fetch("us", "technology") == []


async def test_fetch_handles_unexpected_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        return _FakeResp({"not": "a list"})

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)

    assert await SpotifyChartScraper().fetch("us", "technology") == []


async def test_fetch_uses_top_podcasts_slug_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    seen_urls: list[str] = []

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        seen_urls.append(url)
        return _FakeResp([])

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)
    await SpotifyChartScraper().fetch("us", "")
    assert seen_urls == ["https://podcastcharts.byspotify.com/api/charts/top-podcasts"]


def test_category_slug_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spotify_mod.settings, "spotify_category_slugs", {}, raising=False)
    assert spotify_mod._category_slug("") == "top-podcasts"
    assert spotify_mod._category_slug("Technology") == "technology"
    assert spotify_mod._category_slug("True Crime") == "true-crime"
    assert spotify_mod._category_slug("Society & Culture") == "society-culture"
    assert spotify_mod._category_slug("Health & Fitness") == "health-fitness"


def test_category_slug_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        spotify_mod.settings,
        "spotify_category_slugs",
        {"kids & family": "kids-family-custom"},
        raising=False,
    )
    assert spotify_mod._category_slug("Kids & Family") == "kids-family-custom"


def test_category_slug_empty_for_unresolvable_category(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-blank category that slugifies to nothing must return "" - never a
    silent fall-back to the overall top-podcasts chart."""
    monkeypatch.setattr(spotify_mod.settings, "spotify_category_slugs", {}, raising=False)
    assert spotify_mod._category_slug("!!!") == ""
    assert spotify_mod._category_slug("日本語") == ""
    # blank / explicit top-podcasts still map to the overall chart
    assert spotify_mod._category_slug("") == "top-podcasts"
    assert spotify_mod._category_slug("top-podcasts") == "top-podcasts"


async def test_fetch_fails_loudly_for_unresolvable_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch() must not hit the network (which would return the overall chart)
    for a category with no usable slug - it returns [] like the unknown-slug path."""
    monkeypatch.setattr(spotify_mod.settings, "spotify_category_slugs", {}, raising=False)
    called = False

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        nonlocal called
        called = True
        return _FakeResp([])

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)

    assert await SpotifyChartScraper().fetch("us", "日本語") == []
    assert called is False


def test_spotify_category_slugs_parses_env_string() -> None:
    from app.core.config import Settings

    parsed = Settings(
        spotify_category_slugs="Society & Culture=society-culture, Kids & Family = kids-family "
    ).spotify_category_slugs
    assert parsed == {"society & culture": "society-culture", "kids & family": "kids-family"}


def test_spotify_category_slugs_drops_malformed_pairs() -> None:
    from app.core.config import Settings

    parsed = Settings(
        spotify_category_slugs="good=g, nokey, =noval, noval=, x = y"
    ).spotify_category_slugs
    assert parsed == {"good": "g", "x": "y"}


async def test_feed_resolution_failure_is_caught_and_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_payload = [{"showUri": "spotify:show:x", "showName": "Flaky Show"}]

    async def _fake_request(client, method, url, **kwargs):  # noqa: ANN001
        return _FakeResp(chart_payload)

    async def _raising_enrich(self, **kwargs):  # noqa: ANN001
        raise RuntimeError("upstream boom")

    monkeypatch.setattr(spotify_mod, "request_with_retry", _fake_request)
    monkeypatch.setattr(spotify_mod.AppleEnrichmentClient, "enrich", _raising_enrich)

    # One flaky lookup must not raise out of fetch() - it's skipped.
    assert await SpotifyChartScraper().fetch("us", "technology") == []
