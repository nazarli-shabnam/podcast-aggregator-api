from __future__ import annotations

import socket

import pytest

from app.services.exceptions import ConfigError
from app.services.url_safety import resolve_safe_url


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ConfigError):
        resolve_safe_url("file:///etc/passwd")


def test_rejects_missing_host() -> None:
    with pytest.raises(ConfigError):
        resolve_safe_url("http://")


def test_rejects_loopback_literal() -> None:
    with pytest.raises(ConfigError):
        resolve_safe_url("http://127.0.0.1/feed")


def test_rejects_link_local_metadata_address() -> None:
    with pytest.raises(ConfigError):
        resolve_safe_url("http://169.254.169.254/latest/meta-data")


def test_rejects_private_network_literal() -> None:
    with pytest.raises(ConfigError):
        resolve_safe_url("http://10.0.0.5/feed")


def test_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*a: object, **k: object) -> None:
        raise OSError("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(ConfigError):
        resolve_safe_url("http://does-not-exist.invalid/feed")


def test_accepts_public_host_and_pins_resolved_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))]
    )
    pinned = resolve_safe_url("https://example.com/feed.xml")
    assert pinned.hostname == "example.com"
    assert pinned.pinned_ip == "93.184.216.34"
    assert pinned.scheme == "https"
    # The request target uses the pinned IP, not the hostname - this is
    # what prevents a second, independent (and attacker-controllable)
    # DNS resolution at connect time.
    assert pinned.request_url == "https://93.184.216.34/feed.xml"


def test_pins_ipv6_address_with_brackets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("2606:2800:220:1:248:1893:25c8:1946", 0))],
    )
    pinned = resolve_safe_url("https://example.com/feed.xml")
    assert pinned.request_url == "https://[2606:2800:220:1:248:1893:25c8:1946]/feed.xml"


def test_rejects_ipv6_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("::1", 0))]
    )
    with pytest.raises(ConfigError):
        resolve_safe_url("http://example.com/feed")


def test_rejects_when_any_resolved_address_is_private(monkeypatch: pytest.MonkeyPatch) -> None:
    # A host resolving to multiple addresses, one of which is private,
    # is rejected outright rather than picking only the public one.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (None, None, None, None, ("93.184.216.34", 0)),
            (None, None, None, None, ("127.0.0.1", 0)),
        ],
    )
    with pytest.raises(ConfigError):
        resolve_safe_url("http://example.com/feed")
