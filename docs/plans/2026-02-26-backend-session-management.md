# Backend Session Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move session metadata (list, titles, created_at) from browser localStorage to a persistent SQLite backend so sessions survive server restarts, browser clears, and future multi-tenant use.

**Architecture:** Add a `sessions` table to `persona_lens.db` with `(user_id, session_id, title, created_at)` as primary key. Expose four REST endpoints for session CRUD. Replace the `useSessionManager` hook's localStorage logic with async API calls; keep `activeSessionId` in localStorage as a lightweight UI pointer only.

**Tech Stack:** Python/FastAPI + aiosqlite (backend), React/Next.js hooks (frontend), existing `DB_PATH` SQLite file.

---

### Task 1: Backend — `sessions` table + CRUD endpoints

**Files:**
- Modify: `persona_lens/api/server.py`
- Test: `tests/test_session_crud.py`

**Step 1: Write the failing tests**

Create `tests/test_session_crud.py`:

```python
"""Tests for session CRUD endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from persona_lens.api.server import app, DB_PATH
import aiosqlite
import os

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def clean_sessions():
    """Wipe sessions table before each test."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sessions")
        await db.commit()
    yield


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_sessions_empty(client):
    async with client as c:
        r = await c.get("/api/users/default/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_session(client):
    async with client as c:
        r = await c.post(
            "/api/users/default/sessions",
            json={"session_id": "s1", "title": "Chat 1"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "s1"
    assert data["title"] == "Chat 1"
    assert "created_at" in data


async def test_list_sessions_returns_created(client):
    async with client as c:
        await c.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
        r = await c.get("/api/users/default/sessions")
    assert len(r.json()) == 1
    assert r.json()[0]["session_id"] == "s1"


async def test_rename_session(client):
    async with client as c:
        await c.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
        r = await c.patch("/api/users/default/sessions/s1", json={"title": "@karpathy"})
    assert r.status_code == 200
    assert r.json()["title"] == "@karpathy"


async def test_delete_session(client):
    async with client as c:
        await c.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
        r = await c.delete("/api/users/default/sessions/s1")
    assert r.status_code == 200
    async with client as c:
        sessions = (await c.get("/api/users/default/sessions")).json()
    assert sessions == []


async def test_delete_session_also_removes_profiles(client):
    """Deleting a session should cascade-delete its profile_results rows."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO profile_results (user_id, session_id, username, result_json) VALUES (?, ?, ?, ?)",
            ("default", "s1", "karpathy", "{}"),
        )
        await db.commit()
    async with client as c:
        await c.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
        await c.delete("/api/users/default/sessions/s1")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM profile_results WHERE session_id = ?", ("s1",)
        ) as cur:
            count = (await cur.fetchone())[0]
    assert count == 0


async def test_sessions_isolated_across_users(client):
    async with client as c:
        await c.post("/api/users/user-a/sessions", json={"session_id": "s1", "title": "A"})
        r = await c.get("/api/users/user-b/sessions")
    assert r.json() == []
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens
uv run pytest tests/test_session_crud.py -v 2>&1 | head -30
```
Expected: ImportError or 404 errors — endpoints don't exist yet.

**Step 3: Add `sessions` table and CRUD endpoints to `server.py`**

In `_create_tables()`, add after the `profile_results` CREATE:

```python
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id    TEXT NOT NULL DEFAULT 'default',
                session_id TEXT NOT NULL,
                title      TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, session_id)
            )
        """)
```

Add DB helpers after `_load_profiles`:

```python
async def _create_session(user_id: str, session_id: str, title: str, created_at: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sessions (user_id, session_id, title, created_at) VALUES (?, ?, ?, ?)",
            (user_id, session_id, title, created_at),
        )
        await db.commit()
    return {"user_id": user_id, "session_id": session_id, "title": title, "created_at": created_at}


async def _list_sessions(user_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT session_id, title, created_at FROM sessions WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"session_id": r[0], "title": r[1], "created_at": r[2]} for r in rows]


async def _rename_session(user_id: str, session_id: str, title: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET title = ? WHERE user_id = ? AND session_id = ?",
            (title, user_id, session_id),
        )
        await db.commit()
        async with db.execute(
            "SELECT session_id, title, created_at FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    return {"session_id": row[0], "title": row[1], "created_at": row[2]}


async def _delete_session(user_id: str, session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        await db.execute(
            "DELETE FROM profile_results WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        await db.commit()
```

Add Pydantic models and endpoints (place before `@app.get("/api/health")`):

