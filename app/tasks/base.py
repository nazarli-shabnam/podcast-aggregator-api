"""Shared Celery task configuration."""

from __future__ import annotations

import httpx

from app.services.exceptions import TransientError

RETRY_KWARGS: dict[str, object] = {
    "autoretry_for": (TransientError, httpx.HTTPError, ConnectionError),
    "retry_backoff": True,
    "retry_backoff_max": 600,
    "retry_jitter": True,
    "max_retries": 5,
}
