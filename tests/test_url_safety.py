from __future__ import annotations

import socket

import pytest

from app.services.exceptions import ConfigError
from app.services.url_safety import ensure_safe_url


def test_rejects_non_http_scheme() -> None:
    with pytest.raises(ConfigError):
        ensure_safe_url("file:///etc/passwd")


def test_rejects_missing_host() -> None:
    with pytest.raises(ConfigError):
        ensure_safe_url("http://")


def test_rejects_loopback_literal() -> None:
    with pytest.raises(ConfigError):
        ensure_safe_url("http://127.0.0.1/feed")


def test_rejects_link_local_metadata_address() -> None:
    with pytest.raises(ConfigError):
        ensure_safe_url("http://169.254.169.254/latest/meta-data")


def test_rejects_private_network_literal() -> None:
    with pytest.raises(ConfigError):
        ensure_safe_url("http://10.0.0.5/feed")


def test_rejects_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*a: object, **k: object) -> None:
        raise OSError("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(ConfigError):
        ensure_safe_url("http://does-not-exist.invalid/feed")


def test_accepts_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))]
    )
    assert ensure_safe_url("https://example.com/feed.xml") == "https://example.com/feed.xml"
