"""Swappable chat-history backends for the persona-lens API server.

Toggle via SESSION_BACKEND env var:
  SESSION_BACKEND=sqlite      (default)
  SESSION_BACKEND=acontext    (requires ACONTEXT_API_KEY)
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from agents.extensions.memory import SQLAlchemySession
from agents.models.chatcmpl_converter import Converter
from acontext import AcontextClient
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
_ac_client: AcontextClient | None = None


def _get_ac_client() -> AcontextClient:
    global _ac_client
    if _ac_client is None:
        api_key = os.getenv("ACONTEXT_API_KEY")
        base_url = os.getenv("ACONTEXT_BASE_URL")  # None = use hosted default
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        _ac_client = AcontextClient(**kwargs)
    return _ac_client


class AcontextBackend:
    """Stores chat history in acontext Sessions API."""

    def __init__(self, session_key: str) -> None:
        # session_key is "user_id:session_id" — used as acontext session ID.
        self._session_key = session_key
        self._session_created = False

    async def get_history(self) -> list:
        client = _get_ac_client()
        try:
            response = client.sessions.get_messages(self._session_key, format="openai")
            # Each item in response.items is an OpenAI-format message dict.
            return [item for item in response.items] if response.items else []
        except Exception:
            # Session doesn't exist yet or other transient error → empty history.
            return []

    async def save_messages(self, new_items: list) -> None:
        if not new_items:
            return
        client = _get_ac_client()

        # Ensure session exists (idempotent).
        if not self._session_created:
            try:
                client.sessions.create(use_uuid=self._session_key)
            except Exception:
                pass  # Already exists — ignore.
            self._session_created = True

        # Convert from TResponseInputItem format to OpenAI messages.
        messages = Converter.items_to_messages(new_items)
        for msg in messages:
            client.sessions.store_message(
                session_id=self._session_key, blob=msg, format="openai"
            )


# ── Factory ───────────────────────────────────────────────────────────────────

# Module-level caches — one entry per (user_id, session_id) key.
_sqlite_backends: dict[str, SQLiteBackend] = {}


def make_session(session_key: str, *, engine: AsyncEngine | None = None) -> "ChatSession":
    """Return the appropriate ChatSession for the given key.

    session_key should be the composite "user_id:session_id" string used
    throughout server.py.

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
        return AcontextBackend(session_key)

    raise ValueError(f"Unknown SESSION_BACKEND={backend!r}. Use 'sqlite' or 'acontext'.")
