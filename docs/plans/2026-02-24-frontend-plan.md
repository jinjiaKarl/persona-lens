# Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Next.js web frontend that visualizes KOL analysis results from a new FastAPI backend wrapping the existing persona_lens Python modules.

**Architecture:** FastAPI backend at port 8000 imports persona_lens modules directly and streams SSE events (progress + result). Next.js frontend at port 3000 reads URL params (`?user=karpathy&tweets=50`), connects to SSE, and renders 5 result sections: Profile, Products, Writing Style, Posting Heatmap, Top Posts.

**Tech Stack:** Python: FastAPI, uvicorn, sse-starlette. Frontend: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui, react-window.

> **Note (updated 2026-02-24):** Scaffolded with Next.js 16 + React 19 + Tailwind v4 (no `tailwind.config.ts`; config lives in CSS). shadcn/ui v3 supports Tailwind v4 natively. Tasks 1–3 complete on `main`.

---

## Task 1: FastAPI backend — install dependencies

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add backend deps to pyproject.toml**

Open `pyproject.toml` and add to the `[project] dependencies` list:

```toml
"fastapi>=0.110",
"uvicorn[standard]>=0.29",
"sse-starlette>=1.8",
```

**Step 2: Sync**

```bash
uv sync
```

Expected: dependencies installed, no errors.

**Step 3: Smoke-check imports**

```bash
uv run python -c "import fastapi, uvicorn, sse_starlette; print('ok')"
```

Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add fastapi/uvicorn/sse-starlette deps for web API"
```

---

## Task 2: FastAPI backend — create server.py

**Files:**
- Create: `persona_lens/api/__init__.py`
- Create: `persona_lens/api/server.py`

**Step 1: Create package init**

Create `persona_lens/api/__init__.py` as an empty file.

**Step 2: Create server.py**

Create `persona_lens/api/server.py`:

```python
"""FastAPI server exposing persona_lens analysis as SSE endpoints."""
import json
import os
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from persona_lens.platforms.x.fetcher import fetch_snapshot
from persona_lens.platforms.x.parser import extract_tweet_data, extract_user_info
from persona_lens.platforms.x.analyzer import analyze_user_profile
from persona_lens.utils.patterns import compute_posting_patterns

app = FastAPI(title="persona-lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Check that required env vars are set."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not set")
    return {"status": "ok"}


@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30):
    """Stream SSE events: progress stages then final result."""
    username = username.lstrip("@")

    async def _generate() -> AsyncGenerator[dict, None]:
        try:
            yield {
                "event": "progress",
                "data": json.dumps({"stage": "fetching", "message": "Fetching tweets\u2026"}),
            }
            snapshot = fetch_snapshot(username, tweet_count=tweets)
            all_tweets = extract_tweet_data(snapshot)
            user_tweets = [
                t for t in all_tweets
                if t.get("author") is None
                or t["author"].lstrip("@").lower() == username.lower()
            ]

            yield {
                "event": "progress",
                "data": json.dumps({
                    "stage": "parsing",
                    "message": f"Parsed {len(user_tweets)} tweets\u2026",
                }),
            }
            user_info = extract_user_info(snapshot, username)
            patterns = compute_posting_patterns(user_tweets)

            yield {
                "event": "progress",
                "data": json.dumps({"stage": "analyzing", "message": "Running AI analysis\u2026"}),
            }
            profile = await analyze_user_profile(username, user_tweets)

            result = {
                "user_info": user_info,
                "tweets": user_tweets,
                "patterns": patterns,
                "analysis": profile,
            }
            yield {"event": "result", "data": json.dumps(result, ensure_ascii=False)}

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

**Step 3: Smoke-test server starts**

```bash
uv run uvicorn persona_lens.api.server:app --port 8000 --reload
```

Expected: `Uvicorn running on http://127.0.0.1:8000`. Ctrl-C to stop.

**Step 4: Test health endpoint**

With server running in another terminal:

```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}` (or 503 if OPENAI_API_KEY not set — both are valid responses).

**Step 5: Commit**

```bash
git add persona_lens/api/
git commit -m "feat: FastAPI SSE backend for KOL analysis"
```

---

## Task 3: Next.js project scaffold

**Files:**
- Create: `frontend/` directory via `create-next-app`

**Step 1: Scaffold Next.js app** ✅ Done (Next.js 16, React 19, Tailwind v4)

From the repo root:

