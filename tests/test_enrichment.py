from __future__ import annotations

import pytest

from app.services.enrichment import apple as apple_mod
from app.services.enrichment import podcastindex as pi_mod
from app.services.enrichment.apple import AppleEnrichmentClient
from app.services.enrichment.podcastindex import PodcastIndexEnrichmentClient
from app.services.exceptions import ConfigError


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict:
        return self._payload


async def test_apple_enrich_maps_search_result(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "collectionName": "The Daily Tech Brief",
                "artistName": "Aggregator Media",
                "feedUrl": "https://feeds.example.com/daily-tech-brief",
                "artworkUrl600": "https://img/x.jpg",
                "genres": ["Podcasts", "Technology"],
                "collectionId": 42,
            }
        ]
    }

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return _FakeResp(payload)

    monkeypatch.setattr(apple_mod, "request_with_retry", _fake_request)

    meta = await AppleEnrichmentClient().enrich(
        title="The Daily Tech Brief",
        rss_feed_url="https://feeds.example.com/daily-tech-brief",
        external_ids={},
    )
    assert meta is not None
    assert meta.publisher == "Aggregator Media"
    assert meta.categories == ["Technology"]
    assert meta.external_ids == {"apple": "42"}


async def test_apple_enrich_by_id_and_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _empty(*a: object, **k: object) -> _FakeResp:
        return _FakeResp({"results": []})

    monkeypatch.setattr(apple_mod, "request_with_retry", _empty)
    meta = await AppleEnrichmentClient().enrich(
        title="x", rss_feed_url=None, external_ids={"apple": "99"}
    )
    assert meta is None


async def test_podcastindex_skips_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.podcastindex_api_key", None, raising=False)
    monkeypatch.setattr("app.core.config.settings.podcastindex_api_secret", None, raising=False)
    with pytest.raises(ConfigError):
        await PodcastIndexEnrichmentClient().enrich(title="x", rss_feed_url=None, external_ids={})


async def test_podcastindex_maps_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pi_mod, "_auth_headers", lambda: {"X-Auth-Key": "k"})
    payload = {
        "feed": {
            "id": 555,
            "title": "Deep Work Weekly",
            "description": "Focus",
            "author": "Focus Labs",
            "url": "https://feeds.example.com/deep-work-weekly",
            "image": "https://img/dw.jpg",
            "categories": {"1": "Technology", "2": "Education"},
        }
    }

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return _FakeResp(payload)

    monkeypatch.setattr(pi_mod, "request_with_retry", _fake)
    meta = await PodcastIndexEnrichmentClient().enrich(
        title="Deep Work Weekly",
        rss_feed_url="https://feeds.example.com/deep-work-weekly",
        external_ids={},
    )
    assert meta is not None
    assert meta.publisher == "Focus Labs"
    assert meta.external_ids == {"podcastindex": "555"}
    assert set(meta.categories) == {"Technology", "Education"}
