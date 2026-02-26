# Chat History Restore Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the full chat conversation (user messages, agent responses, tool call indicators) when the user refreshes the page.

**Architecture:** Chat messages are already persisted in the `agent_messages` SQLite table by the OpenAI Agents SDK. This plan adds a GET endpoint that reads those items via `SQLAlchemySession.get_items()`, converts them to a displayable format, and updates `useChat` to fetch and pre-populate messages on mount.

**Tech Stack:** Python/FastAPI + OpenAI Agents SDK `SQLAlchemySession` (backend), React hooks + TypeScript (frontend).

---

### Task 1: Backend — `GET /api/users/{user_id}/sessions/{session_id}/messages`

**Files:**
- Modify: `persona_lens/api/server.py`
- Test: `tests/test_chat_history.py`

**Background on the data format:**

`SQLAlchemySession.get_items()` returns a list of `TResponseInputItem` objects. Each is one of:
- User message: `{"type": "message", "role": "user", "content": str | list}`
  - String content: plain text
  - List content: `[{"type": "input_text", "text": "..."}]`
- Assistant message: `{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "..."}]}`
- Tool call: `{"type": "function_call", "name": "fetch_user", "call_id": "...", "arguments": "..."}`
- Tool output: `{"type": "function_call_output", ...}` — skip, not displayed

Items arrive in chronological order. Tool calls precede the assistant message they belong to, so collect them and attach to the next assistant message.

**Step 1: Write the failing tests**

Create `tests/test_chat_history.py`:

```python
"""Tests for GET /api/users/{user_id}/sessions/{session_id}/messages endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport
from persona_lens.api.server import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_empty_history_returns_empty_list(client):
    """New session with no messages returns []."""
    async with client as c:
        r = await c.get("/api/users/default/sessions/brand-new-session/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_history_converts_user_and_agent_messages(client):
    """Simulate the SDK storing messages, then verify the endpoint converts them."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("default", "hist-test-1")
    # Add a user message and an assistant response the same way the SDK does
    await session.add_items([
        {"type": "message", "role": "user", "content": "Hello"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi there!"}]},
    ])

    async with client as c:
        r = await c.get("/api/users/default/sessions/hist-test-1/messages")
    data = r.json()
    assert len(data) == 2
    assert data[0] == {"role": "user", "content": "Hello", "toolCalls": []}
    assert data[1] == {"role": "agent", "content": "Hi there!", "toolCalls": []}

    # Cleanup
    await session.clear_session()


async def test_history_attaches_tool_calls_to_agent_message(client):
    """Tool call items should be collected and attached to the following agent message."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("default", "hist-test-2")
    await session.add_items([
        {"type": "message", "role": "user", "content": "Analyze @karpathy"},
        {"type": "function_call", "name": "fetch_user", "call_id": "c1", "arguments": "{}"},
        {"type": "function_call", "name": "analyze_user", "call_id": "c2", "arguments": "{}"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done!"}]},
    ])

    async with client as c:
        r = await c.get("/api/users/default/sessions/hist-test-2/messages")
    data = r.json()
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[1]["role"] == "agent"
    assert data[1]["content"] == "Done!"
    assert len(data[1]["toolCalls"]) == 2
    assert data[1]["toolCalls"][0] == {"tool": "fetch_user", "status": "done"}
    assert data[1]["toolCalls"][1] == {"tool": "analyze_user", "status": "done"}

    await session.clear_session()


async def test_history_isolated_across_users(client):
    """Messages for user-a are not visible to user-b."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("user-a", "shared-session")
    await session.add_items([
        {"type": "message", "role": "user", "content": "Secret"},
    ])

    async with client as c:
        r = await c.get("/api/users/user-b/sessions/shared-session/messages")
    assert r.json() == []

    await session.clear_session()
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens
uv run pytest tests/test_chat_history.py -v 2>&1 | head -30
```

Expected: 404 errors — endpoint doesn't exist yet.

**Step 3: Add the conversion helper and endpoint to `server.py`**

Add the conversion helper after `_delete_session` (around line 135):

