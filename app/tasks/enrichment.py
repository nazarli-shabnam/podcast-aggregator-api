"""Podcast metadata enrichment tasks."""

from __future__ import annotations

import uuid

from app.core.celery_app import celery_app, run_async
from app.core.db import session_scope
from app.services.ingest import enrich_podcast
from app.tasks.base import RETRY_KWARGS


async def _run(podcast_id: uuid.UUID) -> bool:
    async with session_scope() as session:
        return await enrich_podcast(session, podcast_id)


@celery_app.task(
    name="app.tasks.enrichment.enrich_podcast_metadata_task",
    rate_limit="60/m",
    **RETRY_KWARGS,
)
def enrich_podcast_metadata_task(podcast_id: str) -> bool:
    return run_async(_run(uuid.UUID(podcast_id)))
