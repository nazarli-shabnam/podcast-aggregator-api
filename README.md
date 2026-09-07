# Podcast Data Aggregation & API Platform

A robust backend system designed to automate daily podcast chart collection, metadata
enrichment, and episode tracking. Built with Python, FastAPI, Celery, and PostgreSQL, the
platform maintains historical trend data and exposes high-performance RESTful API endpoints
for downstream applications.

## Key Capabilities

- **Automated Scraping** – Scheduled daily extraction of Spotify and Podchaser charts grouped
  by country and category.
- **Data Enrichment** – Automatic metadata fetching (descriptions, covers, publisher details)
  and episode tracking via external APIs (Apple Podcasts, Podcast Index) and RSS feeds.
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
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

alembic upgrade head                 # schema + current/next month partitions
python -m app.cli demo               # seed demo chart data (us/technology)

uvicorn app.main:app --reload        # API on http://localhost:8000
celery -A app.core.celery_app worker -l info
celery -A app.core.celery_app beat   -l info
```

### Data sources

Apple Podcasts (iTunes Search API), Podcast Index enrichment, and Podchaser chart scraping
issue real HTTP requests. Spotify chart scraping stays a fixture-backed stub behind the same
`ChartScraper` interface (`app/services/charts/`) **by design, not as a pending TODO** —
Spotify publishes no official or public podcast-charts API, and scraping their unofficial
charts webpage would be fragile and outside their published API surface.

Each real integration skips gracefully (logs a warning, contributes no data) when its
credentials are unset, rather than failing the ingestion task:

| Integration | Env vars |
|---|---|
| Podcast Index enrichment | `PODCASTINDEX_API_KEY`, `PODCASTINDEX_API_SECRET` |
| Podchaser chart scraping | `PODCHASER_CLIENT_ID`, `PODCHASER_CLIENT_SECRET` (OAuth2 client-credentials) |

## API

Every `/api/v1/*` route requires an `X-API-Key` header matching one of the values in
`API_KEYS` (comma-separated; an empty list rejects every request). Each key is rate-limited
independently — `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS` (default 60 req/min),
backed by Redis so it holds across multiple API instances. `/health`, `/docs`, and
`/openapi.json` stay open, no key required.

| Method & path | Description |
|---|---|
| `GET /health` | Liveness + DB check (no API key required) |
| `GET /api/v1/charts` | `country`, `category`, `source` (spotify\|podchaser), `date` (default today) |
| `GET /api/v1/podcasts` | `page`, `page_size`, `q` (title/publisher ILIKE), `category` – offset paginated |
| `GET /api/v1/podcasts/{id}` | Detail + cursor-paginated episodes (`cursor`, `limit`) |

`/api/v1/*` responses: `401` for a missing/invalid `X-API-Key`, `429` (with a `Retry-After`
header) once a key exceeds its rate limit.

## Quality gates

```bash
ruff check .
black --check .
mypy app
pytest --cov=app --cov-report=term-missing --cov-fail-under=90
```

All of the above run in CI (`.github/workflows/ci.yml`) on every pull request to `main`
against live PostgreSQL and Redis services. `main` is protected by a repository ruleset
configured in GitHub Settings → Rules (PR required, `ci` must pass, linear history).
