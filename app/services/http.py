"""Shared async HTTP client factory with retry/backoff and rate limiting."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.exceptions import TransientError

logger = get_logger(__name__)

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class RateLimiter:
    """Simple async token-bucket limiter."""

    def __init__(self, rate_per_second: float, capacity: float | None = None) -> None:
        self._rate = max(rate_per_second, 0.001)
        self._capacity = capacity if capacity is not None else max(rate_per_second, 1.0)
        self._tokens = self._capacity
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(self._capacity, self._tokens + (now - self._updated) * self._rate)
            self._updated = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._updated = time.monotonic()
            else:
                self._tokens -= 1.0


_default_limiter = RateLimiter(settings.http_rate_limit_per_second)


@asynccontextmanager
async def build_client(
    *, base_url: str = "", headers: dict[str, str] | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    timeout = httpx.Timeout(settings.http_timeout_seconds)
    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers or {},
        timeout=timeout,
        follow_redirects=True,
    ) as client:
        yield client


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    limiter: RateLimiter | None = None,
    max_retries: int | None = None,
    **kwargs: object,
) -> httpx.Response:
    """Perform a rate-limited request, retrying transient failures with backoff."""
    limiter = limiter or _default_limiter
    attempts = max_retries if max_retries is not None else settings.http_max_retries
    last_exc: Exception | None = None

    for attempt in range(attempts + 1):
        await limiter.acquire()
        try:
            response = await client.request(method, url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            last_exc = exc
        else:
            if response.status_code not in _RETRY_STATUS:
                return response
            last_exc = TransientError(f"{response.status_code} from {url}")

        if attempt < attempts:
            backoff = min(2**attempt, 30)
            logger.warning("retrying %s %s (attempt %s): %s", method, url, attempt + 1, last_exc)
            await asyncio.sleep(backoff)

    raise TransientError(f"request failed after {attempts + 1} attempts: {last_exc}")
