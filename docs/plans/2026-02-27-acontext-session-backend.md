# Acontext Session Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `AcontextBackend` as a swappable alternative to `SQLiteBackend` for chat history, toggled via `SESSION_BACKEND` env var.

**Architecture:** New `persona_lens/api/session_backend.py` defines a `ChatSession` protocol with two implementations. `server.py` calls `make_session()` instead of `get_chat_session()`. Both backends use the same manual history pattern: load before run, append new items after run. `loop.py` is untouched.

**Tech Stack:** Python/FastAPI, `acontext` Python SDK, `openai-agents` SQLAlchemySession, `agents.models.chatcmpl_converter.Converter`

---

### Task 1: Install `acontext` SDK

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add dependency**

In `pyproject.toml`, add `"acontext>=0.1"` to the `dependencies` list (after `python-dotenv`):

```toml
dependencies = [
  ...
  "python-dotenv",
  "acontext>=0.1",
  ...
]
```

**Step 2: Sync**

Run: `uv sync`
Expected: `acontext` installed successfully, no errors.

**Step 3: Verify import works**

Run: `uv run python -c "from acontext import AcontextClient; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add acontext SDK dependency"
```

---

### Task 2: Create `session_backend.py` with `SQLiteBackend`

**Files:**
- Create: `persona_lens/api/session_backend.py`
- Create: `tests/test_session_backend.py`

**Step 1: Write the failing test**

Create `tests/test_session_backend.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session_backend.py -v`
Expected: `ModuleNotFoundError` — `session_backend` doesn't exist yet.

**Step 3: Implement `SQLiteBackend`**

Create `persona_lens/api/session_backend.py`:

```python
"""Swappable chat-history backends for the persona-lens API server.

Toggle via SESSION_BACKEND env var:
  SESSION_BACKEND=sqlite      (default)
  SESSION_BACKEND=acontext    (requires ACONTEXT_API_KEY)
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from agents.extensions.memory import SQLAlchemySession
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


# ── Factory ───────────────────────────────────────────────────────────────────

# Module-level caches — one entry per (user_id, session_id) key.
_sqlite_backends: dict[str, SQLiteBackend] = {}


def make_session(session_key: str, *, engine: AsyncEngine | None = None) -> ChatSession:
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
        # AcontextBackend added in Task 3
        from persona_lens.api.session_backend import AcontextBackend  # noqa: PLC0415
        return AcontextBackend(session_key)

    raise ValueError(f"Unknown SESSION_BACKEND={backend!r}. Use 'sqlite' or 'acontext'.")
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session_backend.py::test_sqlite_get_history_returns_items tests/test_session_backend.py::test_sqlite_save_and_reload -v`
Expected: Both PASS.

**Step 5: Commit**

```bash
git add persona_lens/api/session_backend.py tests/test_session_backend.py
git commit -m "feat: add SQLiteBackend and ChatSession protocol"
```

---

### Task 3: Add `AcontextBackend`

**Files:**
- Modify: `persona_lens/api/session_backend.py`
- Modify: `tests/test_session_backend.py`

**Step 1: Add failing tests**

Append to `tests/test_session_backend.py`:

```python
# ── AcontextBackend ───────────────────────────────────────────────────────────

async def test_acontext_get_history_returns_empty_when_no_messages():
    """get_history() returns [] when session has no messages (404 or empty)."""
    import os
    os.environ["ACONTEXT_API_KEY"] = "sk-ac-test"

    with patch("persona_lens.api.session_backend.AcontextClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        # Simulate empty message list
        mock_response = MagicMock()
        mock_response.items = []
        mock_client.sessions.get_messages.return_value = mock_response

        from persona_lens.api.session_backend import AcontextBackend
        backend = AcontextBackend("user:sess-1")
        history = await backend.get_history()

    assert history == []


async def test_acontext_save_messages_stores_converted_messages():
    """save_messages() converts items via Converter and calls store_message per item."""
    import os
    os.environ["ACONTEXT_API_KEY"] = "sk-ac-test"

    with patch("persona_lens.api.session_backend.AcontextClient") as MockClient, \
         patch("persona_lens.api.session_backend.Converter") as MockConverter:

        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.sessions.create = MagicMock()
        mock_client.sessions.store_message = MagicMock()

        converted_msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        MockConverter.items_to_messages.return_value = converted_msgs

        from importlib import reload
        import persona_lens.api.session_backend as mod
        reload(mod)  # pick up patched env var

        backend = mod.AcontextBackend("user:sess-2")
        await backend.save_messages([{"role": "user", "content": "hi"}])

    assert mock_client.sessions.store_message.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_session_backend.py -k "acontext" -v`
