from __future__ import annotations

from datetime import date

from app.schemas.common import ChartSource
from app.services.ingest import ingest_chart


async def test_charts_endpoint_returns_ranked_entries(client, db_session) -> None:
    await ingest_chart(db_session, ChartSource.SPOTIFY, "us", "technology")
    await db_session.commit()

    resp = await client.get(
        "/api/v1/charts",
        params={
            "country": "us",
            "category": "technology",
            "source": "spotify",
            "date": date.today().isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body
    assert body[0]["rank"] == 1
    assert body[0]["podcast"]["title"]


async def test_charts_endpoint_empty_for_unknown_day(client) -> None:
    resp = await client.get(
        "/api/v1/charts",
        params={
            "country": "us",
            "category": "technology",
            "source": "podchaser",
            "date": "2000-01-01",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == []
