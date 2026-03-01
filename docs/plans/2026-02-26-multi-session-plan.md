# Multi-Session Chat Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to create, switch, and delete independent chat sessions, each with isolated conversation history and analysis results.

**Architecture:** Frontend manages session lifecycle (create/switch/delete) via a `useSessionManager` hook, persisting the session list to localStorage. Backend isolates `AgentContext` and `SQLAlchemySession` per `session_id` using in-memory dicts keyed by the session ID already present in API requests.

**Tech Stack:** Python/FastAPI (backend), React/Next.js 16, Radix UI Select, localStorage

---

### Task 1: Backend — per-session context and chat isolation

**Files:**
- Modify: `persona_lens/api/server.py`
- Test: `tests/test_api_sessions.py`

**Step 1: Write the failing test**

Create `tests/test_api_sessions.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run pytest tests/test_api_sessions.py -v`
Expected: ImportError or AttributeError since `_contexts` doesn't exist yet.

**Step 3: Implement backend changes**

In `persona_lens/api/server.py`:

1. Remove `_global_ctx = AgentContext()` and `_chat_session: SQLAlchemySession | None = None`
2. Add:
```python
_contexts: dict[str, AgentContext] = {}
_chat_sessions: dict[str, SQLAlchemySession] = {}
```
3. Replace `get_context`:
```python
def get_context(session_id: str) -> AgentContext:
    if session_id not in _contexts:
        _contexts[session_id] = AgentContext()
    return _contexts[session_id]
```
4. Replace `get_chat_session`:
```python
async def get_chat_session(session_id: str) -> SQLAlchemySession:
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = SQLAlchemySession(
            session_id, engine=_engine, create_tables=True
        )
    return _chat_sessions[session_id]
```
5. In the `analyze` endpoint, add `session_id: str = "default"` query param. Replace all references to `_global_ctx` with `get_context(session_id)`:
```python
@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30, session_id: str = "default"):
```
Inside `_generate()`, replace `_global_ctx` with:
```python
ctx = get_context(session_id)
```
And use `ctx.profile_cache` / `ctx.analysis_cache` instead of `_global_ctx.profile_cache` / `_global_ctx.analysis_cache`.

6. In the `chat` endpoint, pass `req.session_id` to `get_chat_session`:
```python
session = await get_chat_session(req.session_id)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run pytest tests/test_api_sessions.py -v`
Expected: All 3 tests PASS.

**Step 5: Run existing tests to verify no regressions**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run pytest tests/ -v`
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add persona_lens/api/server.py tests/test_api_sessions.py
git commit -m "feat: isolate AgentContext and SQLAlchemySession per session_id"
```

---

### Task 2: Frontend — `useSessionManager` hook

**Files:**
- Create: `frontend/hooks/use-session-manager.ts`

**Step 1: Create the hook**

```typescript
// frontend/hooks/use-session-manager.ts
"use client";

import { useState, useCallback, useEffect } from "react";

export interface Session {
  id: string;
  title: string;
  createdAt: number;
}

interface SessionManagerState {
  sessions: Session[];
  activeSessionId: string;
}

const STORAGE_KEY = "persona-lens-sessions";

function makeSession(index: number): Session {
  return {
    id: crypto.randomUUID(),
    title: `Chat ${index}`,
    createdAt: Date.now(),
  };
}

function loadState(): SessionManagerState {
  if (typeof window === "undefined") {
    const s = makeSession(1);
    return { sessions: [s], activeSessionId: s.id };
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as SessionManagerState;
      if (parsed.sessions.length > 0) return parsed;
    }
  } catch { /* ignore */ }
  const s = makeSession(1);
  return { sessions: [s], activeSessionId: s.id };
}

function saveState(state: SessionManagerState) {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }
}

export function useSessionManager() {
  const [state, setState] = useState<SessionManagerState>(loadState);

  // Persist on every change
  useEffect(() => {
    saveState(state);
  }, [state]);

  const createSession = useCallback(() => {
    setState((prev) => {
      const newSession = makeSession(prev.sessions.length + 1);
      return {
        sessions: [...prev.sessions, newSession],
        activeSessionId: newSession.id,
      };
    });
  }, []);

  const switchSession = useCallback((id: string) => {
    setState((prev) => ({ ...prev, activeSessionId: id }));
  }, []);

  const deleteSession = useCallback((id: string) => {
    setState((prev) => {
      const remaining = prev.sessions.filter((s) => s.id !== id);
      if (remaining.length === 0) {
        const fresh = makeSession(1);
        return { sessions: [fresh], activeSessionId: fresh.id };
      }
      const activeId =
        prev.activeSessionId === id ? remaining[remaining.length - 1].id : prev.activeSessionId;
      return { sessions: remaining, activeSessionId: activeId };
    });
  }, []);

  const renameSession = useCallback((id: string, title: string) => {
    setState((prev) => ({
      ...prev,
      sessions: prev.sessions.map((s) =>
        s.id === id ? { ...s, title: title.slice(0, 30) } : s
      ),
    }));
  }, []);

  const activeSession = state.sessions.find((s) => s.id === state.activeSessionId)!;

  return {
    sessions: state.sessions,
    activeSession,
    activeSessionId: state.activeSessionId,
    createSession,
    switchSession,
    deleteSession,
    renameSession,
  };
}
```

