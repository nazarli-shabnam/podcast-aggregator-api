"""Shared Podchaser GraphQL API plumbing.

Podchaser publishes a public GraphQL API (https://api-docs.podchaser.com)
authenticated via OAuth2 client-credentials: exchange ``PODCHASER_CLIENT_ID`` /
``PODCHASER_CLIENT_SECRET`` for a bearer token at ``/token``, then query
``/graphql``. Both the charts scraper (:mod:`app.services.charts.podchaser`) and
the enrichment client (:mod:`app.services.enrichment.podchaser`) build on this.

Field names in the callers' queries match Podchaser's public schema at the time
of writing; if their schema changes, adjust the queries and mappers accordingly.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import settings
from app.services.exceptions import ConfigError
from app.services.http import build_client, request_with_retry

TOKEN_URL = "https://api.podchaser.com/token"  # noqa: S105 - OAuth endpoint URL, not a secret
GRAPHQL_URL = "https://api.podchaser.com/graphql"

# Podchaser access tokens are long-lived (weeks). Caching the token in-process
# avoids a full client-credentials exchange on every chart scrape and every
# enrichment call. Refreshed once it is within _TOKEN_SKEW_SECONDS of expiry.
_TOKEN_SKEW_SECONDS = 300
_DEFAULT_TOKEN_TTL_SECONDS = 3600
_token_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}


def reset_token_cache() -> None:
    """Drop the cached access token (tests, or after a credential change)."""
    _token_cache["value"] = None
    _token_cache["expires_at"] = 0.0


def coerce_number[T: (int, float)](value: Any, cast: type[T]) -> T | None:
    """Best-effort numeric coercion; ``None`` for missing or unparseable upstream
    values so one bad field never aborts a scrape or enrichment call."""
    if value is None:
        return None
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


async def fetch_access_token() -> str:
    """OAuth2 client-credentials token, cached in-process until near expiry.

    Raises :class:`ConfigError` when the ``PODCHASER_CLIENT_*`` settings are
    unset so callers can skip gracefully.
    """
    client_id = settings.podchaser_client_id
    client_secret = settings.podchaser_client_secret
    if not client_id or not client_secret:
        raise ConfigError("PODCHASER_CLIENT_ID / PODCHASER_CLIENT_SECRET not configured")

    cached = _token_cache["value"]
    if cached is not None and time.monotonic() < _token_cache["expires_at"]:
        return str(cached)

    async with build_client() as client:
        resp = await request_with_retry(
            client,
            "POST",
            TOKEN_URL,
            json={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        resp.raise_for_status()
        body = resp.json()
    token = body.get("access_token")
    if not token:
        raise ConfigError("Podchaser token endpoint returned no access_token")

    ttl = coerce_number(body.get("expires_in"), int) or _DEFAULT_TOKEN_TTL_SECONDS
    _token_cache["value"] = str(token)
    _token_cache["expires_at"] = time.monotonic() + max(ttl - _TOKEN_SKEW_SECONDS, 0)
    return str(token)