```python
def _items_to_display_messages(items: list) -> list[dict]:
    """Convert TResponseInputItem objects to frontend-displayable message dicts."""
    messages = []
    pending_tool_calls: list[dict] = []

    for item in items:
        # Items may be Pydantic models or plain dicts — normalise to dict.
        if hasattr(item, "model_dump"):
            item = item.model_dump()

        item_type = item.get("type", "")

        if item_type == "message":
            role = item.get("role", "")
            content = item.get("content", "")

            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(
                    part.get("text", "")
                    for part in content
                    if part.get("type") in ("text", "input_text", "output_text")
                )
            else:
                text = ""

            if not text:
                continue

            if role == "user":
                messages.append({"role": "user", "content": text, "toolCalls": []})
                pending_tool_calls = []
            elif role in ("assistant", "agent"):
                messages.append({
                    "role": "agent",
                    "content": text,
                    "toolCalls": pending_tool_calls,
                })
                pending_tool_calls = []

        elif item_type == "function_call":
            name = item.get("name", "")
            if name:
                pending_tool_calls.append({"tool": name, "status": "done"})
        # function_call_output and other internal items are skipped

    return messages
```

Add the endpoint after the `delete_session` endpoint:

```python
@app.get("/api/users/{user_id}/sessions/{session_id}/messages")
async def get_chat_history(user_id: str, session_id: str):
    """Return the full chat history for a session in display format."""
    session = await get_chat_session(user_id, session_id)
    items = await session.get_items()
    return _items_to_display_messages(items)
```

**Step 4: Run tests to verify they pass**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens
uv run pytest tests/test_chat_history.py -v
```

Expected: All 4 tests PASS.

Note: if `session.add_items()` is not the correct API for the SDK version installed, check the `SQLAlchemySession` source in `.venv/lib/python3.13/site-packages/agents/extensions/memory.py` for the actual method name. The data writing method may be named differently; adjust tests accordingly. The `get_items()` method is confirmed to exist.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add persona_lens/api/server.py tests/test_chat_history.py
git commit -m "feat: add chat history endpoint, convert agent_messages to display format"
```

---

### Task 2: Frontend — `useChat` loads history on mount

**Files:**
- Modify: `frontend/hooks/use-chat.ts`

**Context:** Currently `useChat` initialises state with a single `WELCOME` system message and never fetches history. After this task, it fetches `GET /api/users/{userId}/sessions/{sessionId}/messages` when `sessionId` changes, and pre-populates messages if any exist.

The endpoint returns `[{role, content, toolCalls}]` where:
- `role` is `"user"` or `"agent"`
- `toolCalls` is `[{tool: string, status: "done"}]`

The `ChatMessage` type in `frontend/lib/types.ts` is:
```typescript
interface ChatMessage {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  isStreaming: boolean;
  toolCalls: ToolCallInfo[];
  error?: { error: string; fix: string };
}
```

**Step 1: Add `useEffect` import and history-loading logic**

In `frontend/hooks/use-chat.ts`:

1. Add `useEffect` to the React import line:
```typescript
import { useState, useCallback, useEffect } from "react";
```

2. Add a history-loading `useEffect` inside the `useChat` function, after the `useState` call and before the `sendMessage` callback:

```typescript
  // Load existing chat history from backend when session changes
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;

    async function loadHistory() {
      try {
        const res = await fetch(
          `${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(sessionId)}/messages`
        );
        if (!res.ok || cancelled) return;
        const items: Array<{ role: string; content: string; toolCalls: Array<{ tool: string; status: "done" }> }> =
          await res.json();
        if (cancelled || items.length === 0) return;

        const history: ChatMessage[] = items.map((item) => ({
          id: makeId(),
          role: item.role as ChatMessage["role"],
          content: item.content,
          isStreaming: false,
          toolCalls: item.toolCalls,
        }));

        setState({ messages: history, isStreaming: false });
      } catch {
        // Backend not reachable — keep welcome message
      }
    }

    loadHistory();
    return () => { cancelled = true; };
  }, [sessionId, userId]);
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit 2>&1
```

Expected: No errors.

**Step 3: Commit**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens
git add frontend/hooks/use-chat.ts
git commit -m "feat: useChat loads chat history from backend on mount/session-switch"
```
