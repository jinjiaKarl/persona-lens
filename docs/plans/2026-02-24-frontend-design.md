# Frontend Design Document

**Date**: 2026-02-24
**Status**: Draft

---

## Overview

Add a web frontend to persona-lens that visualizes KOL analysis results. The frontend replaces terminal text output with an interactive single-page analysis panel.

**Stack**: Next.js + React + shadcn/ui + Tailwind CSS + FastAPI backend

---

## Architecture

```
┌──────────────────────────────────────────────┐
│         Next.js Frontend (port 3000)          │
│  Search bar → fetch /api/analyze/{username}   │
│  SSE stream ← progress + final results       │
└─────────────────────┬────────────────────────┘
                      │ HTTP
┌─────────────────────▼────────────────────────┐
│         FastAPI Backend (port 8000)            │
│  POST /api/analyze/{username}?tweets=30       │
│  GET  /api/health                             │
│                                               │
│  Imports persona_lens modules directly:       │
│  fetch_snapshot → parse → patterns → analyze  │
└───────────────────────────────────────────────┘
```

### Key Decisions

- FastAPI imports `persona_lens` Python modules directly (no subprocess)
- SSE (Server-Sent Events) pushes progress states: fetching → parsing → analyzing → done
- Frontend calls one endpoint per analysis; results streamed incrementally
- URL reflects state: `?user=karpathy&tweets=50` for shareable links

---

## FastAPI Backend

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Readiness check (Camofox reachable, API key set) |
| `POST` | `/api/analyze/{username}` | Analyze a user, returns SSE stream |

### POST /api/analyze/{username}

**Query params**: `tweets` (int, default 30)

**SSE events**:

```
event: progress
data: {"stage": "fetching", "message": "Fetching tweets…"}

event: progress
data: {"stage": "parsing", "message": "Parsing 45 tweets…"}

event: progress
data: {"stage": "analyzing", "message": "Running AI analysis…"}

event: result
data: {
  "user_info": { "username", "display_name", "bio", "followers", "following", "tweets_count" },
  "tweets": [ { "id", "text", "timestamp_ms", "likes", "retweets", "replies", "views", "media", "has_media" } ],
  "patterns": { "peak_days": {...}, "peak_hours": {...} },
  "analysis": { "products": [...], "writing_style": "...", "engagement": { "insights": "...", "top_posts": [...] } }
}

event: error
data: {"error": "Camofox Browser is not running", "fix": "Start it with: npm start in camofox-browser/"}
```

### Implementation

New file `persona_lens/api/server.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], ...)

@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30):
    async def event_generator():
        yield {"event": "progress", "data": json.dumps({"stage": "fetching", ...})}
        # call fetch_snapshot, extract_tweet_data, extract_user_info, compute_posting_patterns
        yield {"event": "progress", "data": json.dumps({"stage": "analyzing", ...})}
        # call analyze_user_profile
        yield {"event": "result", "data": json.dumps(full_result)}
    return EventSourceResponse(event_generator())
```

---

## Frontend Page Layout

