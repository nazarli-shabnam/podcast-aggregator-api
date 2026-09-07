"""Chart response schemas."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.common import ChartSource
from app.schemas.podcast import PodcastListItem


class ChartEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rank: int
    source: ChartSource
    country: str
    category: str
    snapshot_date: date
    podcast: PodcastListItem
