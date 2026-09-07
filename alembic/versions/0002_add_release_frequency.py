"""add podcasts.release_frequency_days

Revision ID: 0002_add_release_frequency
Revises: 0001_initial
Create Date: 2026-09-07 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_release_frequency"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE podcasts ADD COLUMN release_frequency_days NUMERIC(6, 2)")


def downgrade() -> None:
    op.execute("ALTER TABLE podcasts DROP COLUMN release_frequency_days")
