# Acontext Session Backend Design

**Date:** 2026-02-27
**Goal:** Add acontext Sessions API as an alternative chat history backend, switchable via `SESSION_BACKEND` env var. `loop.py` (CLI mode) is unchanged.

---

## Architecture

Introduce a `ChatSession` protocol in `persona_lens/api/session_backend.py` with two implementations:

- **`SQLiteBackend`** — wraps `SQLAlchemySession` (openai-agents SDK), default behaviour
- **`AcontextBackend`** — calls acontext Sessions API via `AcontextClient`

`server.py` calls `make_session(session_id)` which returns the right implementation based on `SESSION_BACKEND`.

---

## Interface

```python
class ChatSession(Protocol):
    async def get_history(self) -> list[dict]
    # Returns OpenAI-format message list (role/content dicts) for the full conversation so far.

    async def save_messages(self, items: list) -> None
    # Persists new messages produced by a Runner run.
    # items = result.to_input_list() from openai-agents Runner
```

---

## Chat Endpoint Flow (both backends)

```
1. session = make_session(session_id)
2. history = await session.get_history()
3. full_input = history + [{"role": "user", "content": message}]
4. result = Runner.run_streamed(main_agent, input=full_input, context=ctx)
   # Note: session= arg removed; history managed manually
5. await session.save_messages(result.to_input_list())
```

SQLiteBackend uses `SQLAlchemySession` internally but exposes the same interface, so the chat endpoint is backend-agnostic.

---

## SQLiteBackend

- On `get_history()`: call `SQLAlchemySession.get_items()`, convert via `_items_to_messages()` (already in server.py)
- On `save_messages(items)`: store items into `SQLAlchemySession` using its internal store method

Maintains a dict of `SQLAlchemySession` objects keyed by `session_id` (same as current `_chat_sessions`).

---

## AcontextBackend

- On `get_history()`: call `client.sessions.get_messages(session_id, format="openai")`, return `.items`
- On `save_messages(items)`: call `Converter.items_to_messages(items)`, then `client.sessions.store_message()` for each
- Sessions in acontext are created lazily on first `save_messages` call (or explicitly on first chat)
- `AcontextClient` is initialised once at module level from `ACONTEXT_API_KEY` / `ACONTEXT_BASE_URL`

---

## Configuration

```env
# Default — no extra config needed
SESSION_BACKEND=sqlite

# To use acontext
SESSION_BACKEND=acontext
ACONTEXT_API_KEY=sk-ac-xxx
ACONTEXT_BASE_URL=http://localhost:8029/api/v1  # optional, for self-hosted
```

`make_session()` raises a clear error at startup if `SESSION_BACKEND=acontext` but `ACONTEXT_API_KEY` is missing.

---

## Files Changed

| File | Action |
|------|--------|
| `persona_lens/api/session_backend.py` | Create — protocol + two implementations + `make_session()` |
| `persona_lens/api/server.py` | Modify — replace `get_chat_session()` with `make_session()`, update chat endpoint flow |
| `tests/test_session_backend.py` | Create — unit tests for both backends |
| `.env.example` | Add `SESSION_BACKEND`, `ACONTEXT_API_KEY`, `ACONTEXT_BASE_URL` |

`persona_lens/agent/loop.py` — **unchanged**.

---

## Out of Scope

- Session list / metadata (sessions table in SQLite) — not replaced, stays as-is
- Profile results persistence (profile_results table) — not replaced
- CLI mode (loop.py) — not changed
- Data migration between backends
