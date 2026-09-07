"""Opaque keyset cursor encoding for episode pagination."""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

from fastapi import HTTPException

_EPOCH = "1970-01-01T00:00:00+00:00"


def encode_cursor(published_at: datetime | None, episode_id: uuid.UUID) -> str:
    ts = (published_at or datetime.fromisoformat(_EPOCH)).isoformat()
    raw = f"{ts}|{episode_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), uuid.UUID(id_str)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid cursor: {exc}") from exc
