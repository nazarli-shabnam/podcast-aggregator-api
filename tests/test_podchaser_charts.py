from __future__ import annotations

import pytest

from app.schemas.common import ChartSource
from app.services.charts import podchaser as podchaser_mod
from app.services.charts.podchaser import PodchaserChartScraper, _map_entry
from app.services.exceptions import ConfigError


class _FakeResp:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.podchaser_client_id", "cid", raising=False)
    monkeypatch.setattr(
        "app.core.config.settings.podchaser_client_secret", "csecret", raising=False
    )


async def test_fetch_maps_graphql_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_credentials(monkeypatch)

    responses = [
        _FakeResp({"access_token": "tok123"}),
        _FakeResp(
            {
                "data": {
                    "topCharts": {
                        "data": [
                            {
                                "rank": 1,
                                "podcast": {
                                    "id": "77",
                                    "title": "Founders & Funders",
                                    "author": "Startup Studio",
                                    "imageUrl": "https://img/f.jpg",
                                    "rssUrl": "https://feeds.example.com/founders-and-funders",
                                    "webUrl": "https://podchaser.com/x",
                                    "ratingAverage": 4.6,
                                    "ratingCount": 812,
                                },
                            }
                        ]
                    }
                }
            }
        ),
    ]

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr(podchaser_mod, "request_with_retry", _fake_request)

    entries = await PodchaserChartScraper().fetch("us", "technology")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.rank == 1
    assert entry.source is ChartSource.PODCHASER
    assert entry.title == "Founders & Funders"
    assert entry.rss_feed_url == "https://feeds.example.com/founders-and-funders"
    assert entry.external_ids == {"podchaser": "77"}
    assert entry.rating_average == 4.6
    assert entry.rating_count == 812


async def test_fetch_returns_empty_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.config.settings.podchaser_client_id", None, raising=False)
    monkeypatch.setattr("app.core.config.settings.podchaser_client_secret", None, raising=False)
    assert await PodchaserChartScraper().fetch("us", "technology") == []


async def test_token_endpoint_missing_access_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_credentials(monkeypatch)

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return _FakeResp({})

    monkeypatch.setattr(podchaser_mod, "request_with_retry", _fake_request)
    with pytest.raises(ConfigError):
        await podchaser_mod._fetch_access_token()


async def test_fetch_handles_graphql_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_credentials(monkeypatch)

    responses = [
        _FakeResp({"access_token": "tok123"}),
        _FakeResp({"errors": [{"message": "boom"}]}),
    ]

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr(podchaser_mod, "request_with_retry", _fake_request)
    assert await PodchaserChartScraper().fetch("us", "technology") == []


async def test_fetch_skips_entry_missing_rank_without_crashing_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: one malformed entry (no "rank") must not raise and
    take down the whole scrape - it should be skipped, and other, valid
    entries in the same response still come back."""
    _set_credentials(monkeypatch)

    responses = [
        _FakeResp({"access_token": "tok123"}),
        _FakeResp(
            {
                "data": {
                    "topCharts": {
                        "data": [
                            {
                                # missing "rank" entirely
                                "podcast": {
                                    "title": "No Rank Show",
                                    "rssUrl": "https://feeds.example.com/no-rank",
                                }
                            },
                            {
                                "rank": 2,
                                "podcast": {
                                    "id": "88",
                                    "title": "Valid Show",
                                    "rssUrl": "https://feeds.example.com/valid",
                                },
                            },
                        ]
                    }
                }
            }
        ),
    ]

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr(podchaser_mod, "request_with_retry", _fake_request)

    entries = await PodchaserChartScraper().fetch("us", "technology")
    assert len(entries) == 1
    assert entries[0].title == "Valid Show"
    assert entries[0].rank == 2


async def test_fetch_skips_entries_missing_rss_or_title(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_credentials(monkeypatch)

    responses = [
        _FakeResp({"access_token": "tok123"}),
        _FakeResp(
            {
                "data": {
                    "topCharts": {
                        "data": [
                            {"rank": 1, "podcast": {"title": "No RSS"}},
                            {"rank": 2, "podcast": {"rssUrl": "https://x/y"}},
                        ]
                    }
                }
            }
        ),
    ]

    async def _fake_request(*args: object, **kwargs: object) -> _FakeResp:
        return responses.pop(0)

    monkeypatch.setattr(podchaser_mod, "request_with_retry", _fake_request)
    assert await PodchaserChartScraper().fetch("us", "technology") == []


def test_map_entry_tolerates_missing_or_bad_rating() -> None:
    no_rating = _map_entry(
        {"rank": 1, "podcast": {"title": "No Rating", "rssUrl": "https://x/y"}},
        "us",
        "technology",
    )
    assert no_rating is not None
    assert no_rating.rating_average is None
    assert no_rating.rating_count is None

    bad_rating = _map_entry(
        {
            "rank": 2,
            "podcast": {
                "title": "Bad Rating",
                "rssUrl": "https://x/z",
                "ratingAverage": "n/a",
                "ratingCount": "n/a",
            },
        },
        "us",
        "technology",
    )
    assert bad_rating is not None
    assert bad_rating.rating_average is None
    assert bad_rating.rating_count is None


def test_map_entry_rejects_non_dict_entry() -> None:
    assert _map_entry("not a dict", "us", "technology") is None  # type: ignore[arg-type]


def test_map_entry_rejects_non_dict_podcast() -> None:
    assert _map_entry({"rank": 1, "podcast": "not a dict"}, "us", "technology") is None