```python
class CreateSessionRequest(BaseModel):
    session_id: str
    title: str


class RenameSessionRequest(BaseModel):
    title: str


@app.get("/api/users/{user_id}/sessions")
async def list_sessions(user_id: str):
    """List all sessions for a user, ordered by creation time."""
    return await _list_sessions(user_id)


@app.post("/api/users/{user_id}/sessions")
async def create_session(user_id: str, req: CreateSessionRequest):
    """Create a new session. Idempotent — ignores duplicate session_id."""
    import time
    return await _create_session(user_id, req.session_id, req.title, int(time.time() * 1000))


@app.patch("/api/users/{user_id}/sessions/{session_id}")
async def rename_session(user_id: str, session_id: str, req: RenameSessionRequest):
    """Rename an existing session."""
    result = await _rename_session(user_id, session_id, req.title)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@app.delete("/api/users/{user_id}/sessions/{session_id}")
async def delete_session(user_id: str, session_id: str):
    """Delete a session and all its stored profiles."""
    await _delete_session(user_id, session_id)
    return {"deleted": session_id}
```

Also add `allow_methods=["GET", "POST", "PATCH", "DELETE"]` to the CORSMiddleware.

**Step 4: Run tests to verify they pass**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens
uv run pytest tests/test_session_crud.py -v
```
Expected: All 7 tests PASS.

**Step 5: Run full test suite**

```bash
uv run pytest tests/ -v 2>&1 | tail -10
```
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add persona_lens/api/server.py tests/test_session_crud.py
git commit -m "feat: add sessions table and CRUD endpoints (user_id scoped)"
```

---

### Task 2: Frontend — `useSessionManager` fetches from backend

**Files:**
- Modify: `frontend/hooks/use-session-manager.ts`

**Context:** Currently `useSessionManager` stores the full session list + `activeSessionId` in a single localStorage JSON blob. After this task, session list comes from the backend; only `activeSessionId` stays in localStorage as a lightweight UI pointer.

**Step 1: Rewrite `use-session-manager.ts`**

Replace the entire file content with:

