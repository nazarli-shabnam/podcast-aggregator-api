"""Canonicalisation helpers shared across ingest, enrichment and the API.

Categories arrive from several sources with inconsistent casing and spacing:
chart scrapers pass the configured slug (``technology``), Apple enrichment
appends iTunes genres in Title Case (``Technology``, ``Society & Culture``),
Podchaser appends its own ``categories[].text``. Without a canonical form the
same logical category lands in the DB under several spellings and the
``/api/v1/podcasts?category=`` filter (JSONB containment - exact match) only
ever hits one of them. Everything writing or querying ``podcasts.categories``
runs values through :func:`normalize_category` first.
"""

from __future__ import annotations


def normalize_category(value: str) -> str:
    """Canonical category label: whitespace-collapsed, trimmed, lower-cased.

    Uses ``str.lower`` (not ``casefold``) for exact parity with the
    ``lower(...)`` applied on the SQL side in
    :func:`app.db.upsert._categories_union`.
    """
    return " ".join(value.split()).lower()


def normalize_categories(values: list[str]) -> list[str]:
    """Normalize + de-duplicate a list of category labels, preserving order."""
    seen: dict[str, None] = {}
    for value in values:
        if not value or not value.strip():
            continue
        seen.setdefault(normalize_category(value), None)
    return list(seen)
