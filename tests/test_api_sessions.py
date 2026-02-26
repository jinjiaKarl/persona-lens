"""Tests for per-session isolation in the API server."""

import pytest
from persona_lens.api.server import get_context, _contexts, _chat_sessions


def test_get_context_creates_new_for_unknown_session():
    _contexts.clear()
    ctx_a = get_context("user-1", "session-a")
    ctx_b = get_context("user-1", "session-b")
    assert ctx_a is not ctx_b


def test_get_context_returns_same_for_known_session():
    _contexts.clear()
    ctx1 = get_context("user-1", "session-x")
    ctx2 = get_context("user-1", "session-x")
    assert ctx1 is ctx2


def test_get_context_isolates_across_users():
    _contexts.clear()
    ctx_u1 = get_context("user-1", "session-x")
    ctx_u2 = get_context("user-2", "session-x")
    assert ctx_u1 is not ctx_u2


@pytest.mark.asyncio
async def test_get_chat_session_creates_isolated_sessions():
    from persona_lens.api.server import get_chat_session
    _chat_sessions.clear()
    s1 = await get_chat_session("user-1", "chat-1")
    s2 = await get_chat_session("user-1", "chat-2")
    assert s1 is not s2
    # Same user+session returns same instance
    s1_again = await get_chat_session("user-1", "chat-1")
    assert s1 is s1_again


@pytest.mark.asyncio
async def test_get_chat_session_isolates_across_users():
    from persona_lens.api.server import get_chat_session
    _chat_sessions.clear()
    s_u1 = await get_chat_session("user-1", "chat-x")
    s_u2 = await get_chat_session("user-2", "chat-x")
    assert s_u1 is not s_u2
