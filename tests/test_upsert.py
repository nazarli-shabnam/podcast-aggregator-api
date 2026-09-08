from __future__ import annotations

from sqlalchemy import select, text

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
    Every label is also canonicalised (internal whitespace collapsed, trimmed,
    lower-cased) so near-duplicates from different sources collapse to one entry.
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
            "categories": ["  technology ", "Business", "NEWS", "Society   &   Culture"],
        },
    )
    podcast = await db_session.get(Podcast, pid)
    assert set(podcast.categories) == {"news", "technology", "business", "society & culture"}

    # an empty / absent categories value leaves the stored list untouched
    await upsert_podcast(
        db_session,
        {"title": "Cat Show", "rss_feed_url": "https://feeds.test/cat", "categories": []},
    )
    await upsert_podcast(
        db_session, {"title": "Cat Show 2", "rss_feed_url": "https://feeds.test/cat"}
    )
    await db_session.refresh(podcast)
    assert set(podcast.categories) == {"news", "technology", "business", "society & culture"}


async def test_upsert_podcast_union_folds_legacy_uncanonical_categories(db_session) -> None:
    """A row written before category normalisation existed can hold mixed-case,
    irregularly-spaced labels. The ON CONFLICT union (_categories_union) must fold
    them to the same canonical form the app now writes/queries, so re-ingest
    converges instead of leaving permanently-unfilterable duplicates.
    """
    feed = "https://feeds.test/legacy"
    # JSON with escaped tab/newline + doubled spaces: exactly the shape a
    # pre-normalisation writer could leave that one-arg btrim() would not fix.
    legacy = r'["Society   &   Culture", "society & culture", "\tTech\n", "  Tech  "]'
    pid = (
        await db_session.execute(
            text(
                "INSERT INTO podcasts (title, rss_feed_url, categories) "
                "VALUES (:t, :u, CAST(:c AS jsonb)) RETURNING id"
            ),
            {"t": "Legacy Show", "u": feed, "c": legacy},
        )
    ).scalar_one()

    # A plain daily re-scrape that only knows "news".
    await upsert_podcast(
        db_session,
        {"title": "Legacy Show", "rss_feed_url": feed, "categories": ["News"]},
    )

    podcast = await db_session.get(Podcast, pid)
    assert set(podcast.categories) == {"society & culture", "tech", "news"}


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
