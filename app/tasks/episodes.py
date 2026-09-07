"""Episode synchronisation tasks."""

from __future__ import annotations

import uuid

from app.core.celery_app import celery_app, run_async
from app.core.db import session_scope
from app.core.logging import get_logger
from app.services.ingest import list_tracked_podcast_ids, sync_episodes
from app.tasks.base import RETRY_KWARGS

logger = get_logger(__name__)


async def _run(podcast_id: uuid.UUID) -> int:
    async with session_scope() as session:
        return await sync_episodes(session, podcast_id)


@celery_app.task(
    name="app.tasks.episodes.sync_podcast_episodes_task",
    rate_limit="120/m",
    **RETRY_KWARGS,
)
def sync_podcast_episodes_task(podcast_id: str) -> int:
    return run_async(_run(uuid.UUID(podcast_id)))


async def _dispatch() -> int:
    async with session_scope() as session:
        ids = await list_tracked_podcast_ids(session)
    for podcast_id in ids:
        sync_podcast_episodes_task.delay(str(podcast_id))
    return len(ids)


@celery_app.task(name="app.tasks.episodes.sync_all_tracked_episodes_task")
def sync_all_tracked_episodes_task() -> int:
    count = run_async(_dispatch())
    logger.info("dispatched %d episode sync tasks", count)
    return count
