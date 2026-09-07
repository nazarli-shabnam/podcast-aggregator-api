"""Episode response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    podcast_id: uuid.UUID
    guid: str
    title: str
    description: str | None = None
    published_at: datetime | None = None
    audio_url: str | None = None
    duration_seconds: int | None = None
