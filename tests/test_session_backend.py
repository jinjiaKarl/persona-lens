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


# ── AcontextBackend ───────────────────────────────────────────────────────────

async def test_acontext_get_history_returns_empty_when_no_messages():
    """get_history() returns [] when session has no messages (404 or empty)."""
    import os
    os.environ["ACONTEXT_API_KEY"] = "sk-ac-test"

    with patch("persona_lens.api.session_backend._ac_client", None), \
         patch("persona_lens.api.session_backend.AcontextAsyncClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # Simulate empty message list
        mock_response = MagicMock()
        mock_response.items = []
        mock_client.sessions.get_messages = AsyncMock(return_value=mock_response)

        from persona_lens.api.session_backend import AcontextBackend
        backend = AcontextBackend("user:sess-1")
        history = await backend.get_history()

    assert history == []


async def test_acontext_save_messages_stores_converted_messages():
    """save_messages() converts items via Converter and calls store_message per item."""
    import os
    os.environ["ACONTEXT_API_KEY"] = "sk-ac-test"

    with patch("persona_lens.api.session_backend._ac_client", None), \
         patch("persona_lens.api.session_backend.AcontextAsyncClient") as MockClient, \
         patch("persona_lens.api.session_backend.Converter") as MockConverter:

        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.sessions.create = AsyncMock()
        mock_client.sessions.store_message = AsyncMock()

        converted_msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        MockConverter.items_to_messages.return_value = converted_msgs

        from persona_lens.api.session_backend import AcontextBackend
        backend = AcontextBackend("user:sess-2")
        await backend.save_messages([{"role": "user", "content": "hi"}])

    assert mock_client.sessions.store_message.call_count == 2
