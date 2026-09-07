"""Small operational CLI: ``python -m app.cli <command>``."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from app.core.db import session_scope, task_connection
from app.db.partitions import ensure_partitions
from app.schemas.common import ChartSource
from app.services.ingest import ingest_chart


async def _demo() -> None:
    async with task_connection() as conn:
        await ensure_partitions(conn, date.today())
    async with session_scope() as session:
        for source in ChartSource:
            await ingest_chart(session, source, "us", "technology")
    print("seeded demo charts for us/technology")


async def _partitions() -> None:
    async with task_connection() as conn:
        created = await ensure_partitions(conn, date.today(), months_ahead=3)
    print("ensured partitions:", ", ".join(created))


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="seed demo chart data")
    sub.add_parser("partitions", help="ensure chart_snapshots partitions exist")
    args = parser.parse_args()

    if args.command == "demo":
        asyncio.run(_demo())
    elif args.command == "partitions":
        asyncio.run(_partitions())


if __name__ == "__main__":
    main()
