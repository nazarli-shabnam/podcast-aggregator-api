from __future__ import annotations

from datetime import date

from app.schemas.common import ChartSource
from app.services.ingest import ingest_chart


async def test_charts_endpoint_returns_ranked_entries(
    client, db_session, stub_spotify_scraper
) -> None:
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


async def test_charts_endpoint_defaults_to_latest_snapshot(
    client, db_session, stub_spotify_scraper
) -> None:
    from datetime import timedelta

    old_day = date.today() - timedelta(days=5)
    src = ChartSource.SPOTIFY
    await ingest_chart(db_session, src, "us", "technology", snapshot_date=old_day)
    await ingest_chart(db_session, src, "us", "technology", snapshot_date=date.today())
    await db_session.commit()

    # no `date` param -> newest scraped day, not literally today's calendar date
    resp = await client.get(
        "/api/v1/charts",
        params={"country": "us", "category": "technology", "source": "spotify"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body and {e["snapshot_date"] for e in body} == {date.today().isoformat()}


async def test_charts_endpoint_no_date_and_no_data_is_empty(client) -> None:
    resp = await client.get(
        "/api/v1/charts",
        params={"country": "us", "category": "technology", "source": "podchaser"},
    )
    assert resp.status_code == 200
    assert resp.json() == []
