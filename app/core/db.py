"""Async SQLAlchemy engine and session management.

The API process uses a long-lived pooled ``engine``. Background workers
(Celery, CLI) drive a fresh event loop per invocation via
:func:`app.core.celery_app.run_async`; reusing a pooled connection across
loops corrupts asyncpg, so background helpers get a disposable
``NullPool`` engine each call through :func:`task_engine` / :func:`session_scope`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False, autoflush=False
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session (pooled engine)."""
    async with async_session_maker() as session:
        yield session


@asynccontextmanager
async def task_engine() -> AsyncIterator[AsyncEngine]:
    """Disposable NullPool engine for a single background invocation."""
    eng = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        yield eng
    finally:
        await eng.dispose()


@asynccontextmanager
async def task_connection() -> AsyncIterator[AsyncConnection]:
    """Transactional raw connection for background DDL / maintenance."""
    async with task_engine() as eng, eng.begin() as conn:
        yield conn


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context-managed session with commit/rollback for background work."""
    async with task_engine() as eng:
        session = async_sessionmaker(eng, expire_on_commit=False, autoflush=False)()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
