from __future__ import annotations

import pytest

from app.services.enrichment import apple as apple_mod
from app.services.enrichment import podcastindex as pi_mod
from app.services.enrichment import podchaser as pc_enrich_mod
from app.services.enrichment.apple import AppleEnrichmentClient
from app.services.enrichment.podcastindex import PodcastIndexEnrichmentClient
from app.services.enrichment.podchaser import PodchaserEnrichmentClient
from app.services.exceptions import ConfigError


class _FakeResp:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

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


async def test_apple_enrich_maps_ratings(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "collectionName": "Rated Show",
                "feedUrl": "https://feeds.example.com/rated",
                "collectionId": 7,
                "averageUserRating": 4.7,
                "userRatingCount": 1234,
            }
        ]
    }

    async def _fake_request(*a: object, **k: object) -> _FakeResp:
        return _FakeResp(payload)

    monkeypatch.setattr(apple_mod, "request_with_retry", _fake_request)
    meta = await AppleEnrichmentClient().enrich(
        title="Rated Show", rss_feed_url="https://feeds.example.com/rated", external_ids={}
    )
    assert meta is not None
    assert meta.rating_average == 4.7
    assert meta.rating_count == 1234


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"userRatingCount": 0}, id="count-only-no-avg"),
        pytest.param({"averageUserRating": 0, "userRatingCount": 0}, id="explicit-zero-avg"),
        pytest.param({"averageUserRating": 0.0, "userRatingCount": 812}, id="zero-avg-real-count"),
    ],
)
async def test_apple_enrich_omits_rating_when_average_absent_or_zero(
    monkeypatch: pytest.MonkeyPatch, extra: dict[str, object]
) -> None:
    """iTunes returns averageUserRating 0 (or omits it) for a show with no
    ratings in the queried storefront. Neither shape may surface a rating - it
    would clobber a real rating from another source downstream."""
    payload = {
        "results": [
            {
                "collectionName": "Unrated Show",
                "feedUrl": "https://feeds.example.com/unrated",
                **extra,
            }
        ]
    }

    async def _fake_request(*a: object, **k: object) -> _FakeResp:
        return _FakeResp(payload)

    monkeypatch.setattr(apple_mod, "request_with_retry", _fake_request)
    meta = await AppleEnrichmentClient().enrich(
        title="Unrated Show", rss_feed_url="https://feeds.example.com/unrated", external_ids={}
    )
    assert meta is not None
    assert meta.rating_average is None
    assert meta.rating_count is None


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
        PodchaserEnrichmentClient,
        default_enrichment_clients,
    )

    clients = default_enrichment_clients()
    assert isinstance(clients[0], AppleEnrichmentClient)
    assert isinstance(clients[1], PodcastIndexEnrichmentClient)
    assert isinstance(clients[2], PodchaserEnrichmentClient)


def _pc_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.podchaser_client_id", "cid", raising=False)
    monkeypatch.setattr("app.core.config.settings.podchaser_client_secret", "sec", raising=False)


async def test_podchaser_enrichment_skips_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.core.config.settings.podchaser_client_id", None, raising=False)
    monkeypatch.setattr("app.core.config.settings.podchaser_client_secret", None, raising=False)
    with pytest.raises(ConfigError):
        await PodchaserEnrichmentClient().enrich(title="x", rss_feed_url=None, external_ids={})


async def test_podchaser_enrichment_maps_podcast_by_rss(monkeypatch: pytest.MonkeyPatch) -> None:
    _pc_creds(monkeypatch)
    responses = [
        _FakeResp({"access_token": "tok"}),
        _FakeResp(
            {
                "data": {
                    "podcast": {
                        "title": "Indie Waves",
                        "description": "Indie music talk",
                        "author": "Indie Media",
                        "imageUrl": "https://img/iw.jpg",
                        "rssUrl": "https://feeds.example.com/indie-waves",
                        "ratingAverage": 4.8,
                        "ratingCount": 2100,
                        "categories": [{"text": "Music"}, {"text": "Arts"}],
                    }
                }
            }
        ),
    ]

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr("app.services.podchaser_api.request_with_retry", _fake)
    monkeypatch.setattr(pc_enrich_mod, "request_with_retry", _fake)

    meta = await PodchaserEnrichmentClient().enrich(
        title="Indie Waves",
        rss_feed_url="https://feeds.example.com/indie-waves",
        external_ids={},
    )
    assert meta is not None
    assert meta.publisher == "Indie Media"
    assert meta.rating_average == 4.8
    assert meta.rating_count == 2100
    assert set(meta.categories) == {"Music", "Arts"}


