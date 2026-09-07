from __future__ import annotations

import pytest


async def test_missing_api_key_is_rejected(client) -> None:
    resp = await client.get("/api/v1/podcasts", headers={"X-API-Key": ""})
    assert resp.status_code == 401


async def test_wrong_api_key_is_rejected(client) -> None:
    resp = await client.get("/api/v1/podcasts", headers={"X-API-Key": "not-a-real-key"})
    assert resp.status_code == 401


async def test_valid_api_key_passes_through(client) -> None:
    # client fixture already sends a valid default X-API-Key header.
    resp = await client.get("/api/v1/podcasts")
    assert resp.status_code == 200


async def test_health_stays_open_without_api_key(client) -> None:
    resp = await client.get("/health", headers={"X-API-Key": ""})
    assert resp.status_code == 200


async def test_empty_configured_keys_rejects_everything(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.config.settings.api_keys", [], raising=False)
    resp = await client.get("/api/v1/charts?country=us&category=technology&source=spotify")
    assert resp.status_code == 401
