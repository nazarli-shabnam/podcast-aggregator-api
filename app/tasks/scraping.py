"""Chart scraping tasks."""

from __future__ import annotations

from app.core.celery_app import celery_app, run_async
from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.schemas.common import ChartSource
from app.services.ingest import ingest_chart
from app.tasks.base import RETRY_KWARGS

logger = get_logger(__name__)


async def _run(source: ChartSource, country: str, category: str) -> int:
    async with session_scope() as session:
        podcast_ids = await ingest_chart(session, source, country, category)
    # Enqueue enrichment for each charted podcast.
    from app.tasks.enrichment import enrich_podcast_metadata_task

    for podcast_id in podcast_ids:
        enrich_podcast_metadata_task.delay(str(podcast_id))
    return len(podcast_ids)


@celery_app.task(
    name="app.tasks.scraping.scrape_spotify_charts_task", rate_limit="30/m", **RETRY_KWARGS
)
def scrape_spotify_charts_task(country: str, category: str) -> int:
    return run_async(_run(ChartSource.SPOTIFY, country, category))


@celery_app.task(
    name="app.tasks.scraping.scrape_podchaser_charts_task", rate_limit="30/m", **RETRY_KWARGS
)
def scrape_podchaser_charts_task(country: str, category: str) -> int:
    return run_async(_run(ChartSource.PODCHASER, country, category))


@celery_app.task(name="app.tasks.scraping.scrape_all_charts_task")
def scrape_all_charts_task() -> int:
    """Fan out per configured country/category across both sources."""
    dispatched = 0
    for country in settings.chart_countries:
        for category in settings.chart_categories:
            scrape_spotify_charts_task.delay(country, category)
            scrape_podchaser_charts_task.delay(country, category)
            dispatched += 2
    logger.info("dispatched %d chart scrape tasks", dispatched)
    return dispatched
