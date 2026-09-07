"""Service-layer exception hierarchy."""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for service-layer failures."""


class ConfigError(ServiceError):
    """Raised when a required credential or setting is missing."""


class TransientError(ServiceError):
    """Retryable failure (rate limit, upstream 5xx, network blip)."""