Expected: `ImportError` — `AcontextBackend` not defined yet.

**Step 3: Implement `AcontextBackend`**

Add to `persona_lens/api/session_backend.py`, after the `SQLiteBackend` class and before the factory:

```python
# ── AcontextBackend ───────────────────────────────────────────────────────────

from agents.models.chatcmpl_converter import Converter
from acontext import AcontextClient

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
        # session_key is "user_id:session_id" — use as acontext session ID.
        # acontext accepts arbitrary string IDs (not just UUIDs).
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
```

Also update `make_session()` to remove the local import (it's now at module level):

```python
    if backend == "acontext":
        api_key = os.getenv("ACONTEXT_API_KEY")
        if not api_key:
            raise ValueError(
                "SESSION_BACKEND=acontext requires ACONTEXT_API_KEY to be set"
            )
        return AcontextBackend(session_key)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_session_backend.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add persona_lens/api/session_backend.py tests/test_session_backend.py
git commit -m "feat: add AcontextBackend for chat history via acontext Sessions API"
```

---

### Task 4: Update `server.py` to use `make_session()`

**Files:**
- Modify: `persona_lens/api/server.py`

**Step 1: Replace imports and `_chat_sessions` dict**

At the top of `server.py`, remove:
```python
from agents.extensions.memory import SQLAlchemySession
```

Add:
```python
from persona_lens.api.session_backend import make_session
```

Remove the module-level:
```python
_chat_sessions: dict[str, SQLAlchemySession] = {}
```

**Step 2: Remove `get_chat_session()` function**

Delete the entire `get_chat_session()` function (lines ~209-215).

**Step 3: Update `get_chat_history` endpoint**

Replace:
```python
async def get_chat_history(user_id: str, session_id: str):
    """Return the full chat history for a session in display format."""
    session = await get_chat_session(user_id, session_id)
    items = await session.get_items()
    return _items_to_display_messages(items)
```

With:
```python
async def get_chat_history(user_id: str, session_id: str):
    """Return the full chat history for a session in display format."""
    session = make_session(_ctx_key(user_id, session_id), engine=_engine)
    history = await session.get_history()
    return _items_to_display_messages(history)
```

**Step 4: Update the `chat` endpoint**

Replace the current `chat` endpoint body from:
```python
ctx = get_context(req.user_id, req.session_id)
session = await get_chat_session(req.user_id, req.session_id)

async def _generate() -> AsyncGenerator[dict, None]:
    ...
    result = Runner.run_streamed(
        main_agent,
        input=req.message,
        context=ctx,
        session=session,
    )
    async for event in result.stream_events():
        ...
    # persist new users ...
    yield {"event": "done", "data": "{}"}
```

With this updated version (the `_generate` closure and the `chat` function body):

```python
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream chat responses from the main agent via SSE."""
    ctx = get_context(req.user_id, req.session_id)
    session = make_session(_ctx_key(req.user_id, req.session_id), engine=_engine)

    async def _generate() -> AsyncGenerator[dict, None]:
        before_analyses: set[str] = set(ctx.analysis_cache.get("x", {}).keys())

        try:
            # 1. Load history, build full input.
            history = await session.get_history()
            full_input = list(history) + [{"role": "user", "content": req.message}]
            history_len = len(history)

            # 2. Run agent (no session= arg — we manage history manually).
            result = Runner.run_streamed(
                main_agent,
                input=full_input,
                context=ctx,
            )

            # 3. Stream events.
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    if isinstance(event.data, ResponseTextDeltaEvent):
                        delta = event.data.delta
                        if delta:
                            yield {
                                "event": "token",
                                "data": json.dumps({"delta": delta}),
                            }
                elif event.type == "run_item_stream_event":
                    item = event.item
                    item_type = getattr(item, "type", "")
                    if item_type == "tool_call_item":
                        raw = getattr(item, "raw_item", None)
                        tool_name = getattr(raw, "name", "") if raw else ""
                        if tool_name:
                            yield {
                                "event": "tool_call",
                                "data": json.dumps({"tool": tool_name, "status": "running"}),
                            }

            # 4. Persist new turn (user msg + agent response).
            all_items = result.to_input_list()
            new_items = all_items[history_len:]  # slice off prior history
            await session.save_messages(new_items)

            # 5. Emit analysis_result for newly analyzed users and persist them.
            after_analyses: set[str] = set(ctx.analysis_cache.get("x", {}).keys())
            new_users = after_analyses - before_analyses
            for username in new_users:
                x_profile = ctx.profile_cache.get("x", {}).get(username, {})
                x_summary = ctx.analysis_cache["x"][username]
                if x_profile:
                    analysis = {
                        "products": x_summary.get("products", []),
                        "writing_style": x_summary.get("writing_style", ""),
                        "engagement": {
                            "top_posts": x_summary.get("top_posts", []),
                            "insights": x_summary.get("engagement_insights", ""),
                        },
                    }
                    profile_result = {
                        "user_info": x_profile.get("user_info", {}),
                        "tweets": x_profile.get("tweets", []),
                        "patterns": x_profile.get("patterns", {}),
                        "analysis": analysis,
                    }
                    await _save_profile(req.user_id, req.session_id, username, profile_result)
                    yield {
                        "event": "analysis_result",
                        "data": json.dumps(profile_result, ensure_ascii=False),
                    }

            yield {"event": "done", "data": "{}"}

        except Exception as exc:
            msg = str(exc)
            fix = ""
            if "9377" in msg or "camofox" in msg.lower() or "Connection" in msg:
                fix = "Start Camofox Browser: cd camofox-browser && npm start"
            elif "OPENAI_API_KEY" in msg:
                fix = "Set OPENAI_API_KEY in your .env file"
            yield {
                "event": "error",
                "data": json.dumps({"error": msg, "fix": fix}),
            }

    return EventSourceResponse(_generate())
```

**Step 5: Run existing tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

**Step 6: Quick smoke check (import only)**

Run: `uv run python -c "from persona_lens.api.server import app; print('ok')"`
Expected: `ok`

**Step 7: Commit**

```bash
git add persona_lens/api/server.py
git commit -m "feat: replace get_chat_session with make_session, manual history management"
```

---

### Task 5: Update `.env.example`

**Files:**
- Modify: `.env.example`

**Step 1: Add new variables**

Open `.env.example` and append:

```env
# ── Session Backend ────────────────────────────────────────────────────────────
# Options: sqlite (default, no extra config) | acontext (requires ACONTEXT_API_KEY)
SESSION_BACKEND=sqlite

# Required when SESSION_BACKEND=acontext
# ACONTEXT_API_KEY=sk-ac-your-key-here
# ACONTEXT_BASE_URL=http://localhost:8029/api/v1   # optional: self-hosted instance
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add SESSION_BACKEND, ACONTEXT_API_KEY env vars to .env.example"
```

---

### Task 6: End-to-end smoke test

**Step 1: Start backend with sqlite (default)**

Run: `uv run uvicorn persona_lens.api.server:app --port 8000`

In another terminal:
```bash
curl -s http://localhost:8000/api/health
```
Expected: `{"status":"ok"}`

**Step 2: Verify chat history endpoint returns empty list for new session**

```bash
curl -s http://localhost:8000/api/users/default/sessions/smoke-test/messages
```
Expected: `[]`

**Step 3: Run all tests one final time**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS.

**Step 4: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address smoke test findings"
```
