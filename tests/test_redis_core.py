"""Direct test for app/core/redis.py's close_redis().

Monkeypatches the shared module-level client's aclose() rather than
calling the real one - redis_client is a singleton reused by every other
test in the session (rate limiting, auth), so actually closing it here
would break test isolation for whatever runs afterward.
"""

from __future__ import annotations

import pytest

from app.core import redis as redis_mod

pytestmark = pytest.mark.asyncio


async def test_close_redis_calls_aclose_on_the_shared_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _fake_aclose() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(redis_mod.redis_client, "aclose", _fake_aclose)
    await redis_mod.close_redis()
    assert called is True
