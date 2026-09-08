"""Shared enums and generic pagination envelopes."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ChartSource(StrEnum):
    SPOTIFY = "spotify"
    PODCHASER = "podchaser"


class Page(BaseModel, Generic[T]):
    """Offset-based pagination envelope."""

    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @property
    def pages(self) -> int:
        # page_size is validated >= 1 (Field(ge=1) above), so no zero-guard needed.
        return (self.total + self.page_size - 1) // self.page_size


class CursorPage(BaseModel, Generic[T]):
    """Keyset (cursor) pagination envelope."""

    items: list[T]
    next_cursor: str | None = None
    limit: int = Field(ge=1)
