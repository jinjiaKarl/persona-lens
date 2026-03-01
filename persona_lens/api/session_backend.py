"""Swappable chat-history backends for the persona-lens API server.

Toggle via SESSION_BACKEND env var:
  SESSION_BACKEND=sqlite      (default)
  SESSION_BACKEND=acontext    (requires ACONTEXT_API_KEY)
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

_log = logging.getLogger(__name__)

from agents.extensions.memory import SQLAlchemySession
from agents.models.chatcmpl_converter import Converter
from acontext import AcontextAsyncClient
from acontext.errors import APIError as AcontextAPIError
from sqlalchemy.ext.asyncio import AsyncEngine


# ── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class ChatSession(Protocol):
    """Minimal interface for a per-session chat history store."""

    async def get_history(self) -> list:
        """Return all stored messages as a list usable as Runner input.

        SQLiteBackend returns list[TResponseInputItem].
        AcontextBackend returns list[dict] (OpenAI message format).
        Both are accepted by Runner.run_streamed(input=...).
        """
        ...

    async def save_messages(self, new_items: list) -> None:
        """Persist new items produced in the current turn.

        Pass result.to_input_list()[len(history):] — items since the last
        history snapshot, i.e. this turn's user message + agent response.
        """
        ...


# ── SQLiteBackend ─────────────────────────────────────────────────────────────

class SQLiteBackend:
    """Wraps SQLAlchemySession; stores history in local SQLite."""

    def __init__(self, session_id: str, *, engine: AsyncEngine) -> None:
        self._sa = SQLAlchemySession(session_id, engine=engine, create_tables=True)

    async def get_history(self) -> list:
        return list(await self._sa.get_items())

    async def save_messages(self, new_items: list) -> None:
        if new_items:
            await self._sa.add_items(new_items)


# ── AcontextBackend ───────────────────────────────────────────────────────────

# Singleton client — initialised lazily so missing API key fails at runtime, not import.
_ac_client: AcontextAsyncClient | None = None


async def _get_ac_client() -> AcontextAsyncClient:
    global _ac_client
    if _ac_client is None:
        api_key = os.getenv("ACONTEXT_API_KEY")
        base_url = os.getenv("ACONTEXT_BASE_URL")  # None = use hosted default
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        _ac_client = AcontextAsyncClient(**kwargs)
    return _ac_client


class AcontextBackend:
    """Stores chat history in acontext Sessions API."""

    def __init__(self, session_key: str, *, session_id: str, user_id: str | None = None) -> None:
        self._session_key = session_key  # cache key only ("user_id:session_id")
        self._session_id = session_id    # actual UUID used for acontext API calls
        self._user_id = user_id          # bound to acontext user for multi-tenant isolation
        self._session_created = False

    async def get_history(self) -> list:
        client = await _get_ac_client()
        try:
            response = await client.sessions.get_messages(self._session_id, format="openai")
            messages = list(response.items) if response.items else []
            # OpenAI chat format allows content=null on assistant messages that only
            # carry tool_calls, but the Responses API (used by Runner) rejects null.
            for msg in messages:
                if isinstance(msg, dict) and msg.get("content") is None:
                    msg["content"] = ""
            return messages
        except Exception as exc:
            # Session doesn't exist yet → empty history (expected on first turn).
            # Any other error is logged so it doesn't silently disappear.
            _log.warning("acontext get_history failed (session=%s): %s", self._session_id, exc)
            return []

    async def save_messages(self, new_items: list) -> None:
        if not new_items:
            return
        client = await _get_ac_client()

        # Ensure session exists (idempotent).
        if not self._session_created:
            try:
                kwargs: dict = {"use_uuid": self._session_id}
                if self._user_id:
                    kwargs["user"] = self._user_id
                await client.sessions.create(**kwargs)
                self._session_created = True
            except AcontextAPIError as exc:
                if exc.status_code == 409:
                    # Session already exists — that's fine, proceed to store.
                    self._session_created = True
                else:
                    _log.error("acontext session create failed (session=%s): %s", self._session_id, exc)
                    raise
            except Exception as exc:
                _log.error("acontext session create failed (session=%s): %s", self._session_id, exc)
                raise

        # Convert from TResponseInputItem format to OpenAI messages.
        messages = Converter.items_to_messages(new_items)
        for msg in messages:
            try:
                await client.sessions.store_message(
                    session_id=self._session_id, blob=msg, format="openai"
                )
            except Exception as exc:
                _log.error("acontext store_message failed (session=%s): %s", self._session_id, exc)
                raise


# ── Factory ───────────────────────────────────────────────────────────────────

# Module-level caches — one entry per (user_id, session_id) key.
_sqlite_backends: dict[str, SQLiteBackend] = {}
_acontext_backends: dict[str, AcontextBackend] = {}


def make_session(
    session_key: str,
    *,
    engine: AsyncEngine | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
) -> "ChatSession":
    """Return the appropriate ChatSession for the given key.

    session_key — composite "user_id:session_id", used as cache key.
    session_id  — the raw UUID from the frontend, used as the acontext session ID.
    user_id     — passed to AcontextBackend for per-user isolation in acontext.

    Raises ValueError if SESSION_BACKEND=acontext but ACONTEXT_API_KEY is unset.
    """
    backend = os.getenv("SESSION_BACKEND", "sqlite").lower()

    if backend == "sqlite":
        if engine is None:
            raise ValueError("make_session requires engine= when backend=sqlite")
        if session_key not in _sqlite_backends:
            _sqlite_backends[session_key] = SQLiteBackend(session_key, engine=engine)
        return _sqlite_backends[session_key]

    if backend == "acontext":
        api_key = os.getenv("ACONTEXT_API_KEY")
        if not api_key:
            raise ValueError(
                "SESSION_BACKEND=acontext requires ACONTEXT_API_KEY to be set"
            )
        ac_session_id = session_id or session_key  # fall back to session_key if not provided
        if session_key not in _acontext_backends:
            _acontext_backends[session_key] = AcontextBackend(
                session_key, session_id=ac_session_id, user_id=user_id
            )
        return _acontext_backends[session_key]

    raise ValueError(f"Unknown SESSION_BACKEND={backend!r}. Use 'sqlite' or 'acontext'.")
