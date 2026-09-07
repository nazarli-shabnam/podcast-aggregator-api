"""SSRF guard for outbound requests to user/ingestion-supplied URLs.

``rss_feed_url`` values originate from chart scrapers and enrichment
responses - external, only loosely trusted data. Validating the hostname
once and then letting the HTTP client re-resolve it at connect time is
not enough: a domain with a short DNS TTL can resolve to a public address
during validation and to a private/loopback/metadata address moments
later when the connection actually opens (DNS rebinding). To close that
gap, :func:`resolve_safe_url` resolves the host exactly once, validates
that address, and returns it as a *pinned* connection target - callers
must connect to that pinned IP (not re-resolve the hostname) while still
using the original hostname for the `Host` header and TLS SNI/certificate
validation (via httpcore's ``sni_hostname`` request extension), so
certificate checking stays correct even though the socket doesn't dial
the hostname directly.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.services.exceptions import ConfigError

_ALLOWED_SCHEMES = frozenset({"http", "https"})


@dataclass(slots=True, frozen=True)
class PinnedUrl:
    """A URL whose host has been resolved once and validated as public.

    ``request_url`` has its hostname replaced by ``pinned_ip`` (IPv6
    addresses bracketed) so an HTTP client connects to exactly the
    address that was validated - not a fresh, independently-resolved one.
    ``hostname`` is preserved for the ``Host`` header and TLS SNI.
    """

    request_url: str
    hostname: str
    pinned_ip: str
    port: int | None
    scheme: str


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


def resolve_safe_url(url: str) -> PinnedUrl:
    """Resolve ``url``'s host once and pin it to a validated public IP.

    Raises :class:`ConfigError` (non-retryable, skip-and-log) when the URL
    is malformed, uses a disallowed scheme, fails to resolve, or resolves
    to a private/loopback/link-local/reserved/multicast address.
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise ConfigError(f"unsafe feed url (scheme/host): {url!r}")

    hostname = parts.hostname
    try:
        infos = socket.getaddrinfo(hostname, parts.port)
    except OSError as exc:
        raise ConfigError(f"could not resolve feed host {hostname!r}: {exc}") from exc

    resolved_ips = [str(info[4][0]) for info in infos]
    if not resolved_ips or any(not _is_public_ip(ip) for ip in resolved_ips):
        raise ConfigError(f"feed url resolves to a non-public address: {url!r}")

    pinned_ip = resolved_ips[0]
    netloc = f"[{pinned_ip}]" if ":" in pinned_ip else pinned_ip
    if parts.port:
        netloc += f":{parts.port}"
    request_url = parts._replace(netloc=netloc).geturl()

    return PinnedUrl(
        request_url=request_url,
        hostname=hostname,
        pinned_ip=pinned_ip,
        port=parts.port,
        scheme=parts.scheme,
    )