```typescript
// frontend/hooks/use-session-manager.ts
"use client";

import { useState, useCallback, useEffect } from "react";

export interface Session {
  session_id: string;
  title: string;
  created_at: number;
}

const API_BASE = "http://localhost:8000";
const ACTIVE_KEY = "persona-lens-active-session";
const DEFAULT_USER = "default";

function loadActiveId(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(ACTIVE_KEY) ?? "";
}

function saveActiveId(id: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(ACTIVE_KEY, id);
  }
}

export function useSessionManager(userId: string = DEFAULT_USER) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);

  // Fetch sessions from backend on mount
  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`);
        if (!res.ok) throw new Error("Failed to fetch sessions");
        const data: Session[] = await res.json();

        if (data.length === 0) {
          // No sessions yet — create an initial one
          const id = crypto.randomUUID();
          const created = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: id, title: "Chat 1" }),
          }).then((r) => r.json()) as Session;
          setSessions([created]);
          setActiveSessionId(id);
          saveActiveId(id);
        } else {
          setSessions(data);
          const saved = loadActiveId();
          const validId = data.find((s) => s.session_id === saved)?.session_id ?? data[data.length - 1].session_id;
          setActiveSessionId(validId);
          saveActiveId(validId);
        }
      } catch {
        // Backend not running — fall back to a synthetic local session
        const id = loadActiveId() || crypto.randomUUID();
        setSessions([{ session_id: id, title: "Chat 1", created_at: Date.now() }]);
        setActiveSessionId(id);
        saveActiveId(id);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [userId]);

  const createSession = useCallback(async () => {
    const id = crypto.randomUUID();
    const title = `Chat ${sessions.length + 1}`;
    try {
      const created = await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: id, title }),
      }).then((r) => r.json()) as Session;
      setSessions((prev) => [...prev, created]);
      setActiveSessionId(id);
      saveActiveId(id);
    } catch {
      // Optimistic local fallback
      const s: Session = { session_id: id, title, created_at: Date.now() };
      setSessions((prev) => [...prev, s]);
      setActiveSessionId(id);
      saveActiveId(id);
    }
  }, [sessions.length, userId]);

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id);
    saveActiveId(id);
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    try {
      await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
    } catch { /* ignore — delete optimistically */ }

    setSessions((prev) => {
      const remaining = prev.filter((s) => s.session_id !== id);
      if (remaining.length === 0) {
        // Will trigger a new session creation on next render via the useEffect
        return [];
      }
      setActiveSessionId((cur) => {
        if (cur === id) {
          const next = remaining[remaining.length - 1].session_id;
          saveActiveId(next);
          return next;
        }
        return cur;
      });
      return remaining;
    });
  }, [userId]);

  const renameSession = useCallback(async (id: string, title: string) => {
    const trimmed = title.slice(0, 30);
    try {
      await fetch(`${API_BASE}/api/users/${encodeURIComponent(userId)}/sessions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      });
    } catch { /* ignore */ }
    setSessions((prev) =>
      prev.map((s) => (s.session_id === id ? { ...s, title: trimmed } : s))
    );
  }, [userId]);

  const activeSession = sessions.find((s) => s.session_id === activeSessionId) ?? sessions[0];

  return {
    sessions,
    activeSession,
    activeSessionId,
    isLoading,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  };
}
```

**Step 2: Verify TypeScript compiles**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit 2>&1
```
Expected: Errors in `page.tsx` and `chat-panel.tsx` because `Session.id` → `Session.session_id` changed. Those are fixed in Task 3.

**Step 3: Commit**

```bash
git add frontend/hooks/use-session-manager.ts
git commit -m "feat: useSessionManager fetches from backend, localStorage only stores activeSessionId"
```

---

### Task 3: Frontend — update callers for `session_id` field rename

**Files:**
- Modify: `frontend/app/page.tsx`
- Modify: `frontend/components/chat-panel.tsx`

**Context:** `Session` used to have `.id`; now it has `.session_id`. Update all callers.

**Step 1: Update `chat-panel.tsx`**

The `sessions` prop type in `ChatPanelProps` currently is `{ id: string; title: string; createdAt: number }[]`. Update it to match the new `Session` shape:

```typescript
import type { Session } from "@/hooks/use-session-manager";

interface ChatPanelProps {
  sessionId: string;
  sessions: Session[];
  onNewSession: () => void;
  onSwitchSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onAnalysisResult?: (result: AnalysisResult) => void;
}
```

In the JSX, update the `<Select>` and `<SelectItem>` to use `s.session_id` instead of `s.id`:

```tsx
<Select value={sessionId} onValueChange={onSwitchSession}>
  <SelectTrigger size="sm" className="flex-1 min-w-0">
    <SelectValue />
  </SelectTrigger>
  <SelectContent position="popper" align="start">
    {sessions.map((s) => (
      <SelectItem key={s.session_id} value={s.session_id}>
        {s.title}
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

**Step 2: Update `page.tsx`**

`useSessionManager` now returns `isLoading`. Add it to the destructure:

```typescript
const {
  sessions,
  activeSession,
  activeSessionId,
  isLoading: sessionsLoading,
  createSession,
  switchSession,
  deleteSession,
  renameSession,
} = useSessionManager();
```

While `sessionsLoading` is true and `activeSessionId` is empty, the chat panel and analysis would attempt to fetch with an empty session id — guard against this by only rendering the main content when ready:

In the JSX, wrap the `<main>` and mobile div contents to show nothing meaningful while loading:

```tsx
{/* show a simple loading state until sessions are fetched */}
{sessionsLoading ? (
  <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
    Loading…
  </div>
) : (
  <>
    {/* ── Desktop ── */}
    <main ...> ... </main>
    {/* ── Mobile ── */}
    <div className="md:hidden ..."> ... </div>
  </>
)}
```

**Step 3: Verify TypeScript compiles cleanly**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit 2>&1
```
Expected: **No errors**.

**Step 4: Commit**

```bash
git add frontend/app/page.tsx frontend/components/chat-panel.tsx
git commit -m "feat: update page and ChatPanel for backend-managed sessions"
```

---

### Task 4: Remove old localStorage session key

**Files:**
- Modify: `frontend/hooks/use-session-manager.ts` (already done above — `STORAGE_KEY` is gone)

This task is a verification step. After Task 2, the old `"persona-lens-sessions"` localStorage key is no longer written. Confirm it:

**Step 1: Confirm `STORAGE_KEY` is not in the codebase**

```bash
grep -r "persona-lens-sessions" /Users/zhangjinjia/code/memodb-io/persona-lens/frontend/
```
Expected: No output.

**Step 2: Run full backend tests**

```bash
cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run pytest tests/ -v 2>&1 | tail -10
```
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: verify old localStorage session key is removed"
```
(Only commit if there are actual unstaged changes; skip otherwise.)
