# Podcast Data Aggregation & API Platform

A robust backend system designed to automate daily podcast chart collection, metadata
enrichment, and episode tracking. Built with Python, FastAPI, Celery, and PostgreSQL, the
platform maintains historical trend data and exposes high-performance RESTful API endpoints
for downstream applications.

## Key Capabilities

- **Automated Scraping** – Scheduled daily extraction of Spotify and Podchaser charts grouped
  by country and category.
- **Data Enrichment** – Automatic metadata fetching (descriptions, covers, publisher details,
  ratings) and episode tracking via external APIs (Apple Podcasts, Podcast Index, Podchaser)
  and RSS feeds.
- **Scalable Architecture** – PostgreSQL declarative RANGE partitioning of `chart_snapshots`,
  strategic composite indexing, and idempotent UPSERT ingestion.
- **RESTful API** – Low-latency endpoints for filtered chart views, paginated podcast lists
  (offset) and deep episode feeds (cursor / keyset).

## Stack

FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · asyncpg · Alembic · Celery + Redis · httpx

## Project layout

```
app/
  api/        FastAPI routers (v1)
  core/       config, async DB engine, Celery app, logging
  db/         SQLAlchemy models, mixins, partition helpers, UPSERT helpers
  schemas/    Pydantic request/response models
  services/   scrapers, enrichment clients, RSS parsing, ingestion orchestration
  tasks/      Celery tasks (scraping, enrichment, episodes, maintenance)
  main.py     app factory
alembic/      async migration environment + versions
```

## Local development

```bash
docker compose up -d                 # postgres:15 + redis:7
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

alembic upgrade head                 # schema + current/next month partitions
python -m app.cli demo               # seed demo chart data (us/technology)

uvicorn app.main:app --reload        # API on http://localhost:8000
celery -A app.core.celery_app worker -l info
celery -A app.core.celery_app beat   -l info
```

### Data sources

All chart scraping and enrichment integrations issue real HTTP requests — nothing is
fixture-backed.

- **Spotify charts** — Spotify has no official partner API for charts, but
  `podcastcharts.byspotify.com` is backed by a public, unauthenticated JSON endpoint:
  `GET https://podcastcharts.byspotify.com/api/charts/{category}?region={country}&limit=N`
  (`category` is `top-podcasts` for the overall chart, or a genre slug — Spotify uses
  hyphenated slugs for multi-word genres, e.g. `true-crime`, `health-fitness`,
  `society-culture`; match `CHART_CATEGORIES` to those for real Spotify scraping). That
  response has no RSS feed URL (only a Spotify show URI) — many charted shows, especially
  Spotify-exclusive ones, have no public feed at all — so each entry's feed is resolved via
  the Apple iTunes Search enrichment client; a show with no resolvable feed is skipped
  (logged), not treated as a scrape failure.
- **Podchaser charts** — real OAuth2 client-credentials + GraphQL integration.
- **Apple Podcasts** — keyless enrichment (title, publisher, cover, categories, **ratings** —
  `averageUserRating` / `userRatingCount`).
- **Podcast Index** — enrichment (title, description, categories); no ratings.
- **Podchaser** — enrichment (title, description, categories, ratings); also the charts source
  above. Both use the shared OAuth2 client-credentials plumbing.

Integrations that need credentials skip gracefully (log a warning, contribute no data) when
unset, rather than failing the ingestion task:

| Integration | Env vars |
|---|---|
| Podcast Index enrichment | `PODCASTINDEX_API_KEY`, `PODCASTINDEX_API_SECRET` |
| Podchaser chart scraping **and** enrichment | `PODCHASER_CLIENT_ID`, `PODCHASER_CLIENT_SECRET` (OAuth2 client-credentials) |

Apple Podcasts (iTunes Search) and Spotify charts are both keyless — no credentials needed.

### Publishing frequency

`podcasts.release_frequency_days` is not fetched from any source — none of Apple, Podcast
Index, or Podchaser publish it. It's derived **after every episode sync**
(`app/services/ingest.py::sync_episodes`): the median number of days between the podcast's
most recent dated episodes, or `NULL` with fewer than two to compare. A podcast that has
been charted but not yet episode-synced therefore reports `NULL` until the next
`sync_all_tracked_episodes_task` run (every 6h) reaches it — this is by design, not a gap.

### Scope: podcast-level granularity

Charts and enrichment operate at **podcast** granularity. The spec mentions "top episodes"
as an alternative chart shape; the two chart sources in use (Spotify's `podcastcharts`
JSON and Podchaser's `topCharts` GraphQL query) return podcast rankings only, so
episode-level charts and episode-level enrichment are intentionally not implemented.
Episodes are still fully tracked per podcast via RSS (`GET /api/v1/podcasts/{id}`).

## API

Every `/api/v1/*` route requires an `X-API-Key` header matching one of the values in
`API_KEYS` (comma-separated; an empty list rejects every request). Each key is rate-limited
independently — `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS` (default 60 req/min),
backed by Redis so it holds across multiple API instances. `/health`, `/docs`, and
`/openapi.json` stay open, no key required.

| Method & path | Description |
|---|---|
| `GET /health` | Liveness + DB check (no API key required); returns `503` when the DB check fails |
| `GET /api/v1/charts` | **required:** `country`, `category`, `source` (`spotify`\|`podchaser`); optional: `date` (defaults to the most recent scraped snapshot for that country/category/source, *not* the calendar day) |
| `GET /api/v1/podcasts` | `page`, `page_size`, `q` (title/publisher ILIKE), `category` (case-insensitive) – offset paginated |
| `GET /api/v1/podcasts/{id}` | Detail + cursor-paginated episodes (`cursor`, `limit`) |

Omitting any of `country`, `category`, or `source` on `/api/v1/charts` is a `422`.

`/api/v1/*` responses: `401` for a missing/invalid `X-API-Key`, `429` (with a `Retry-After`
header) once a key exceeds its rate limit.

## Quality gates

```bash
ruff check .          # lint + flake8-bandit ("S") security rules
black --check .
mypy app              # strict
pip-audit             # known-vulnerability scan of installed dependencies
pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

All of the above run in CI (`.github/workflows/ci.yml`) on every pull request to `main`
against live PostgreSQL and Redis services. The coverage gate is **90%**. `main` is
protected by a repository ruleset configured in GitHub Settings → Rules (PR required,
`ci` must pass, linear history).
