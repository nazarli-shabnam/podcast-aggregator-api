"""normalize existing podcasts.categories to canonical form

Folds every stored category label to the canonical form the application now
writes and queries (see app.core.normalize / app.db.upsert._categories_union):
whitespace-trimmed, lower-cased, de-duplicated. Without this, rows written
before category normalisation keep mixed-case duplicates that the
``/api/v1/podcasts?category=`` filter can't match consistently.

Revision ID: 0003_normalize_categories
Revises: 0002_add_release_frequency
Create Date: 2026-09-08 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_normalize_categories"
down_revision: str | None = "0002_add_release_frequency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        UPDATE podcasts
        SET categories = COALESCE(
            (
                SELECT jsonb_agg(DISTINCT lower(btrim(value)) ORDER BY lower(btrim(value)))
                FROM jsonb_array_elements_text(categories) AS value
                WHERE btrim(value) <> ''
            ),
            '[]'::jsonb
        )
        WHERE categories IS NOT NULL AND categories <> '[]'::jsonb
        """)


def downgrade() -> None:
    # One-way data normalisation - the original casing/spacing is not retained
    # anywhere, so there is nothing to restore.
    pass
