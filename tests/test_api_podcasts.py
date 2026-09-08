from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.upsert import upsert_episodes, upsert_podcast


async def _seed_podcast_with_episodes(db_session, count: int = 5):
    pid = await upsert_podcast(
        db_session,
        {
            "title": "Cursor Test Show",
            "publisher": "QA Labs",
            "rss_feed_url": "https://feeds.test/cursor",
            "categories": ["technology"],
            "rating_count": 10,
        },
    )
    base = datetime(2025, 1, 1, tzinfo=UTC)
    await upsert_episodes(
        db_session,
        pid,
        [
            {
                "guid": f"g{i}",
                "title": f"Episode {i}",
                "published_at": base + timedelta(days=i),
            }
            for i in range(count)
        ],
    )
    await db_session.commit()
    return pid


async def test_list_podcasts_pagination_and_search(client, db_session) -> None:
    await _seed_podcast_with_episodes(db_session)
    resp = await client.get("/api/v1/podcasts", params={"q": "cursor", "page_size": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page_size"] == 1
    assert body["items"][0]["title"] == "Cursor Test Show"


async def test_list_podcasts_category_filter(client, db_session) -> None:
    await upsert_podcast(
        db_session,
        {
            "title": "Tech Weekly",
            "rss_feed_url": "https://feeds.test/tech-weekly",
            "categories": ["Technology", "News"],
        },
    )
    await upsert_podcast(
        db_session,
        {
            "title": "Cooking Hour",
            "rss_feed_url": "https://feeds.test/cooking-hour",
            "categories": ["Food"],
        },
    )
    await db_session.commit()

    resp = await client.get("/api/v1/podcasts", params={"category": "News"})
    assert resp.status_code == 200
    titles = [i["title"] for i in resp.json()["items"]]
    assert titles == ["Tech Weekly"]

    # JSONB containment is case-sensitive
    assert (await client.get("/api/v1/podcasts", params={"category": "news"})).json()["items"] == []


async def test_podcast_detail_cursor_pagination(client, db_session) -> None:
    pid = await _seed_podcast_with_episodes(db_session, count=5)

    first = await client.get(f"/api/v1/podcasts/{pid}", params={"limit": 2})
    assert first.status_code == 200
    page1 = first.json()["episodes"]
    assert len(page1["items"]) == 2
    assert page1["items"][0]["title"] == "Episode 4"  # newest first
    assert page1["next_cursor"]

    second = await client.get(
        f"/api/v1/podcasts/{pid}", params={"limit": 2, "cursor": page1["next_cursor"]}
    )
    page2 = second.json()["episodes"]
    assert [i["title"] for i in page2["items"]] == ["Episode 2", "Episode 1"]


async def test_podcast_detail_cursor_survives_null_published_at_boundary(
    client, db_session
) -> None:
    """Regression test: an episode with published_at=NULL sorts as "now"
    (coalesced), so it lands first/newest. When it's the sole item on a
    page, the encoded cursor must reflect that coalesced value - not a
    NULL-derived epoch sentinel - or the next page comes back empty even
    though older, real episodes still exist.
    """
    pid = await upsert_podcast(
        db_session,
        {
            "title": "Undated Episode Show",
            "rss_feed_url": "https://feeds.test/undated",
        },
    )
    base = datetime(2025, 1, 1, tzinfo=UTC)
    await upsert_episodes(
        db_session,
        pid,
        [
            {"guid": "past-1", "title": "Old Episode 1", "published_at": base},
            {"guid": "past-2", "title": "Old Episode 2", "published_at": base + timedelta(days=1)},
            {"guid": "undated", "title": "Undated Episode", "published_at": None},
        ],
    )
    await db_session.commit()

    first = await client.get(f"/api/v1/podcasts/{pid}", params={"limit": 1})
    assert first.status_code == 200
    page1 = first.json()["episodes"]
    assert [i["title"] for i in page1["items"]] == ["Undated Episode"]
    assert page1["next_cursor"]

    second = await client.get(
        f"/api/v1/podcasts/{pid}", params={"limit": 10, "cursor": page1["next_cursor"]}
    )
    page2 = second.json()["episodes"]
    assert [i["title"] for i in page2["items"]] == ["Old Episode 2", "Old Episode 1"]


async def test_podcast_detail_404(client) -> None:
    resp = await client.get("/api/v1/podcasts/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_podcast_detail_bad_cursor(client, db_session) -> None:
    pid = await _seed_podcast_with_episodes(db_session, count=1)
    resp = await client.get(f"/api/v1/podcasts/{pid}", params={"cursor": "!!!not-base64!!!"})
    assert resp.status_code == 422
