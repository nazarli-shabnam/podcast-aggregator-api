from __future__ import annotations


async def test_health_ok(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_health_degraded_when_db_down(client, monkeypatch) -> None:
    import app.main as main_mod

    class _BrokenEngine:
        def connect(self):  # noqa: ANN201
            raise RuntimeError("db gone")

    monkeypatch.setattr(main_mod, "engine", _BrokenEngine())
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "degraded"


async def test_openapi_schema_lists_routes(client) -> None:
    resp = await client.get("/openapi.json")
    paths = resp.json()["paths"]
    assert "/api/v1/charts" in paths
    assert "/api/v1/podcasts/{podcast_id}" in paths
