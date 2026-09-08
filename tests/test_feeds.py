from __future__ import annotations

import socket
from urllib.parse import urlsplit

import httpx
import pytest

from app.services import feeds as feeds_mod
from app.services.exceptions import ConfigError
from app.services.feeds import _parse_datetime, _parse_duration, fetch_feed_episodes, parse_feed
from app.services.url_safety import PinnedUrl


def _fake_pin(url: str) -> PinnedUrl:
    """Bypass real DNS resolution in tests: pin to a fake-but-plausible IP
    while keeping the request URL identical to what MockTransport expects.
    """
    parts = urlsplit(url)
    return PinnedUrl(
        request_url=url,
        hostname=parts.hostname or "",
        pinned_ip="203.0.113.1",
        port=parts.port,
        scheme=parts.scheme,
    )


def test_parse_duration_variants() -> None:
    assert _parse_duration("3600") == 3600
    assert _parse_duration("45:30") == 2730
    assert _parse_duration("1:02:03") == 3723
    assert _parse_duration(None) is None
    assert _parse_duration("garbage") is None


def test_parse_datetime_invalid() -> None:
    assert _parse_datetime(None) is None
    assert _parse_datetime("not a date") is None
    assert _parse_datetime("Mon, 01 Sep 2025 10:00:00 +0000") is not None


def test_parse_feed_skips_items_without_guid() -> None:
    xml = "<rss><channel><item><title>No guid</title></item></channel></rss>"
    assert parse_feed(xml) == []


async def test_fetch_feed_episodes(monkeypatch: pytest.MonkeyPatch) -> None:
    feed = """<rss><channel>
      <item><title>A</title><guid>g1</guid></item>
    </channel></rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "feed.test"
        return httpx.Response(200, text=feed)

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(feeds_mod, "resolve_safe_url", _fake_pin)
    episodes = await fetch_feed_episodes("http://feed.test/rss")
    assert [e.guid for e in episodes] == ["g1"]


async def test_fetch_feed_episodes_follows_safe_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    feed = "<rss><channel><item><title>A</title><guid>g1</guid></item></channel></rss>"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "http://feed.test/old":
            return httpx.Response(301, headers={"location": "http://feed.test/new"})
        return httpx.Response(200, text=feed)

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(feeds_mod, "resolve_safe_url", _fake_pin)
    episodes = await fetch_feed_episodes("http://feed.test/old")
    assert [e.guid for e in episodes] == ["g1"]


async def test_fetch_feed_episodes_rejects_unsafe_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301, headers={"location": "http://169.254.169.254/latest"})

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    def _fake_resolve(url: str) -> PinnedUrl:
        if "169.254" in url:
            raise ConfigError("blocked")
        return _fake_pin(url)

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(feeds_mod, "resolve_safe_url", _fake_resolve)
    with pytest.raises(ConfigError):
        await fetch_feed_episodes("http://feed.test/old")


async def test_fetch_feed_episodes_pins_to_resolved_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """The actual outbound request must target the pinned IP, not the
    hostname - this is what closes the DNS-rebinding gap."""
    feed = "<rss><channel><item><title>A</title><guid>g1</guid></item></channel></rss>"
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, text=feed)

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))]
    )
    await fetch_feed_episodes("https://feed.test/rss")
    assert seen_urls == ["https://93.184.216.34/rss"]


async def test_fetch_feed_episodes_raises_on_redirect_missing_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(301)  # redirect status, no Location header

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(feeds_mod, "resolve_safe_url", _fake_pin)
    with pytest.raises(ConfigError, match="missing Location header"):
        await fetch_feed_episodes("http://feed.test/old")


async def test_fetch_feed_episodes_raises_after_too_many_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Always redirect to itself - never terminates on its own.
        return httpx.Response(301, headers={"location": "http://feed.test/old"})

    class _CM:
        async def __aenter__(self):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler))

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(feeds_mod, "build_client", lambda **kw: _CM())
    monkeypatch.setattr(feeds_mod, "resolve_safe_url", _fake_pin)
    with pytest.raises(ConfigError, match="too many redirects"):
        await fetch_feed_episodes("http://feed.test/old")
