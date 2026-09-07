"""Async Redis client for the API process (rate limiting).

Celery manages its own Redis connections internally via ``celery_app.py``
(broker/result backend); this module is a separate, small async client for
use directly from FastAPI request handling - currently just rate limiting.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis = Redis.from_url(  # type: ignore[type-arg]
    settings.redis_url, decode_responses=True
)


async def get_redis() -> AsyncIterator[Redis]:  # type: ignore[type-arg]
    """FastAPI dependency yielding the shared async Redis client."""
    yield redis_client


async def close_redis() -> None:
    await redis_client.aclose()  # type: ignore[attr-defined]
