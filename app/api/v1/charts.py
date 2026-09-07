"""Charts endpoint."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
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
    date_: date = Query(default_factory=date.today, alias="date"),
    session: AsyncSession = Depends(get_session),
) -> list[ChartSnapshot]:
    stmt = (
        select(ChartSnapshot)
        .options(joinedload(ChartSnapshot.podcast))
        .where(
            ChartSnapshot.country == country.lower(),
            ChartSnapshot.category == category.lower(),
            ChartSnapshot.source == source.value,
            ChartSnapshot.snapshot_date == date_,
        )
        .order_by(ChartSnapshot.rank)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