**Step 2: Verify no build errors**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add frontend/hooks/use-session-manager.ts
git commit -m "feat: add useSessionManager hook with localStorage persistence"
```

---

### Task 3: Frontend — make `useChat` session-aware

**Files:**
- Modify: `frontend/hooks/use-chat.ts`

**Step 1: Update `useChat` to accept `sessionId` prop**

Changes to `frontend/hooks/use-chat.ts`:

1. Remove `getOrCreateSessionId()` function entirely.
2. Change the hook signature to accept `sessionId`:
```typescript
interface UseChatOptions {
  sessionId: string;
  onAnalysisResult?: (result: AnalysisResult) => void;
}

export function useChat({ sessionId, onAnalysisResult }: UseChatOptions) {
```
3. Remove the `sessionIdRef` and its `useEffect`. Instead, use `sessionId` directly in `sendMessage`:
```typescript
body: JSON.stringify({
  message: text,
  session_id: sessionId,
}),
```
4. Add `sessionId` to the `useCallback` dependency array for `sendMessage`.

**Step 2: Verify no build errors**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit`
Expected: Type errors in `chat-panel.tsx` (expected — will fix in Task 5).

**Step 3: Commit**

```bash
git add frontend/hooks/use-chat.ts
git commit -m "feat: make useChat accept sessionId prop instead of using localStorage"
```

---

### Task 4: Frontend — make `useAnalysis` session-aware

**Files:**
- Modify: `frontend/hooks/use-analysis.ts`

**Step 1: Update `useAnalysis` to accept and pass `sessionId`**

Changes to `frontend/hooks/use-analysis.ts`:

1. Add `sessionId` parameter:
```typescript
export function useAnalysis(sessionId: string) {
```
2. Append `session_id` to the fetch URL:
```typescript
const res = await fetch(
  `${API_BASE}/api/analyze/${encodeURIComponent(username)}?tweets=${tweets}&session_id=${encodeURIComponent(sessionId)}`,
  { method: "POST" }
);
```
3. Add `sessionId` to the `useCallback` dependency array.

**Step 2: Verify no build errors**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit`
Expected: Type errors in `page.tsx` (expected — will fix in Task 5).

**Step 3: Commit**

```bash
git add frontend/hooks/use-analysis.ts
git commit -m "feat: pass session_id to /api/analyze endpoint"
```

---

### Task 5: Frontend — session switcher UI in ChatPanel

**Files:**
- Modify: `frontend/components/chat-panel.tsx`

**Step 1: Add session switcher header and accept new props**

Update `ChatPanelProps` and add the session switcher UI at the top of the chat panel:

```typescript
interface ChatPanelProps {
  sessionId: string;
  sessions: { id: string; title: string; createdAt: number }[];
  onNewSession: () => void;
  onSwitchSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onAnalysisResult?: (result: AnalysisResult) => void;
}
```

Inside `ChatPanel`, pass `sessionId` to `useChat`:
```typescript
const { state, sendMessage } = useChat({ sessionId, onAnalysisResult });
```

Add a session switcher bar above the message list:
```tsx
{/* Session switcher */}
<div className="flex items-center gap-2 p-2 border-b shrink-0">
  <Button
    variant="outline"
    size="sm"
    onClick={onNewSession}
    aria-label="New chat session"
    style={{ touchAction: "manipulation" }}
  >
    + New
  </Button>
  <Select value={sessionId} onValueChange={onSwitchSession}>
    <SelectTrigger size="sm" className="flex-1 min-w-0">
      <SelectValue />
    </SelectTrigger>
    <SelectContent position="popper" align="start">
      {sessions.map((s) => (
        <SelectItem key={s.id} value={s.id}>
          {s.title}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
  {sessions.length > 1 && (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => onDeleteSession(sessionId)}
      aria-label="Delete current session"
      style={{ touchAction: "manipulation" }}
    >
      <Trash2 className="size-4" />
    </Button>
  )}
</div>
```

Add the necessary imports at the top:
```typescript
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2 } from "lucide-react";
```

**Step 2: Verify no build errors**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit`
Expected: Errors in `page.tsx` for missing props (expected — will fix in Task 6).

**Step 3: Commit**

```bash
git add frontend/components/chat-panel.tsx
git commit -m "feat: add session switcher UI to chat panel header"
```

---

### Task 6: Frontend — wire everything together in `page.tsx`

**Files:**
- Modify: `frontend/app/page.tsx`

**Step 1: Integrate session manager and per-session state**

Key changes to `page.tsx`:

1. Import `useSessionManager`:
```typescript
import { useSessionManager } from "@/hooks/use-session-manager";
```

2. In `AnalysisPage`, add session manager and per-session profiles:
```typescript
const {
  sessions,
  activeSession,
  activeSessionId,
  createSession,
  switchSession,
  deleteSession,
  renameSession,
} = useSessionManager();

const { state, analyze } = useAnalysis(activeSessionId);

// Per-session analysis results: { [sessionId]: { [username]: AnalysisResult } }
const [profilesBySession, setProfilesBySession] = useState<Record<string, Record<string, AnalysisResult>>>({});
const [selectedBySession, setSelectedBySession] = useState<Record<string, string | null>>({});
```

3. Replace `analyzedProfiles` with session-scoped access:
```typescript
const analyzedProfiles = profilesBySession[activeSessionId] ?? {};
const selectedUsername = selectedBySession[activeSessionId] ?? null;
```

4. Update `setAnalyzedProfiles` calls to scope by session:
```typescript
// When analysis result arrives
useEffect(() => {
  if (result) {
    const username = result.user_info.username;
    setProfilesBySession(prev => ({
      ...prev,
      [activeSessionId]: { ...(prev[activeSessionId] ?? {}), [username]: result },
    }));
    setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }));
  }
}, [result, activeSessionId]);
```

5. Update `handleChatAnalysis`:
```typescript
const handleChatAnalysis = useCallback((chatResult: AnalysisResult) => {
  const username = chatResult.user_info.username;
  setProfilesBySession(prev => ({
    ...prev,
    [activeSessionId]: { ...(prev[activeSessionId] ?? {}), [username]: chatResult },
  }));
  setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }));
  setMobileTab("results");
}, [activeSessionId]);
```

6. Update `setSelectedUsername` to scope by session:
```typescript
onClick={() => setSelectedBySession(prev => ({ ...prev, [activeSessionId]: username }))}
```

7. Auto-rename session on first user message (via chat). In `handleChatAnalysis` or in a new callback, rename the session to the first analyzed user:
```typescript
// In handleChatAnalysis, after setProfilesBySession:
const currentProfiles = profilesBySession[activeSessionId] ?? {};
if (Object.keys(currentProfiles).length === 0) {
  renameSession(activeSessionId, `@${username}`);
}
```

8. Pass session props to `ChatPanel` (both desktop and mobile instances). Use `key={activeSessionId}` to force remount on session switch:
```tsx
<ChatPanel
  key={activeSessionId}
  sessionId={activeSessionId}
  sessions={sessions}
  onNewSession={createSession}
  onSwitchSession={switchSession}
  onDeleteSession={deleteSession}
  onAnalysisResult={handleChatAnalysis}
/>
```

9. Clean up: remove the old `useState<Record<string, AnalysisResult>>({})` and `useState<string | null>(null)` for `analyzedProfiles`/`selectedUsername`, since they are now derived from the `*BySession` states.

**Step 2: Verify build succeeds**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npx tsc --noEmit`
Expected: No errors.

**Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: wire multi-session state into page with per-session profile isolation"
```

---

### Task 7: Manual smoke test

**Step 1: Start backend**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run uvicorn persona_lens.api.server:app --port 8000`

**Step 2: Start frontend**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens/frontend && npm run dev`

**Step 3: Verify multi-session behavior**

1. Open http://localhost:3000
2. Default "Chat 1" session should be active
3. Type a message in chat — verify it sends with `session_id`
4. Click "+ New" — verify new "Chat 2" session appears and is active
5. Switch back to "Chat 1" via dropdown — verify left panel shows Chat 1's data (empty or with profiles)
6. Analyze a user in Chat 1 — verify profile appears only in Chat 1's context
7. Switch to Chat 2, analyze a different user — verify profiles are isolated
8. Delete a session — verify it's removed and another becomes active
9. Refresh page — verify session list persists (chat history does not — expected)

**Step 4: Run all backend tests**

Run: `cd /Users/zhangjinjia/code/memodb-io/persona-lens && uv run pytest tests/ -v`
Expected: All tests PASS.

**Step 5: Final commit if any fixups needed**

```bash
git add -A
git commit -m "fix: address smoke test findings"
```
