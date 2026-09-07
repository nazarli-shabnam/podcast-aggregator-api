"""initial schema: podcasts, episodes, partitioned chart_snapshots

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from alembic import op
from app.db.partitions import _month_bounds, create_monthly_partition_sql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.execute("""
        CREATE TABLE podcasts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(512) NOT NULL,
            description TEXT,
            image_url VARCHAR(2048),
            rss_feed_url VARCHAR(2048) NOT NULL,
            publisher VARCHAR(512),
            rating_average NUMERIC(3, 2),
            rating_count INTEGER NOT NULL DEFAULT 0,
            categories JSONB NOT NULL DEFAULT '[]'::jsonb,
            external_ids JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_podcasts_rss_feed_url UNIQUE (rss_feed_url)
        )
        """)
    op.execute("CREATE INDEX ix_podcasts_categories_gin ON podcasts USING gin (categories)")
    op.execute("CREATE INDEX ix_podcasts_external_ids_gin ON podcasts USING gin (external_ids)")
    op.execute("CREATE INDEX ix_podcasts_title_trgm ON podcasts USING gin (title gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_podcasts_publisher_trgm ON podcasts USING gin (publisher gin_trgm_ops)"
    )

    op.execute("""
        CREATE TABLE episodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            podcast_id UUID NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
            guid VARCHAR(1024) NOT NULL,
            title VARCHAR(1024) NOT NULL,
            description TEXT,
            published_at TIMESTAMPTZ,
            audio_url VARCHAR(2048),
            duration_seconds INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_episodes_podcast_id_guid UNIQUE (podcast_id, guid)
        )
        """)
    op.execute("CREATE INDEX ix_episodes_podcast_id ON episodes (podcast_id)")
    op.execute("CREATE INDEX ix_episodes_published_at ON episodes (published_at)")
    op.execute(
        "CREATE INDEX ix_episodes_podcast_published ON episodes (podcast_id, published_at, id)"
    )

    op.execute("""
        CREATE TABLE chart_snapshots (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            snapshot_date DATE NOT NULL,
            podcast_id UUID NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            source VARCHAR(32) NOT NULL,
            country VARCHAR(2) NOT NULL,
            category VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_chart_snapshots PRIMARY KEY (id, snapshot_date),
            CONSTRAINT ck_chart_snapshots_rank_positive CHECK (rank >= 1),
            CONSTRAINT uq_chart_snapshots_slot
                UNIQUE (source, country, category, snapshot_date, rank)
        ) PARTITION BY RANGE (snapshot_date)
        """)
    op.execute(
        "CREATE INDEX ix_chart_snapshots_lookup "
        "ON chart_snapshots (country, category, snapshot_date, rank)"
    )
    op.execute(
        "CREATE INDEX ix_chart_snapshots_podcast_date "
        "ON chart_snapshots (podcast_id, snapshot_date)"
    )

    today = date.today()
    op.execute(create_monthly_partition_sql(today))
    _, next_month = _month_bounds(today)
    op.execute(create_monthly_partition_sql(next_month))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chart_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS episodes CASCADE")
    op.execute("DROP TABLE IF EXISTS podcasts CASCADE")