async def test_podchaser_enrichment_returns_none_on_graphql_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pc_creds(monkeypatch)
    responses = [_FakeResp({"access_token": "tok"}), _FakeResp({"errors": [{"message": "nope"}]})]

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr("app.services.podchaser_api.request_with_retry", _fake)
    monkeypatch.setattr(pc_enrich_mod, "request_with_retry", _fake)

    meta = await PodchaserEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.example.com/x", external_ids={}
    )
    assert meta is None


async def test_podchaser_enrichment_returns_none_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pc_creds(monkeypatch)
    responses = [_FakeResp({"access_token": "tok"}), _FakeResp({"data": {"podcast": None}})]

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr("app.services.podchaser_api.request_with_retry", _fake)
    monkeypatch.setattr(pc_enrich_mod, "request_with_retry", _fake)

    meta = await PodchaserEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.example.com/missing", external_ids={}
    )
    assert meta is None


async def test_podchaser_enrichment_title_search_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _pc_creds(monkeypatch)
    seen: list[str] = []
    responses = [
        _FakeResp({"access_token": "tok"}),
        _FakeResp(
            {"data": {"podcasts": {"data": [{"title": "Found", "rssUrl": "https://feeds/found"}]}}}
        ),
    ]

    async def _fake(client, method, url, **kwargs):  # noqa: ANN001
        seen.append(kwargs.get("json", {}).get("query", ""))
        return responses.pop(0)

    monkeypatch.setattr("app.services.podchaser_api.request_with_retry", _fake)
    monkeypatch.setattr(pc_enrich_mod, "request_with_retry", _fake)

    meta = await PodchaserEnrichmentClient().enrich(
        title="Found", rss_feed_url=None, external_ids={}
    )
    assert meta is not None and meta.title == "Found"
    assert any("podcasts(" in q for q in seen)


async def test_podchaser_access_token_is_cached_across_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pc_creds(monkeypatch)
    from app.services import podchaser_api

    calls = 0

    async def _fake_token_request(*a: object, **k: object) -> _FakeResp:
        nonlocal calls
        calls += 1
        return _FakeResp({"access_token": "tok", "expires_in": 3600})

    monkeypatch.setattr(podchaser_api, "request_with_retry", _fake_token_request)

    assert await podchaser_api.fetch_access_token() == "tok"
    assert await podchaser_api.fetch_access_token() == "tok"
    assert calls == 1  # second call served from the in-process cache


async def test_podchaser_enrichment_clears_token_cache_on_graphql_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 401/403 on the GraphQL call means the cached token is dead. It must be
    dropped so the next run re-exchanges instead of replaying it until TTL."""
    _pc_creds(monkeypatch)
    from app.services import podchaser_api

    responses = [
        _FakeResp({"access_token": "tok", "expires_in": 3600}),
        _FakeResp({"message": "unauthorized"}, status_code=401),
    ]

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr("app.services.podchaser_api.request_with_retry", _fake)
    monkeypatch.setattr(pc_enrich_mod, "request_with_retry", _fake)

    meta = await PodchaserEnrichmentClient().enrich(
        title="x", rss_feed_url="https://feeds.example.com/x", external_ids={}
    )
    assert meta is None
    assert podchaser_api._token_cache["value"] is None  # cache was cleared


async def test_fetch_access_token_raises_configerror_on_rejected_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _pc_creds(monkeypatch)
    from app.services import podchaser_api

    async def _fake(*a: object, **k: object) -> _FakeResp:
        return _FakeResp({"error": "invalid_client"}, status_code=401)

    monkeypatch.setattr(podchaser_api, "request_with_retry", _fake)

    with pytest.raises(ConfigError):
        await podchaser_api.fetch_access_token()
    assert podchaser_api._token_cache["value"] is None


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