```
┌──────────────────────────────────────────────────────────┐
│  Persona Lens    [@username________]  [Analyze]  [30 ▼]  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌── Profile Card ────┐  ┌── Products ─────────────────┐ │
│  │ Display Name        │  │ [Cursor]  [Claude API]      │ │
│  │ @handle             │  │ [Notion]  [Arc Browser]     │ │
│  │ Bio text…           │  │                             │ │
│  │ 12.3K followers     │  │ AI-Coding (3)               │ │
│  │ 500 following       │  │ SaaS (2)                    │ │
│  │ 8,523 tweets        │  │ Hardware (1)                │ │
│  └─────────────────────┘  └─────────────────────────────┘ │
│                                                          │
│  ┌── Writing Style ───┐  ┌── Posting Heatmap ──────────┐ │
│  │ "Uses short,        │  │  Mon ████████               │ │
│  │  punchy sentences.  │  │  Tue ████                   │ │
│  │  Heavy emoji usage  │  │  Wed ██████                 │ │
│  │  …"                 │  │  …                          │ │
│  └─────────────────────┘  │  Peak: Mon, 08-12 UTC       │ │
│                           └─────────────────────────────┘ │
│                                                          │
│  ┌── Top Posts & Engagement ────────────────────────────┐ │
│  │ "Thread-style posts drive 3x more engagement…"       │ │
│  │ ┌──────────────────┬────────┬───────┬───────┐        │ │
│  │ │ Tweet            │ Likes  │ RTs   │ Views │        │ │
│  │ ├──────────────────┼────────┼───────┼───────┤        │ │
│  │ │ "Just shipped…"  │ 2,345  │  450  │ 89.1K │        │ │
│  │ │ "Hot take: AI…"  │ 1,823  │  320  │ 67.4K │        │ │
│  │ └──────────────────┴────────┴───────┴───────┘        │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌── All Tweets (collapsible) ─────────────────────────┐ │
│  │ [All ▼]  [Sort: Time ▼]  [Export JSON]  [Export CSV] │ │
│  │ Tweet 1…                                             │ │
│  │ Tweet 2…                                             │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### Components

| Component | Data Source | Description |
|-----------|------------|-------------|
| **SearchBar** | User input | Username input + tweet count selector + analyze button |
| **ProgressIndicator** | SSE stream | Step-by-step progress with spinner |
| **ProfileCard** | `user_info` | Display name, bio, follower/following counts |
| **ProductTags** | `analysis.products` | Tag cloud grouped by category |
| **WritingStyle** | `analysis.writing_style` | Prose card |
| **PostingHeatmap** | `patterns` | Bar chart by day-of-week + hour slots |
| **TopPosts** | `analysis.engagement` | Insights text + sortable table |
| **TweetList** | `tweets` | Collapsible list with sort/filter, virtualized if >50 |
| **ErrorPanel** | SSE error event | Error message with actionable fix suggestion |
| **EmptyState** | No analysis yet | Welcome message with usage instructions |

---

## UI States

### 1. Empty State (initial load)

Welcome message: "Enter an X/Twitter username to analyze their profile, products, and engagement patterns."

### 2. Loading State

Step-by-step progress indicator:
- ✓ Fetching tweets… (completed)
- ⟳ Running AI analysis… (in progress)
- ○ Done (pending)

### 3. Result State

Full layout as shown above.

### 4. Error State

Inline error panel with:
- What went wrong (specific message)
- How to fix it (actionable instruction)
- Retry button

---

## Web Interface Guidelines Compliance

Rules from [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines) applied to this design:

### Accessibility
- Search input: `<label>` + `spellCheck={false}` (username field)
- Analyze button: semantic `<button>`, not `<div onClick>`
- Progress updates: `aria-live="polite"` region
- All icon buttons: `aria-label` required
- Hierarchical headings: `<h1>` page title → `<h2>` section titles

### Forms
- Submit button stays enabled until request starts; shows spinner during request
- Correct `autocomplete="off"` on username input
- Placeholder: `"e.g. karpathy…"` (ends with `…`)

### Typography
- Number columns (likes, retweets, views): `font-variant-numeric: tabular-nums`
- Headings: `text-wrap: balance`
- Loading text ends with `…` (not `...`)
- Curly quotes in prose content

### Content Handling
- Tweet text: `line-clamp-3` with expand option
- Bio text: handle empty/long content gracefully
- Empty states: dedicated UI, not broken/blank page
- Long usernames: truncate with `…`

### Performance
- Tweet list >50 items: virtualize (react-window or similar)
- Images: `loading="lazy"`, explicit `width`/`height`
- `<link rel="preconnect">` for API endpoint

### Navigation & State
- URL reflects analysis state: `?user=karpathy&tweets=50`
- Shareable deep links
- Export buttons for data (JSON/CSV)

### Numbers & Locale
- All numbers formatted with `Intl.NumberFormat` (12,345 or 12.3K)
- Timestamps via `Intl.DateTimeFormat`

### Dark Mode
- `color-scheme: dark` on `<html>`
- `<meta name="theme-color">` matches background
- System preference auto-detection via `prefers-color-scheme`

### Animation
- Skeleton loading: `transform`/`opacity` only
- Respect `prefers-reduced-motion`
- No `transition: all`; list properties explicitly
- Progress animations interruptible

### Touch
- `touch-action: manipulation` on interactive elements
- `overscroll-behavior: contain` if any modals/drawers added

### Error Messages
- Include specific fix/next step (e.g. "Start Camofox with `npm start`")
- Active voice, second person

### Anti-patterns to Avoid
- No `user-scalable=no` or `maximum-scale=1`
- No `onPaste` + `preventDefault`
- No `outline-none` without `focus-visible` replacement
- No `<div>` click handlers — use `<button>`
- No images without dimensions
- No hardcoded date/number formats

---

## Project Structure

```
persona-lens/
  persona_lens/
    api/
      __init__.py
      server.py           # FastAPI app + /api/analyze endpoint
    agent/                 # existing
    platforms/             # existing
    utils/                 # existing
  frontend/
    package.json
    next.config.js
    tailwind.config.ts
    components.json        # shadcn/ui config
    app/
      layout.tsx           # Root layout + theme provider
      page.tsx             # Main analysis page
    components/
      search-bar.tsx
      progress-indicator.tsx
      profile-card.tsx
      product-tags.tsx
      writing-style.tsx
      posting-heatmap.tsx
      top-posts.tsx
      tweet-list.tsx
      error-panel.tsx
      empty-state.tsx
    lib/
      api.ts               # SSE client + fetch wrapper
      format.ts            # Intl.NumberFormat / DateTimeFormat helpers
    hooks/
      use-analysis.ts      # SSE connection + state management
```

---

## Dependencies

### Backend (Python, add to pyproject.toml)
- `fastapi`
- `uvicorn`
- `sse-starlette`

### Frontend (Node.js, new package.json)
- `next`
- `react`, `react-dom`
- `tailwindcss`
- `@radix-ui/react-*` (via shadcn/ui)
- `class-variance-authority`, `clsx`, `tailwind-merge` (shadcn/ui utils)
- `react-window` (virtual list)

---

## Startup

```bash
# Terminal 1: Camofox Browser
cd camofox-browser && npm start

# Terminal 2: FastAPI backend
uv run uvicorn persona_lens.api.server:app --reload --port 8000

# Terminal 3: Next.js frontend
cd frontend && npm run dev
```
