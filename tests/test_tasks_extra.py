from __future__ import annotations

import uuid

import pytest

from app.tasks import enrichment as enrichment_mod
from app.tasks import episodes as episodes_mod
from app.tasks import maintenance as maintenance_mod


def test_ensure_partitions_task_creates_tables() -> None:
    created = maintenance_mod.ensure_partitions_task()
    assert created
    assert all(name.startswith("chart_snapshots_") for name in created)


def test_sync_podcast_episodes_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_sync(session, podcast_id):  # noqa: ANN001
        return 7

    monkeypatch.setattr(episodes_mod, "sync_episodes", _fake_sync)
    assert episodes_mod.sync_podcast_episodes_task(str(uuid.uuid4())) == 7


def test_sync_all_tracked_episodes_task(monkeypatch: pytest.MonkeyPatch) -> None:
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    dispatched: list[str] = []

    async def _fake_list(session, limit=500):  # noqa: ANN001
        return ids

    monkeypatch.setattr(episodes_mod, "list_tracked_podcast_ids", _fake_list)
    monkeypatch.setattr(
        episodes_mod.sync_podcast_episodes_task, "delay", lambda pid: dispatched.append(pid)
    )
    assert episodes_mod.sync_all_tracked_episodes_task() == 3
    assert len(dispatched) == 3


def test_enrich_podcast_metadata_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_enrich(session, podcast_id):  # noqa: ANN001
        return True

    monkeypatch.setattr(enrichment_mod, "enrich_podcast", _fake_enrich)
    assert enrichment_mod.enrich_podcast_metadata_task(str(uuid.uuid4())) is True
