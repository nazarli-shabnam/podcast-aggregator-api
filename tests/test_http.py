from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from app.services.exceptions import TransientError
from app.services.http import RateLimiter, request_with_retry


async def test_rate_limiter_throttles() -> None:
    limiter = RateLimiter(rate_per_second=20, capacity=1)
    start = time.monotonic()
    await limiter.acquire()
    await limiter.acquire()
    assert time.monotonic() - start >= 0.03


async def test_request_with_retry_succeeds_first_try() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await request_with_retry(client, "GET", "http://x/api")
    assert resp.status_code == 200
    assert calls == 1


async def test_request_with_retry_retries_then_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _d: _real_sleep(0))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TransientError):
            await request_with_retry(client, "GET", "http://x/api", max_retries=2)
    assert calls == 3


async def test_request_with_retry_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda _d: _real_sleep(0))
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500) if calls == 1 else httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        resp = await request_with_retry(client, "GET", "http://x/api", max_retries=3)
    assert resp.status_code == 200
    assert calls == 2
