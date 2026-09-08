"""Charts endpoint."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.db import get_session
from app.db.models import ChartSnapshot
from app.schemas.chart import ChartEntryRead
from app.schemas.common import ChartSource

router = APIRouter(tags=["charts"])


@router.get("/charts", response_model=list[ChartEntryRead])
async def get_charts(
    country: str = Query(..., min_length=2, max_length=2),
    category: str = Query(..., min_length=1),
    source: ChartSource = Query(...),
    date_: date | None = Query(
        None, alias="date", description="Defaults to the most recent scraped day"
    ),
    session: AsyncSession = Depends(get_session),
) -> list[ChartSnapshot]:
    slot = (
        ChartSnapshot.country == country.lower(),
        ChartSnapshot.category == category.lower(),
        ChartSnapshot.source == source.value,
    )

    if date_ is None:
        # "latest" = the newest snapshot_date actually scraped for this slot,
        # not literally today (which is empty until the day's scrape runs).
        date_ = await session.scalar(select(func.max(ChartSnapshot.snapshot_date)).where(*slot))
        if date_ is None:
            return []

    stmt = (
        select(ChartSnapshot)
        .options(joinedload(ChartSnapshot.podcast))
        .where(*slot, ChartSnapshot.snapshot_date == date_)
        .order_by(ChartSnapshot.rank)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