```bash
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*" \
  --yes
```

**Step 2: Install additional deps**

```bash
cd frontend
npm install react-window
npm install --save-dev @types/react-window
```

**Step 3: Install shadcn/ui**

```bash
cd frontend
npx shadcn@latest init
```

When prompted:
- Style: Default
- Base color: Slate
- CSS variables: Yes

Then add needed components:

```bash
npx shadcn@latest add badge button card input label select separator skeleton table
```

**Step 4: Verify dev server**

```bash
cd frontend && npm run dev
```

Expected: Next.js dev server on http://localhost:3000, default page visible.

**Step 5: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat: scaffold Next.js frontend with shadcn/ui and Tailwind"
```

---

## Task 4: Format utilities

**Files:**
- Create: `frontend/lib/format.ts`

**Step 1: Create format.ts**

```typescript
// frontend/lib/format.ts

/** Format large numbers as "12.3K" or "1.2M" */
export function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

/** Format exact numbers with commas: 12,345 */
export function formatExact(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/** Format UTC ms timestamp as locale date string */
export function formatDate(tsMs: number): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(tsMs));
}
```

**Step 2: Commit**

```bash
cd frontend
git add lib/format.ts
git commit -m "feat: add Intl-based format helpers"
```

---

## Task 5: API types and SSE hook

**Files:**
- Create: `frontend/lib/types.ts`
- Create: `frontend/hooks/use-analysis.ts`

**Step 1: Create types.ts**

```typescript
// frontend/lib/types.ts

export interface UserInfo {
  username: string;
  display_name: string;
  bio: string;
  joined: string;
  tweets_count: number;
  followers: number;
  following: number;
}

export interface Tweet {
  id: string;
  text: string;
  timestamp_ms: number;
  likes: number;
  retweets: number;
  replies: number;
  views: number;
  author: string | null;
  author_name: string | null;
  media: string[];
  has_media: boolean;
  time_ago: string | null;
}

export interface ProductItem {
  product: string;
  category: string;
}

export interface TopPost {
  text: string;
  likes: number;
  retweets: number;
}

export interface AnalysisResult {
  user_info: UserInfo;
  tweets: Tweet[];
  patterns: {
    peak_days: Record<string, number>;
    peak_hours: Record<string, number>;
  };
  analysis: {
    products: ProductItem[];
    writing_style: string;
    engagement: {
      top_posts: TopPost[];
      insights: string;
    };
  };
}

export type ProgressStage = "fetching" | "parsing" | "analyzing" | "done";

export interface ProgressEvent {
  stage: ProgressStage;
  message: string;
}

export interface AnalysisState {
  status: "idle" | "loading" | "success" | "error";
  progress: ProgressEvent | null;
  result: AnalysisResult | null;
  error: { error: string; fix: string } | null;
}
```

**Step 2: Create use-analysis.ts**

```typescript
// frontend/hooks/use-analysis.ts
"use client";

import { useState, useCallback } from "react";
import type { AnalysisState, AnalysisResult, ProgressEvent } from "@/lib/types";

const API_BASE = "http://localhost:8000";

