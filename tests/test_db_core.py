"""Direct tests for app/core/db.py's session helpers.

These bypass the ``client`` fixture's dependency_overrides on purpose -
that override replaces get_session() entirely for API tests, so the
real function (and session_scope's commit/rollback control flow) would
otherwise never actually run under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session, session_scope

pytestmark = pytest.mark.asyncio


async def test_get_session_yields_a_working_async_session() -> None:
    gen = get_session()
    session = await gen.__anext__()
    try:
        assert isinstance(session, AsyncSession)
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
    finally:
        # Drain the generator so its `async with` block closes the session.
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()


async def test_session_scope_commits_on_success() -> None:
    async with session_scope() as session:
        await session.execute(text("SELECT 1"))
    # No exception on exit means the commit path ran without error.


async def test_session_scope_rolls_back_and_reraises_on_exception() -> None:
    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        async with session_scope() as session:
            await session.execute(text("SELECT 1"))
            raise _Boom("simulated task failure")
