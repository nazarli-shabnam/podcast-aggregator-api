"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.db import engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    logger.info("starting %s (env=%s)", settings.app_name, settings.environment)
    yield
    await engine.dispose()
    await close_redis()
    logger.info("shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(api_router)

    @app.get("/health", tags=["meta"])
    async def health(response: Response) -> dict[str, str]:
        db_ok = "ok"
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            logger.warning("health db check failed: %s", exc)
            db_ok = "error"
        if db_ok != "ok":
            # 503 so load balancers / probes keying on the status code mark
            # the instance unhealthy, not just the JSON body.
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ok" if db_ok == "ok" else "degraded", "database": db_ok}

    return app


app = create_app()
