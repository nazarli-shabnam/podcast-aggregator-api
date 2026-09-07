"""Helpers for managing monthly RANGE partitions of ``chart_snapshots``."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PARENT_TABLE = "chart_snapshots"


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    return start, end


def partition_name(day: date) -> str:
    start, _ = _month_bounds(day)
    return f"{PARENT_TABLE}_{start:%Y_%m}"


def create_monthly_partition_sql(day: date) -> str:
    """Return idempotent DDL creating the partition covering ``day``'s month."""
    start, end = _month_bounds(day)
    name = partition_name(day)
    return (
        f'CREATE TABLE IF NOT EXISTS "{name}" PARTITION OF "{PARENT_TABLE}" '
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}');"
    )


async def create_monthly_partition(conn: AsyncConnection, day: date) -> str:
    name = partition_name(day)
    await conn.execute(text(create_monthly_partition_sql(day)))
    return name


async def ensure_partitions(
    conn: AsyncConnection, around: date, months_ahead: int = 2
) -> list[str]:
    """Ensure partitions exist for ``around``'s month plus ``months_ahead`` months."""
    created: list[str] = []
    cursor = around.replace(day=1)
    for _ in range(months_ahead + 1):
        created.append(await create_monthly_partition(conn, cursor))
        _, cursor = _month_bounds(cursor)
    return created
