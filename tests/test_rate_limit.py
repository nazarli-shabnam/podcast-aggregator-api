from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.redis import redis_client


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_rate_limit_keys():
    yield
    async for key in redis_client.scan_iter(match="ratelimit:test-rl-*"):
        await redis_client.delete(key)


async def test_rate_limit_blocks_after_threshold(client, monkeypatch: pytest.MonkeyPatch) -> None:
    key = f"test-rl-{uuid.uuid4()}"
    monkeypatch.setattr(settings, "api_keys", [key], raising=False)
    monkeypatch.setattr(settings, "rate_limit_requests", 3, raising=False)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60, raising=False)

    headers = {"X-API-Key": key}
    for _ in range(3):
        resp = await client.get("/api/v1/podcasts", headers=headers)
        assert resp.status_code == 200

    blocked = await client.get("/api/v1/podcasts", headers=headers)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


async def test_repeated_bad_keys_get_throttled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "auth_failure_limit", 3, raising=False)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60, raising=False)

    headers = {"X-API-Key": "definitely-not-valid"}
    for _ in range(3):
        assert (await client.get("/api/v1/podcasts", headers=headers)).status_code == 401

    throttled = await client.get("/api/v1/podcasts", headers=headers)
    assert throttled.status_code == 429
    assert "Retry-After" in throttled.headers


async def test_rate_limit_is_per_key(client, monkeypatch: pytest.MonkeyPatch) -> None:
    key_a = f"test-rl-{uuid.uuid4()}"
    key_b = f"test-rl-{uuid.uuid4()}"
    monkeypatch.setattr(settings, "api_keys", [key_a, key_b], raising=False)
    monkeypatch.setattr(settings, "rate_limit_requests", 1, raising=False)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60, raising=False)

    assert (await client.get("/api/v1/podcasts", headers={"X-API-Key": key_a})).status_code == 200
    assert (await client.get("/api/v1/podcasts", headers={"X-API-Key": key_a})).status_code == 429
    # A different key has its own independent counter.
    assert (await client.get("/api/v1/podcasts", headers={"X-API-Key": key_b})).status_code == 200
