"""Tests for per-session isolation in the API server."""

import pytest
from persona_lens.api.server import get_context, _contexts, _chat_sessions

pytestmark = pytest.mark.asyncio


def test_get_context_creates_new_for_unknown_session():
    _contexts.clear()
    ctx_a = get_context("session-a")
    ctx_b = get_context("session-b")
    assert ctx_a is not ctx_b


def test_get_context_returns_same_for_known_session():
    _contexts.clear()
    ctx1 = get_context("session-x")
    ctx2 = get_context("session-x")
    assert ctx1 is ctx2


async def test_get_chat_session_creates_isolated_sessions():
    from persona_lens.api.server import get_chat_session
    _chat_sessions.clear()
    s1 = await get_chat_session("chat-1")
    s2 = await get_chat_session("chat-2")
    assert s1 is not s2
    # Same id returns same session
    s1_again = await get_chat_session("chat-1")
    assert s1 is s1_again
