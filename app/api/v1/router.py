"""Aggregate v1 router. Every route here requires a valid X-API-Key."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_api_key
from app.api.v1 import charts, podcasts

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(charts.router)
api_router.include_router(podcasts.router)
