from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from app.db.partitions import (
    create_monthly_partition_sql,
    ensure_partitions,
    partition_name,
)


def test_partition_name_and_sql() -> None:
    day = date(2026, 3, 15)
    assert partition_name(day) == "chart_snapshots_2026_03"
    sql = create_monthly_partition_sql(day)
    assert "FROM ('2026-03-01') TO ('2026-04-01')" in sql
    assert "IF NOT EXISTS" in sql


def test_partition_name_december_rolls_over() -> None:
    sql = create_monthly_partition_sql(date(2026, 12, 1))
    assert "FROM ('2026-12-01') TO ('2027-01-01')" in sql


@pytest.mark.asyncio
async def test_ensure_partitions_creates_child_tables(db_session) -> None:
    conn = await db_session.connection()
    names = await ensure_partitions(conn, date(2026, 6, 1), months_ahead=1)
    assert names == ["chart_snapshots_2026_06", "chart_snapshots_2026_07"]
    exists = await conn.scalar(
        text("SELECT to_regclass('public.chart_snapshots_2026_07') IS NOT NULL")
    )
    assert exists is True
