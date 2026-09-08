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


def test_podcastindex_auth_headers_with_real_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.podcastindex_api_key", "mykey", raising=False)
    monkeypatch.setattr(
        "app.core.config.settings.podcastindex_api_secret", "mysecret", raising=False
    )
    headers = pi_mod._auth_headers()
    assert headers["X-Auth-Key"] == "mykey"
    assert "X-Auth-Date" in headers
    assert len(headers["Authorization"]) == 40  # sha1 hex digest length


async def test_podcastindex_searches_by_term_without_feed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pi_mod, "_auth_headers", lambda: {"X-Auth-Key": "k"})
    seen_paths: list[str] = []

    async def _fake(client, method, path, **kwargs):  # noqa: ANN001
        seen_paths.append(path)
        return _FakeResp({"feed": {"title": "Found It", "url": "https://feeds.test/found"}})

    monkeypatch.setattr(pi_mod, "request_with_retry", _fake)
    meta = await PodcastIndexEnrichmentClient().enrich(
        title="Found It", rss_feed_url=None, external_ids={}
    )
    assert seen_paths == ["/search/byterm"]
    assert meta is not None
    assert meta.title == "Found It"


async def test_podcastindex_takes_first_of_a_feed_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pi_mod, "_auth_headers", lambda: {"X-Auth-Key": "k"})

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return _FakeResp({"feed": [{"title": "First"}, {"title": "Second"}]})

    monkeypatch.setattr(pi_mod, "request_with_retry", _fake)
    meta = await PodcastIndexEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.test/x", external_ids={}
    )
    assert meta is not None
    assert meta.title == "First"


async def test_podcastindex_returns_none_for_empty_feed_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pi_mod, "_auth_headers", lambda: {"X-Auth-Key": "k"})

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return _FakeResp({"feed": []})

    monkeypatch.setattr(pi_mod, "request_with_retry", _fake)
    meta = await PodcastIndexEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.test/x", external_ids={}
    )
    assert meta is None


async def test_podcastindex_returns_none_when_feed_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pi_mod, "_auth_headers", lambda: {"X-Auth-Key": "k"})

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return _FakeResp({})

    monkeypatch.setattr(pi_mod, "request_with_retry", _fake)
    meta = await PodcastIndexEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.test/x", external_ids={}
    )
    assert meta is None


def test_default_enrichment_clients_order() -> None:
    from app.services.enrichment import (
        AppleEnrichmentClient,
        PodcastIndexEnrichmentClient,
        default_enrichment_clients,
    )

    clients = default_enrichment_clients()
    assert isinstance(clients[0], AppleEnrichmentClient)
    assert isinstance(clients[1], PodcastIndexEnrichmentClient)


async def test_apple_enrich_falls_back_to_first_result_when_no_feed_url_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "results": [
            {
                "collectionName": "Some Other Show",
                "feedUrl": "https://feeds.example.com/some-other-show",
                "collectionId": 1,
            }
        ]
    }

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return _FakeResp(payload)

    monkeypatch.setattr(apple_mod, "request_with_retry", _fake_request)

    meta = await AppleEnrichmentClient().enrich(
        title="Some Other Show",
        rss_feed_url="https://feeds.example.com/daily-tech-brief",  # no result matches this
        external_ids={},
    )
    assert meta is not None
    assert meta.rss_feed_url == "https://feeds.example.com/some-other-show"
