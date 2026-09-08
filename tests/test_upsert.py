from __future__ import annotations

from sqlalchemy import select

from app.db.models import Episode, Podcast
from app.db.upsert import upsert_episodes, upsert_podcast


async def test_upsert_podcast_inserts_then_merges_external_ids(db_session) -> None:
    pid = await upsert_podcast(
        db_session,
        {
            "title": "Show A",
            "rss_feed_url": "https://feeds.test/a",
            "categories": ["technology"],
            "external_ids": {"spotify": "s1"},
        },
    )
    pid2 = await upsert_podcast(
        db_session,
        {
            "title": "Show A (updated)",
            "rss_feed_url": "https://feeds.test/a",
            "external_ids": {"apple": "a1"},
        },
    )
    assert pid == pid2
    podcast = await db_session.get(Podcast, pid)
    assert podcast.title == "Show A (updated)"
    assert podcast.external_ids == {"spotify": "s1", "apple": "a1"}


async def test_upsert_podcast_unions_categories_on_conflict(db_session) -> None:
    """A chart scrape only knows one category; it must not wipe the richer
    list a prior enrichment stored - the two are unioned, de-duplicated.
    Every label is also canonicalised (trimmed + lower-cased) so mixed-case
    duplicates from different sources collapse to one entry.
    """
    pid = await upsert_podcast(
        db_session,
        {
            "title": "Cat Show",
            "rss_feed_url": "https://feeds.test/cat",
            "categories": ["News", "Technology"],
        },
    )
    await upsert_podcast(
        db_session,
        {
            "title": "Cat Show",
            "rss_feed_url": "https://feeds.test/cat",
            "categories": ["  technology ", "Business", "NEWS"],
        },
    )
    podcast = await db_session.get(Podcast, pid)
    assert set(podcast.categories) == {"news", "technology", "business"}

    # an empty / absent categories value leaves the stored list untouched
    await upsert_podcast(
        db_session,
        {"title": "Cat Show", "rss_feed_url": "https://feeds.test/cat", "categories": []},
    )
    await upsert_podcast(
        db_session, {"title": "Cat Show 2", "rss_feed_url": "https://feeds.test/cat"}
    )
    await db_session.refresh(podcast)
    assert set(podcast.categories) == {"news", "technology", "business"}


async def test_upsert_episodes_is_idempotent(db_session) -> None:
    pid = await upsert_podcast(db_session, {"title": "S", "rss_feed_url": "https://feeds.test/s"})
    rows = [{"guid": "g1", "title": "Ep 1"}, {"guid": "g2", "title": "Ep 2"}]
    assert await upsert_episodes(db_session, pid, rows) == 2
    await upsert_episodes(db_session, pid, [{"guid": "g1", "title": "Ep 1 v2"}])

    episodes = (
        (await db_session.execute(select(Episode).where(Episode.podcast_id == pid))).scalars().all()
    )
    assert len(episodes) == 2
    assert {e.guid: e.title for e in episodes}["g1"] == "Ep 1 v2"


async def test_upsert_episodes_with_empty_list_is_a_noop(db_session) -> None:
    pid = await upsert_podcast(db_session, {"title": "S", "rss_feed_url": "https://feeds.test/s2"})
    assert await upsert_episodes(db_session, pid, []) == 0
