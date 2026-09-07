"""Shared API dependencies."""

from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from redis.asyncio import Redis

from app.core.config import settings
from app.core.redis import get_redis


@dataclass(slots=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Depends(_api_key_header),
    redis: Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> str:
    """Validate ``X-API-Key`` and apply a per-key fixed-window rate limit.

    401 when the key is missing or not one of ``settings.api_keys`` (an
    empty configured list means no key satisfies auth). Otherwise 429
    with a ``Retry-After`` header once the key exceeds
    ``settings.rate_limit_requests`` within the current window.
    """
    if not api_key or api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="missing or invalid API key")

    window = settings.rate_limit_window_seconds
    bucket = int(time.time()) // window
    redis_key = f"ratelimit:{api_key}:{bucket}"

    count = await redis.incr(redis_key)
    if count == 1:
        await redis.expire(redis_key, window)

    if count > settings.rate_limit_requests:
        ttl = await redis.ttl(redis_key)
        retry_after = ttl if ttl > 0 else window
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    return api_key
