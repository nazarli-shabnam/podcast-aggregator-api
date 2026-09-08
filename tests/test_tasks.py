from __future__ import annotations

import pytest

from app.core.celery_app import run_async
from app.tasks import scraping


def test_run_async_executes_coroutine() -> None:
    async def _double(x: int) -> int:
        return x * 2

    assert run_async(_double(21)) == 42


def test_scrape_all_charts_task_fans_out(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class _Stub:
        @staticmethod
        def delay(country: str, category: str) -> None:
            calls.append((country, category))

    monkeypatch.setattr(scraping, "scrape_spotify_charts_task", _Stub)
    monkeypatch.setattr(scraping, "scrape_podchaser_charts_task", _Stub)
    monkeypatch.setattr(scraping.settings, "chart_countries", ["us", "gb"])
    monkeypatch.setattr(scraping.settings, "chart_categories", ["technology"])

    dispatched = scraping.scrape_all_charts_task()
    assert dispatched == 4
    assert ("us", "technology") in calls and ("gb", "technology") in calls


def test_scrape_task_ingests_and_enqueues_enrichment(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.tasks.enrichment as enrichment_mod

    enqueued: list[str] = []
    monkeypatch.setattr(
        enrichment_mod.enrich_podcast_metadata_task,
        "delay",
        lambda pid: enqueued.append(pid),
    )

    async def _fake_ingest(session, source, country, category):  # noqa: ANN001
        import uuid

        return [uuid.uuid4(), uuid.uuid4()]

    monkeypatch.setattr(scraping, "ingest_chart", _fake_ingest)

    count = scraping.scrape_spotify_charts_task("us", "technology")
    assert count == 2
    assert len(enqueued) == 2


def test_scrape_podchaser_charts_task_ingests(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.tasks.enrichment as enrichment_mod

    monkeypatch.setattr(enrichment_mod.enrich_podcast_metadata_task, "delay", lambda pid: None)

    async def _fake_ingest(session, source, country, category):  # noqa: ANN001
        import uuid

        return [uuid.uuid4()]

    monkeypatch.setattr(scraping, "ingest_chart", _fake_ingest)

    assert scraping.scrape_podchaser_charts_task("us", "technology") == 1
