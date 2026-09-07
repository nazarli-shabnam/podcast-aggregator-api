"""SQLAlchemy 2.0 ORM models.

``ChartSnapshot`` uses PostgreSQL declarative RANGE partitioning on
``snapshot_date``. The parent table is created empty; monthly child
partitions are provisioned by :mod:`app.db.partitions`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin


class Podcast(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "podcasts"

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    rss_feed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    publisher: Mapped[str | None] = mapped_column(String(512))
    rating_average: Mapped[float | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    external_ids: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)

    episodes: Mapped[list[Episode]] = relationship(
        back_populates="podcast", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("rss_feed_url", name="uq_podcasts_rss_feed_url"),
        Index("ix_podcasts_categories_gin", "categories", postgresql_using="gin"),
        Index("ix_podcasts_external_ids_gin", "external_ids", postgresql_using="gin"),
    )


class Episode(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "episodes"

    podcast_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("podcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    guid: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_url: Mapped[str | None] = mapped_column(String(2048))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    podcast: Mapped[Podcast] = relationship(back_populates="episodes")

    __table_args__ = (
        UniqueConstraint("podcast_id", "guid", name="uq_episodes_podcast_id_guid"),
        Index("ix_episodes_podcast_id", "podcast_id"),
        Index("ix_episodes_published_at", "published_at"),
        Index("ix_episodes_podcast_published", "podcast_id", "published_at", "id"),
    )


class ChartSnapshot(TimestampMixin, Base):
    __tablename__ = "chart_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True, nullable=False)
    podcast_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("podcasts.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)

    podcast: Mapped[Podcast] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("rank >= 1", name="rank_positive"),
        Index(
            "ix_chart_snapshots_lookup",
            "country",
            "category",
            "snapshot_date",
            "rank",
        ),
        Index("ix_chart_snapshots_podcast_date", "podcast_id", "snapshot_date"),
        UniqueConstraint(
            "source",
            "country",
            "category",
            "snapshot_date",
            "rank",
            name="uq_chart_snapshots_slot",
        ),
        {"postgresql_partition_by": "RANGE (snapshot_date)"},
    )
