"""Database maintenance tasks."""

from __future__ import annotations

from datetime import date

from app.core.celery_app import celery_app, run_async
from app.core.db import task_connection
from app.core.logging import get_logger
from app.db.partitions import ensure_partitions

logger = get_logger(__name__)


async def _run() -> list[str]:
    async with task_connection() as conn:
        return await ensure_partitions(conn, date.today(), months_ahead=3)


@celery_app.task(name="app.tasks.maintenance.ensure_partitions_task")
def ensure_partitions_task() -> list[str]:
    created = run_async(_run())
    logger.info("ensured chart_snapshots partitions: %s", created)
    return created
