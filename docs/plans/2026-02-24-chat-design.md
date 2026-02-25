# Chat Feature Design Document

**Date**: 2026-02-24
**Status**: Draft

---

## Overview

Add a chat panel alongside the existing analysis panel. Users can interact with the existing Python Agent (OpenAI Agents SDK) through a conversational interface. Analysis results triggered via chat automatically update the left-side visualization panel.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Next.js Frontend                          │
│  Left panel (60%)              Right panel (40%)             │
│  Analysis visualization        Chat interface                │
│  (existing components)         Message history + input       │
└──────────┬─────────────────────────────┬─────────────────────┘
           │ SSE (existing)              │ POST /api/chat (new)
           ▼                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                           │
│  POST /api/analyze/{username}   (existing)                   │
│  POST /api/chat                 (new)                        │
│    └─→ get_context(session_id)                               │
│    └─→ OpenAI Agents SDK Runner (streaming)                  │
│         Main Agent → KOL Agent                              │
│         (fetch_user + analyze_user tools)                    │
└──────────────────────────────────────────────────────────────┘
```

---

## Session State Management

### Current phase (single user)

A single global `AgentContext` is used for all requests. The `session_id` field is accepted but ignored.

```python
_GLOBAL_CTX = AgentContext(profile_cache={}, analysis_cache={})

def get_context(session_id: str) -> AgentContext:
    return _GLOBAL_CTX
```

### Future migration path (multi-tenant)

Only `get_context` needs to change. The chat endpoint itself stays the same.

```python
_SESSIONS: dict[str, AgentContext] = {}

def get_context(session_id: str) -> AgentContext:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = AgentContext(profile_cache={}, analysis_cache={})
    return _SESSIONS[session_id]
```

The frontend generates a UUID on first load and stores it in `localStorage`. It sends this `session_id` on every chat request.

---

## API

### POST /api/chat

**Request body:**

```json
{
  "message": "analyze @karpathy",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**SSE response stream:**

| Event | Data | Purpose |
|-------|------|---------|
| `token` | `{"delta": "..."}` | Streaming Agent text output |
| `tool_call` | `{"tool": "fetch_user", "args": {...}, "status": "running"}` | Show Agent tool activity |
| `analysis_result` | `{user_info, tweets, patterns, analysis}` | Update left panel when analysis completes |
| `error` | `{"error": "...", "fix": "..."}` | Error with actionable fix |
| `done` | `{}` | Stream complete |

**Implementation sketch:**

```python
@app.post("/api/chat")
async def chat(req: ChatRequest):
    ctx = get_context(req.session_id)

    async def _generate():
        async for event in Runner.run_streamed(main_agent, req.message, context=ctx):
            if event.type == "text_delta":
                yield {"event": "token", "data": json.dumps({"delta": event.delta})}
            elif event.type == "tool_call":
                yield {"event": "tool_call", "data": json.dumps({
                    "tool": event.tool_name,
                    "status": "running"
                })}
                # After analyze_user completes, emit structured result
                if event.tool_name == "analyze_user" and event.output:
                    username = event.tool_args.get("username", "")
                    cached = ctx.profile_cache.get("x", {}).get(username)
                    if cached:
                        yield {"event": "analysis_result", "data": json.dumps({
                            "user_info": cached["user_info"],
                            "tweets": cached["tweets"],
                            "patterns": cached["patterns"],
                            "analysis": ctx.analysis_cache.get("x", {}).get(username, {}),
                        }, ensure_ascii=False)}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(_generate())
```

---

## Frontend Layout

### Desktop (≥768px): side-by-side

```
┌──────────────────────────────────────────────────────────────┐
│  Persona Lens                                                │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─── Analysis Panel (60%) ───┐  ┌── Chat (40%) ───────────┐ │
│  │  [search bar]              │  │  System                 │ │
│  │                            │  │  "Hi! Analyze a user    │ │
│  │  (empty / loading / result)│  │   or ask me anything…" │ │
│  │                            │  │                         │ │
│  │  Profile Card              │  │  User                   │ │
│  │  Products                  │  │  "analyze @karpathy"    │ │
│  │  Writing Style             │  │                         │ │
│  │  Heatmap                   │  │  Agent                  │ │
│  │  Top Posts                 │  │  "→ Fetching…           │ │
│  │  Tweets                    │  │   → Analyzing…          │ │
│  │                            │  │   Here's what I found:  │ │
│  │                            │  │   ..."  [streaming]     │ │
│  │                            │  │                         │ │
│  │                            │  ├─────────────────────────┤ │
│  │                            │  │ [message input…] [Send] │ │
│  └────────────────────────────┘  └─────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Mobile (<768px): tab switching

```
[Results] [Chat]  ← tabs
─────────────────
(active tab content)
```

---

## Frontend Components

### New components

| Component | File | Description |
|-----------|------|-------------|
| `ChatPanel` | `components/chat-panel.tsx` | Full chat panel: message list + input bar |
| `ChatMessage` | `components/chat-message.tsx` | Single message bubble (user/agent/system) |
| `ToolCallIndicator` | `components/tool-call-indicator.tsx` | Shows "→ Fetching @karpathy…" during tool calls |

### New hook

| Hook | File | Description |
|------|------|-------------|
| `useChat` | `hooks/use-chat.ts` | SSE connection, message history state, session_id management |

### Modified files

| File | Change |
|------|--------|
| `app/page.tsx` | Restructure layout to left/right panels; add mobile tab switching |
| `persona_lens/api/server.py` | Add `POST /api/chat` endpoint + `get_context()` |

---

## State Management

### Chat message types

```typescript
interface Message {
  id: string;
  role: "user" | "agent" | "system";
  content: string;        // accumulated text
  isStreaming: boolean;   // true while receiving tokens
  toolCalls?: ToolCall[];
}

interface ToolCall {
  tool: string;
  status: "running" | "done";
}
```

### useChat hook responsibilities

1. Generate and persist `session_id` in `localStorage`
2. Maintain `messages: Message[]`
3. On `sendMessage(text)`: append user message, open SSE to `/api/chat`
4. On `token` event: accumulate `delta` into last agent message
5. On `analysis_result` event: call `onAnalysisResult(result)` callback → updates left panel
6. On `done`/`error`: finalize streaming state

---

## Error Handling

- Camofox not running → `error` SSE event with fix instruction
- API key missing → `error` SSE event
- Network error mid-stream → mark last message as error, show retry option

---

## Web Interface Guidelines Compliance

- Chat input: `<label>` (sr-only), `spellCheck={false}`, `autocomplete="off"`
- Send button: `<button>` with `aria-label`
- Streaming text: `aria-live="polite"` on agent message container
- Tool call indicators: end with `…` (not `...`)
- No `outline-none` without `focus-visible` replacement
- `touch-action: manipulation` on send button
- Mobile tabs: proper `role="tablist"` + `role="tab"` + `aria-selected`
