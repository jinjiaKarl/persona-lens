"""Tests for per-session isolation in the API server."""

import pytest
from persona_lens.api.server import get_context, _contexts
from persona_lens.api.session_backend import make_session, _sqlite_backends
from sqlalchemy.ext.asyncio import create_async_engine


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


def test_make_session_creates_isolated_sessions():
    _sqlite_backends.clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    s1 = make_session("user-1:chat-1", engine=engine)
    s2 = make_session("user-1:chat-2", engine=engine)
    assert s1 is not s2
    # Same key returns same instance
    s1_again = make_session("user-1:chat-1", engine=engine)
    assert s1 is s1_again


def test_make_session_isolates_across_users():
    _sqlite_backends.clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    s_u1 = make_session("user-1:chat-x", engine=engine)
    s_u2 = make_session("user-2:chat-x", engine=engine)
    assert s_u1 is not s_u2
