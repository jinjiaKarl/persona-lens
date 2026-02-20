# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the CLI
uv run persona-lens <username>
uv run persona-lens <username> --tweets 40 --output report.md

# Run a quick import/smoke check
uv run python -c "from persona_lens.fetchers.x import fetch_snapshot; print('ok')"

# Clean up stale Camofox Browser tabs (if hitting 429s)
uv run python -c "
from dotenv import load_dotenv; load_dotenv()
import httpx, os
with httpx.Client(base_url=os.getenv('CAMOFOX_URL','http://localhost:9377'), timeout=10) as c:
    c.delete('/sessions/persona-lens')
"
```

## Prerequisites

Two external services must be running:

1. **Camofox Browser** on port 9377 — `npm start` inside the cloned `camofox-browser` repo
2. **`.env`** with `OPENAI_API_KEY` set (copy from `.env.example`)

## Architecture

```
CLI (cli.py)
  → fetch_snapshot()        fetchers/x.py     — Camofox Browser REST API → Nitter page
  → extract_activity()      fetchers/x.py     — snowflake ID decode → day + time-slot counts
  → analyze()               analyzers/openai_analyzer.py  — snapshot + activity → PersonaReport
  → format_report()         formatters/markdown.py        — PersonaReport → Markdown string
```

**Data flow:** The CLI fetches an accessibility snapshot (plain text tree, not HTML) from Nitter via Camofox Browser, decodes tweet timestamps locally from Twitter snowflake IDs, passes both to OpenAI in a single call, and renders the result as Markdown.

**`PersonaReport`** (`models.py`) is the central Pydantic model. Fields `posting_days` and `posting_hours` are populated locally before being passed to `analyze()`; all other fields come from the OpenAI JSON response.

## Key Implementation Details

**Camofox Browser API** (base URL from `CAMOFOX_URL`):
- `POST /tabs` → returns `tabId`
- `POST /tabs/:id/wait` with `{"selector": ".timeline-item"}` before every snapshot
- `GET /tabs/:id/snapshot?userId=...` → returns `{"snapshot": "..."}` (accessibility text tree)
- `POST /tabs/:id/navigate` with `{"url": "..."}` for cursor-based pagination
- `DELETE /tabs/:id` in a `finally` block — always clean up or sessions hit a tab limit (429)

**Nitter pagination** uses cursor query params extracted from the snapshot (`cursor=...` regex), not "Load more" clicks.

**Snowflake decoding**: `ts_ms = (tweet_id >> 22) + 1288834974657`. All times are UTC — no timezone conversion is performed.

**Nitter instance resolution** (`_resolve_nitter`): env var → probe `nitter.net` → fallback to LibreRedirect community list at `https://raw.githubusercontent.com/libredirect/instances/main/data.json`.

## README Correction

The README shows `uv run persona-lens analyze @elonmusk` but the CLI has a single command (no subcommand). Correct usage is:

```bash
uv run persona-lens elonmusk
```