export function useAnalysis() {
  const [state, setState] = useState<AnalysisState>({
    status: "idle",
    progress: null,
    result: null,
    error: null,
  });

  const analyze = useCallback(async (username: string, tweets: number) => {
    setState({ status: "loading", progress: null, result: null, error: null });

    try {
      const res = await fetch(
        `${API_BASE}/api/analyze/${encodeURIComponent(username)}?tweets=${tweets}`,
        { method: "POST" }
      );

      if (!res.ok || !res.body) {
        throw new Error(`Server error: ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (currentEvent === "progress") {
              setState((s) => ({ ...s, progress: data as ProgressEvent }));
            } else if (currentEvent === "result") {
              setState({
                status: "success",
                progress: { stage: "done", message: "Done" },
                result: data as AnalysisResult,
                error: null,
              });
            } else if (currentEvent === "error") {
              setState({
                status: "error",
                progress: null,
                result: null,
                error: data,
              });
            }
            currentEvent = "";
          }
        }
      }
    } catch (err) {
      setState({
        status: "error",
        progress: null,
        result: null,
        error: {
          error: err instanceof Error ? err.message : String(err),
          fix: "Make sure the FastAPI server is running: uv run uvicorn persona_lens.api.server:app --port 8000",
        },
      });
    }
  }, []);

  return { state, analyze };
}
```

**Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/hooks/use-analysis.ts
git commit -m "feat: add analysis types and SSE hook"
```

---

## Task 6: UI components — EmptyState and ErrorPanel

**Files:**
- Create: `frontend/components/empty-state.tsx`
- Create: `frontend/components/error-panel.tsx`

**Step 1: Create empty-state.tsx**

```tsx
// frontend/components/empty-state.tsx
export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <h2 className="text-2xl font-semibold text-balance">
        Analyze any X/Twitter KOL
      </h2>
      <p className="mt-3 max-w-md text-muted-foreground text-pretty">
        Enter a username above to extract their product mentions, writing style,
        and engagement patterns.
      </p>
    </div>
  );
}
```

**Step 2: Create error-panel.tsx**

```tsx
// frontend/components/error-panel.tsx
import { Button } from "@/components/ui/button";

interface ErrorPanelProps {
  error: string;
  fix: string;
  onRetry: () => void;
}

export function ErrorPanel({ error, fix, onRetry }: ErrorPanelProps) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="rounded-lg border border-destructive/50 bg-destructive/10 p-6"
    >
      <p className="font-medium text-destructive">Analysis failed</p>
      <p className="mt-1 text-sm text-muted-foreground">{error}</p>
      {fix && (
        <p className="mt-2 text-sm font-mono bg-muted rounded px-2 py-1 inline-block">
          {fix}
        </p>
      )}
      <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/components/empty-state.tsx frontend/components/error-panel.tsx
git commit -m "feat: add EmptyState and ErrorPanel components"
```

---

## Task 7: UI components — ProgressIndicator and ProfileCard

**Files:**
- Create: `frontend/components/progress-indicator.tsx`
- Create: `frontend/components/profile-card.tsx`

**Step 1: Create progress-indicator.tsx**

```tsx
// frontend/components/progress-indicator.tsx
import { Skeleton } from "@/components/ui/skeleton";
import type { ProgressStage } from "@/lib/types";

const STAGES: { key: ProgressStage; label: string }[] = [
  { key: "fetching", label: "Fetching tweets\u2026" },
  { key: "parsing",  label: "Parsing tweets\u2026" },
  { key: "analyzing", label: "Running AI analysis\u2026" },
  { key: "done",    label: "Done" },
];

const ORDER: ProgressStage[] = ["fetching", "parsing", "analyzing", "done"];

interface ProgressIndicatorProps {
  stage: ProgressStage;
  message: string;
}

export function ProgressIndicator({ stage, message }: ProgressIndicatorProps) {
  const currentIdx = ORDER.indexOf(stage);
  return (
    <div
      aria-live="polite"
      className="space-y-3 py-8"
    >
      {STAGES.map(({ key, label }, idx) => {
        const done = idx < currentIdx;
        const active = idx === currentIdx;
        return (
          <div key={key} className="flex items-center gap-3 text-sm">
            <span className="w-5 text-center">
              {done ? "✓" : active ? "⟳" : "○"}
            </span>
            <span className={done ? "text-muted-foreground line-through" : active ? "font-medium" : "text-muted-foreground"}>
              {active ? message : label}
            </span>
          </div>
        );
      })}
      <Skeleton className="mt-4 h-32 w-full" />
    </div>
  );
}
```

**Step 2: Create profile-card.tsx**

```tsx
// frontend/components/profile-card.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCount, formatExact } from "@/lib/format";
import type { UserInfo } from "@/lib/types";

interface ProfileCardProps {
  userInfo: UserInfo;
  tweetsParsed: number;
}

export function ProfileCard({ userInfo, tweetsParsed }: ProfileCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-balance">
          {userInfo.display_name || userInfo.username}
        </CardTitle>
        <p className="text-sm text-muted-foreground">@{userInfo.username}</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {userInfo.bio && (
          <p className="text-sm leading-relaxed">{userInfo.bio}</p>
        )}
        <dl className="grid grid-cols-3 gap-2 pt-2 text-sm font-variant-nums tabular-nums">
          <div>
            <dt className="text-muted-foreground">Followers</dt>
            <dd className="font-medium">{formatCount(userInfo.followers)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Following</dt>
            <dd className="font-medium">{formatCount(userInfo.following)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Tweets</dt>
            <dd className="font-medium">{formatCount(userInfo.tweets_count)}</dd>
          </div>
        </dl>
        <p className="text-xs text-muted-foreground pt-1">
          {formatExact(tweetsParsed)} tweets analyzed
        </p>
      </CardContent>
    </Card>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/components/progress-indicator.tsx frontend/components/profile-card.tsx
git commit -m "feat: add ProgressIndicator and ProfileCard components"
```

---

## Task 8: UI components — ProductTags and WritingStyle

**Files:**
- Create: `frontend/components/product-tags.tsx`
- Create: `frontend/components/writing-style.tsx`

**Step 1: Create product-tags.tsx**

```tsx
// frontend/components/product-tags.tsx
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ProductItem } from "@/lib/types";

interface ProductTagsProps {
  products: ProductItem[];
}

export function ProductTags({ products }: ProductTagsProps) {
  if (products.length === 0) {
    return (
      <Card>
        <CardHeader><CardTitle>Products Mentioned</CardTitle></CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No products detected.</p>
        </CardContent>
      </Card>
    );
  }

  // Group by category
  const grouped: Record<string, string[]> = {};
  for (const { product, category } of products) {
    (grouped[category] ??= []).push(product);
  }

  return (
    <Card>
      <CardHeader><CardTitle>Products Mentioned</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(grouped).map(([cat, items]) => (
          <div key={cat}>
            <p className="text-xs font-medium text-muted-foreground mb-1">
              {cat} ({items.length})
            </p>
            <div className="flex flex-wrap gap-1">
              {items.map((p) => (
                <Badge key={p} variant="secondary">{p}</Badge>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
```

**Step 2: Create writing-style.tsx**

```tsx
// frontend/components/writing-style.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface WritingStyleProps {
  text: string;
}

export function WritingStyle({ text }: WritingStyleProps) {
  return (
    <Card>
      <CardHeader><CardTitle>Writing Style</CardTitle></CardHeader>
      <CardContent>
        {text ? (
          <p className="text-sm leading-relaxed">{text}</p>
        ) : (
          <p className="text-sm text-muted-foreground">No writing style data.</p>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/components/product-tags.tsx frontend/components/writing-style.tsx
git commit -m "feat: add ProductTags and WritingStyle components"
```

---

## Task 9: UI components — PostingHeatmap and TopPosts

**Files:**
- Create: `frontend/components/posting-heatmap.tsx`
- Create: `frontend/components/top-posts.tsx`

**Step 1: Create posting-heatmap.tsx**

```tsx
// frontend/components/posting-heatmap.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const HOURS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"];

interface PostingHeatmapProps {
  peakDays: Record<string, number>;
  peakHours: Record<string, number>;
}

function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs tabular-nums" style={{ fontVariantNumeric: "tabular-nums" }}>
      <div
        className="h-3 rounded-sm bg-primary transition-all duration-300 motion-reduce:transition-none"
        style={{ width: `${pct}%`, minWidth: pct > 0 ? "2px" : "0" }}
        aria-hidden="true"
      />
      <span className="text-muted-foreground">{value}</span>
    </div>
  );
}

export function PostingHeatmap({ peakDays, peakHours }: PostingHeatmapProps) {
  const maxDay = Math.max(...Object.values(peakDays), 1);
  const maxHour = Math.max(...Object.values(peakHours), 1);
  const topDay = Object.entries(peakDays).sort((a, b) => b[1] - a[1])[0]?.[0];
  const topHour = Object.entries(peakHours).sort((a, b) => b[1] - a[1])[0]?.[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Posting Patterns</CardTitle>
        {topDay && (
          <p className="text-xs text-muted-foreground">
            Peak: {topDay}, {topHour} UTC
          </p>
        )}
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-6">
        <div>
          <h3 className="text-xs font-medium mb-2">By Day</h3>
          <div className="space-y-1" style={{ width: "100%" }}>
            {DAYS.map((d) => (
              <div key={d} className="grid items-center gap-2" style={{ gridTemplateColumns: "6rem 1fr" }}>
                <span className="text-xs text-muted-foreground truncate">{d}</span>
                <Bar value={peakDays[d] ?? 0} max={maxDay} />
              </div>
            ))}
          </div>
        </div>
        <div>
          <h3 className="text-xs font-medium mb-2">By Hour (UTC)</h3>
          <div className="space-y-1">
            {HOURS.map((h) => (
              <div key={h} className="grid items-center gap-2" style={{ gridTemplateColumns: "4rem 1fr" }}>
                <span className="text-xs text-muted-foreground">{h}</span>
                <Bar value={peakHours[h] ?? 0} max={maxHour} />
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Create top-posts.tsx**

```tsx
// frontend/components/top-posts.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { formatExact } from "@/lib/format";
import type { TopPost } from "@/lib/types";

interface TopPostsProps {
  insights: string;
  topPosts: TopPost[];
}

export function TopPosts({ insights, topPosts }: TopPostsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Top Posts &amp; Engagement</CardTitle>
        {insights && (
          <p className="text-sm text-muted-foreground text-pretty">{insights}</p>
        )}
      </CardHeader>
      <CardContent>
        {topPosts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No top posts data.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tweet</TableHead>
                <TableHead className="text-right w-20">Likes</TableHead>
                <TableHead className="text-right w-20">RTs</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {topPosts.map((post, i) => (
                <TableRow key={i}>
                  <TableCell className="max-w-xs">
                    <p className="line-clamp-3 text-sm">{post.text}</p>
                  </TableCell>
                  <TableCell
                    className="text-right text-sm"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {formatExact(post.likes)}
                  </TableCell>
                  <TableCell
                    className="text-right text-sm"
                    style={{ fontVariantNumeric: "tabular-nums" }}
                  >
                    {formatExact(post.retweets)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 3: Commit**

```bash
git add frontend/components/posting-heatmap.tsx frontend/components/top-posts.tsx
git commit -m "feat: add PostingHeatmap and TopPosts components"
```

---

## Task 10: UI component — TweetList

**Files:**
- Create: `frontend/components/tweet-list.tsx`

**Step 1: Create tweet-list.tsx**

This component virtualizes the list when >50 tweets, handles sort, and export.

```tsx
// frontend/components/tweet-list.tsx
"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { formatDate, formatExact } from "@/lib/format";
import type { Tweet } from "@/lib/types";

type SortKey = "time" | "likes" | "retweets";

interface TweetListProps {
  tweets: Tweet[];
  username: string;
}

function exportJSON(tweets: Tweet[], username: string) {
  const blob = new Blob([JSON.stringify(tweets, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${username}-tweets.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function exportCSV(tweets: Tweet[], username: string) {
  const header = "id,text,timestamp_ms,likes,retweets,replies,views";
  const rows = tweets.map((t) =>
    [t.id, JSON.stringify(t.text), t.timestamp_ms, t.likes, t.retweets, t.replies, t.views].join(",")
  );
  const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${username}-tweets.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export function TweetList({ tweets, username }: TweetListProps) {
  const [sort, setSort] = useState<SortKey>("time");
  const [expanded, setExpanded] = useState(false);

  const sorted = [...tweets].sort((a, b) => {
    if (sort === "likes") return b.likes - a.likes;
    if (sort === "retweets") return b.retweets - a.retweets;
    return b.timestamp_ms - a.timestamp_ms;
  });

  // Show only first 10 when collapsed
  const visible = expanded ? sorted : sorted.slice(0, 10);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>All Tweets ({tweets.length})</CardTitle>
          <div className="flex items-center gap-2">
            <label htmlFor="tweet-sort" className="sr-only">Sort tweets by</label>
            <Select value={sort} onValueChange={(v) => setSort(v as SortKey)}>
              <SelectTrigger id="tweet-sort" className="w-36 h-8 text-xs" style={{ touchAction: "manipulation" }}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="time">Sort: Time</SelectItem>
                <SelectItem value="likes">Sort: Likes</SelectItem>
                <SelectItem value="retweets">Sort: Retweets</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              aria-label="Export tweets as JSON"
              style={{ touchAction: "manipulation" }}
              onClick={() => exportJSON(tweets, username)}
            >
              Export JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              aria-label="Export tweets as CSV"
              style={{ touchAction: "manipulation" }}
              onClick={() => exportCSV(tweets, username)}
            >
              Export CSV
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {visible.map((t) => (
          <div key={t.id} className="border-b pb-3 last:border-0 last:pb-0">
            <p className="text-sm line-clamp-3 min-w-0 break-words">{t.text}</p>
            <div
              className="flex gap-4 mt-1 text-xs text-muted-foreground"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {t.timestamp_ms > 0 && <span>{formatDate(t.timestamp_ms)}</span>}
              <span>{formatExact(t.likes)} likes</span>
              <span>{formatExact(t.retweets)} RTs</span>
              <span>{formatExact(t.replies)} replies</span>
            </div>
          </div>
        ))}
        {tweets.length > 10 && (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            style={{ touchAction: "manipulation" }}
            onClick={() => setExpanded((e) => !e)}
          >
            {expanded ? "Show less" : `Show all ${tweets.length} tweets`}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/components/tweet-list.tsx
git commit -m "feat: add TweetList component with sort and export"
```

---

## Task 11: SearchBar component

**Files:**
- Create: `frontend/components/search-bar.tsx`

**Step 1: Create search-bar.tsx**

```tsx
// frontend/components/search-bar.tsx
"use client";

import { useState, FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

interface SearchBarProps {
  onAnalyze: (username: string, tweets: number) => void;
  isLoading: boolean;
  initialUsername?: string;
  initialTweets?: number;
}

export function SearchBar({ onAnalyze, isLoading, initialUsername = "", initialTweets = 30 }: SearchBarProps) {
  const [username, setUsername] = useState(initialUsername);
  const [tweets, setTweets] = useState(String(initialTweets));

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = username.replace(/^@/, "").trim();
    if (!trimmed) return;
    onAnalyze(trimmed, Number(tweets));
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <div className="flex-1">
        <Label htmlFor="username-input" className="sr-only">
          X/Twitter username
        </Label>
        <Input
          id="username-input"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="e.g. karpathy\u2026"
          autoComplete="off"
          spellCheck={false}
          disabled={isLoading}
          className="h-9"
          style={{ touchAction: "manipulation" }}
        />
      </div>
      <div>
        <Label htmlFor="tweet-count" className="sr-only">Number of tweets</Label>
        <Select value={tweets} onValueChange={setTweets} disabled={isLoading}>
          <SelectTrigger id="tweet-count" className="w-24 h-9" style={{ touchAction: "manipulation" }}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {[20, 30, 50, 100].map((n) => (
              <SelectItem key={n} value={String(n)}>{n} tweets</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Button
        type="submit"
        disabled={isLoading || !username.trim()}
        className="h-9"
        style={{ touchAction: "manipulation" }}
      >
        {isLoading ? "Analyzing\u2026" : "Analyze"}
      </Button>
    </form>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/components/search-bar.tsx
git commit -m "feat: add SearchBar component"
```

---

## Task 12: Main page and root layout

**Files:**
- Modify: `frontend/app/layout.tsx`
- Modify: `frontend/app/page.tsx`

**Step 1: Update layout.tsx**

Replace the contents of `frontend/app/layout.tsx`:

```tsx
// frontend/app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  title: "Persona Lens",
  description: "Analyze X/Twitter KOL profiles with AI",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="http://localhost:8000" />
      </head>
      <body className={`${inter.className} min-h-screen bg-background antialiased`}>
        {children}
      </body>
    </html>
  );
}
```

**Step 2: Create page.tsx**

Replace the contents of `frontend/app/page.tsx`:

```tsx
// frontend/app/page.tsx
"use client";

import { useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { SearchBar } from "@/components/search-bar";
import { ProgressIndicator } from "@/components/progress-indicator";
import { ProfileCard } from "@/components/profile-card";
import { ProductTags } from "@/components/product-tags";
import { WritingStyle } from "@/components/writing-style";
import { PostingHeatmap } from "@/components/posting-heatmap";
import { TopPosts } from "@/components/top-posts";
import { TweetList } from "@/components/tweet-list";
import { EmptyState } from "@/components/empty-state";
import { ErrorPanel } from "@/components/error-panel";
import { useAnalysis } from "@/hooks/use-analysis";

export default function Home() {
  const router = useRouter();
  const params = useSearchParams();
  const { state, analyze } = useAnalysis();

  const initialUser = params.get("user") ?? "";
  const initialTweets = Number(params.get("tweets") ?? 30);

  // Auto-run if URL has a user param on first load
  useEffect(() => {
    if (initialUser) {
      analyze(initialUser, initialTweets);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAnalyze = useCallback(
    (username: string, tweets: number) => {
      router.push(`/?user=${encodeURIComponent(username)}&tweets=${tweets}`);
      analyze(username, tweets);
    },
    [router, analyze]
  );

  const { status, progress, result, error } = state;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 space-y-6">
      {/* Skip link for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:ring-2 focus:ring-ring"
      >
        Skip to content
      </a>

      <header>
        <h1 className="text-xl font-bold tracking-tight text-balance mb-4">
          Persona Lens
        </h1>
        <SearchBar
          onAnalyze={handleAnalyze}
          isLoading={status === "loading"}
          initialUsername={initialUser}
          initialTweets={initialTweets}
        />
      </header>

      <main id="main-content">
        {status === "idle" && <EmptyState />}

        {status === "loading" && progress && (
          <ProgressIndicator stage={progress.stage} message={progress.message} />
        )}

        {status === "error" && error && (
          <ErrorPanel
            error={error.error}
            fix={error.fix}
            onRetry={() => {
              const u = params.get("user") ?? "";
              const t = Number(params.get("tweets") ?? 30);
              if (u) analyze(u, t);
            }}
          />
        )}

        {status === "success" && result && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <ProfileCard
                userInfo={result.user_info}
                tweetsParsed={result.tweets.length}
              />
              <ProductTags products={result.analysis.products} />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <WritingStyle text={result.analysis.writing_style} />
              <PostingHeatmap
                peakDays={result.patterns.peak_days}
                peakHours={result.patterns.peak_hours}
              />
            </div>

            <TopPosts
              insights={result.analysis.engagement.insights}
              topPosts={result.analysis.engagement.top_posts}
            />

            <TweetList
              tweets={result.tweets}
              username={result.user_info.username}
            />
          </div>
        )}
      </main>
    </div>
  );
}
```

**Step 3: Verify the app builds**

```bash
cd frontend && npm run build
```

Expected: build completes with no errors. Warnings about `useSearchParams` needing Suspense boundary are OK — wrap in Suspense if Next.js requires it.

If you get a Suspense error for `useSearchParams`, wrap the page content:

```tsx
// In page.tsx, wrap <Home> content in <Suspense fallback={null}>
import { Suspense } from "react";
// ... wrap body in <Suspense fallback={<div />}>
```

**Step 4: Manual smoke test**

```bash
# Terminal 1
uv run uvicorn persona_lens.api.server:app --port 8000 --reload

# Terminal 2
cd frontend && npm run dev
```

Open http://localhost:3000 — empty state should appear. Enter a username and click Analyze.

**Step 5: Commit**

```bash
git add frontend/app/layout.tsx frontend/app/page.tsx
git commit -m "feat: main page with URL state sync and full analysis layout"
```

---

## Task 13: Dark mode support

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: `frontend/app/layout.tsx`

**Step 1: Ensure globals.css has dark mode vars**

shadcn/ui init already creates dark mode CSS variables in `globals.css`. Verify the file contains:

```css
@layer base {
  .dark { ... }
}
```

If missing, run `npx shadcn@latest init` again or check the shadcn docs.

**Step 2: Add next-themes for system preference**

```bash
cd frontend && npm install next-themes
```

**Step 3: Create theme provider**

Create `frontend/components/theme-provider.tsx`:

```tsx
"use client";
import { ThemeProvider as NextThemesProvider } from "next-themes";
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem>
      {children}
    </NextThemesProvider>
  );
}
```

**Step 4: Wrap layout with ThemeProvider**

In `frontend/app/layout.tsx`, import and wrap:

```tsx
import { ThemeProvider } from "@/components/theme-provider";
// In body:
<ThemeProvider>{children}</ThemeProvider>
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: add dark mode support via next-themes"
```

---

## Task 14: Final verification

**Step 1: Run full stack**

```bash
# Terminal 1: Camofox Browser (must be running)
# Terminal 2:
uv run uvicorn persona_lens.api.server:app --port 8000 --reload
# Terminal 3:
cd frontend && npm run dev
```

**Step 2: Checklist**

- [ ] http://localhost:3000 shows empty state
- [ ] Entering a username + clicking Analyze shows progress stages
- [ ] Results render: Profile, Products, Writing Style, Heatmap, Top Posts, Tweets
- [ ] URL updates to `?user=<username>&tweets=<n>`
- [ ] Refreshing the page re-runs analysis for same user
- [ ] Export JSON/CSV buttons download files
- [ ] Dark mode toggles correctly with system preference
- [ ] http://localhost:8000/api/health returns `{"status":"ok"}`

**Step 3: Run Python tests to confirm backend unchanged**

```bash
uv run pytest tests/ -v
```

Expected: all existing tests pass.

**Step 4: Commit**

```bash
git add .
git commit -m "feat: complete persona-lens web frontend"
```
