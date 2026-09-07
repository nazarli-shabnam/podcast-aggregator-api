"""SSRF guard for outbound requests to user/ingestion-supplied URLs.

``rss_feed_url`` values originate from chart scrapers and enrichment
responses - external, only loosely trusted data. Without validation a
malicious or misconfigured feed URL could point at the metadata service,
an internal admin endpoint, or another host on the private network.
This module enforces an http(s)-only, public-address-only policy.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from app.services.exceptions import ConfigError

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def ensure_safe_url(url: str) -> str:
    """Validate ``url`` is http(s) and resolves only to public addresses.

    Returns the url unchanged on success; raises :class:`ConfigError`
    (treated as a non-retryable, skip-and-log condition by callers) when
    the URL is malformed, uses a disallowed scheme, or resolves to a
    private/loopback/link-local/reserved address.
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise ConfigError(f"unsafe feed url (scheme/host): {url!r}")

    hostname = parts.hostname
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError as exc:
        raise ConfigError(f"could not resolve feed host {hostname!r}: {exc}") from exc

    resolved_ips = {str(info[4][0]) for info in infos}
    if not resolved_ips or any(not _is_public_ip(ip) for ip in resolved_ips):
        raise ConfigError(f"feed url resolves to a non-public address: {url!r}")

    return url
