"""Aggregate v1 router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import charts, podcasts

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(charts.router)
api_router.include_router(podcasts.router)
