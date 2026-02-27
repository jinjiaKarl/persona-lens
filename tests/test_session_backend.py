"""Tests for ChatSession backends."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

pytestmark = pytest.mark.asyncio


# ── SQLiteBackend ─────────────────────────────────────────────────────────────

async def test_sqlite_get_history_returns_items():
    """get_history() delegates to SQLAlchemySession.get_items()."""
    from persona_lens.api.session_backend import SQLiteBackend
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    backend = SQLiteBackend("test-session", engine=engine)

    # Newly created session has no history
    history = await backend.get_history()
    assert history == []


async def test_sqlite_save_and_reload():
    """save_messages() persists items that get_history() returns next call."""
    from persona_lens.api.session_backend import SQLiteBackend
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    backend = SQLiteBackend("test-session-2", engine=engine)

    items = [{"role": "user", "content": "hello"}]
    await backend.save_messages(items)

    history = await backend.get_history()
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
