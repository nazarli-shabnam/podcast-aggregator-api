"""Celery application, Beat schedule, and shared task utilities."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "podcast_aggregator",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.scraping",
        "app.tasks.enrichment",
        "app.tasks.episodes",
        "app.tasks.maintenance",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    result_expires=3600,
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.task_routes = {
    "app.tasks.scraping.*": {"queue": "scraping"},
    "app.tasks.enrichment.*": {"queue": "enrichment"},
    "app.tasks.episodes.*": {"queue": "episodes"},
    "app.tasks.maintenance.*": {"queue": "maintenance"},
}

celery_app.conf.beat_schedule = {
    "scrape-charts-daily": {
        "task": "app.tasks.scraping.scrape_all_charts_task",
        "schedule": crontab(hour="6", minute="0"),
    },
    "sync-episodes-every-6h": {
        "task": "app.tasks.episodes.sync_all_tracked_episodes_task",
        "schedule": crontab(hour="*/6", minute="30"),
    },
    "ensure-partitions-monthly": {
        "task": "app.tasks.maintenance.ensure_partitions_task",
        "schedule": crontab(day_of_month="25", hour="0", minute="0"),
    },
}


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine to completion from a synchronous Celery task.

    Each call gets a fresh event loop that is closed afterwards, so
    successive tasks in a worker never share a stale loop (which would
    corrupt asyncpg connection state).
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:  # pragma: no cover - defensive
        raise RuntimeError("run_async called from within a running event loop")

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        asyncio.set_event_loop(None)
        loop.close()
