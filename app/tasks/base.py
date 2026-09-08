"""Shared Celery task configuration."""

from __future__ import annotations

from app.services.exceptions import TransientError

# ``request_with_retry`` (app.services.http) already retries retryable HTTP
# failures a few times and raises ``TransientError`` once exhausted, so the
# Celery layer only needs to retry on that and on connection loss - retrying
# on raw ``httpx.HTTPError`` here would stack a second multiplier on top of
# the inner loop (and would also retry non-transient 4xx responses).
RETRY_KWARGS: dict[str, object] = {
    "autoretry_for": (TransientError, ConnectionError),
    "retry_backoff": True,
    "retry_backoff_max": 600,
    "retry_jitter": True,
    "max_retries": 3,
}
