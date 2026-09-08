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
    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "database": "error"}


async def test_openapi_schema_lists_routes(client) -> None:
    resp = await client.get("/openapi.json")
    paths = resp.json()["paths"]
    assert "/api/v1/charts" in paths
    assert "/api/v1/podcasts/{podcast_id}" in paths


async def test_lifespan_disposes_engine_and_closes_redis_on_shutdown(monkeypatch) -> None:
    """ASGITransport-based tests never run lifespan events, so exercise
    the context manager directly - mocking the two resources it tears
    down (real ones are shared singletons other tests still need)."""
    import app.main as main_mod

    disposed = False
    closed = False

    class _FakeEngine:
        async def dispose(self) -> None:
            nonlocal disposed
            disposed = True

    async def _fake_close_redis() -> None:
        nonlocal closed
        closed = True

    monkeypatch.setattr(main_mod, "engine", _FakeEngine())
    monkeypatch.setattr(main_mod, "close_redis", _fake_close_redis)

    async with main_mod.lifespan(main_mod.app):
        pass

    assert disposed is True
    assert closed is True
