# Multi-Session Chat Design

**Date:** 2026-02-26
**Status:** Approved

## Problem

The UI only supports a single chat session. All conversations share one global `AgentContext` and one `SQLAlchemySession`. Users cannot maintain separate conversation threads with independent analysis results.

## Decision

**Approach A — frontend-managed sessions, backend keyed by session_id.**

Frontend owns the session lifecycle (create, switch, delete). Backend isolates `AgentContext` and `SQLAlchemySession` by the `session_id` already present in requests.

## Backend Changes (`persona_lens/api/server.py`)

### Replace global singletons with per-session dicts

```python
_contexts: dict[str, AgentContext] = {}
_chat_sessions: dict[str, SQLAlchemySession] = {}
```

### `get_context(session_id)`

Lazily create an `AgentContext` per session_id:

```python
def get_context(session_id: str) -> AgentContext:
    if session_id not in _contexts:
        _contexts[session_id] = AgentContext()
    return _contexts[session_id]
```

### `get_chat_session(session_id)`

Lazily create a `SQLAlchemySession` per session_id:

```python
async def get_chat_session(session_id: str) -> SQLAlchemySession:
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = SQLAlchemySession(
            session_id, engine=_engine, create_tables=True
        )
    return _chat_sessions[session_id]
```

### `/api/analyze/{username}`

Add `session_id` query parameter. Cache results into `get_context(session_id)` instead of `_global_ctx`.

### Delete `_global_ctx` and `_chat_session` globals.

## Frontend Changes

### New hook: `useSessionManager`

```typescript
interface Session {
  id: string;        // crypto.randomUUID()
  title: string;     // auto-generated from first user message (first 30 chars)
  createdAt: number; // Date.now()
}

interface SessionManagerState {
  sessions: Session[];
  activeSessionId: string;
}
```

Operations: create, switch, delete, rename. Session list persisted to `localStorage`.

A default session is created on first visit.

### `page.tsx` — per-session analysis results

Change `analyzedProfiles` from `Record<string, AnalysisResult>` to per-session:

```typescript
Record<string, Record<string, AnalysisResult>>
// profilesBySession[sessionId][username] = AnalysisResult
```

Switching sessions switches the displayed profiles.

### `use-chat.ts` — session-aware

- Accept `sessionId` parameter
- Send `sessionId` in API requests (already has `session_id` field in `ChatRequest`)

For isolation: use `key={activeSessionId}` on `ChatPanel` to force remount on switch. Cache messages in `useSessionManager` so switching back restores history.

### `use-analysis.ts` — session-aware

- Accept `sessionId` parameter
- Pass `session_id` query param to `/api/analyze/{username}?session_id=...`

### Chat panel top bar

Add a session switcher at the top of the chat panel:

```
[+ New Chat] [▾ Session title dropdown]
```

- "+" button creates a new session and switches to it
- Dropdown shows all sessions (title + relative time), current highlighted
- Each item has a delete button (with confirmation if it's the only session)

## Data Flow

```
User clicks "New Chat"
  → useSessionManager creates Session { id, title: "Chat N", createdAt }
  → activeSessionId updates → ChatPanel remounts with new sessionId
  → Left panel clears (no profiles for this session yet)

User sends message in session B
  → POST /api/chat { session_id: "B", message: "analyze @karpathy" }
  → Backend creates AgentContext for "B" if needed
  → Agent fetches/analyzes, stores in context["B"]
  → Frontend caches result in profilesBySession["B"]

User switches back to session A
  → ChatPanel remounts with key="A", restores cached messages
  → Left panel shows profilesBySession["A"]
```

## Limitations

- In-memory SQLite: all sessions lost on server restart (switching to file-based SQLite is a one-line change)
- No server-side session cleanup / TTL (acceptable for single-user)
- Messages cached in React state only — page refresh loses chat history (session list survives in localStorage)
