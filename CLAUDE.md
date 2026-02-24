# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Start the interactive agent
uv run persona-lens
uv run persona-lens --tweets 50

# Run tests
uv run pytest tests/ -v

# Run a quick import/smoke check
uv run python -c "from persona_lens.agent.loop import run_interactive_loop; print('ok')"

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
agent/cli.py              — Typer CLI entry point (no subcommands)
agent/loop.py             — Interactive agent loop (OpenAI Agents SDK)
  ├─ Main Agent           — general Q&A + WebSearch, hands off KOL tasks
  └─ KOL Analysis Agent   — specialist with two tools:
       ├─ fetch_user       — fetch snapshot → parse tweets → compute patterns (pure Python)
       └─ analyze_user     — run Profile Analyzer sub-agent (GPT-4o)
fetchers/x.py             — Camofox Browser REST API → Nitter page
fetchers/tweet_parser.py  — snapshot → structured tweets + user info
fetchers/patterns.py      — tweet timestamps → posting patterns
analyzers/user_profile_analyzer.py  — GPT-4o sub-agent → products, style, engagement
```

**Data flow:** The agent fetches an accessibility snapshot (plain text tree) from Nitter via Camofox Browser, parses it into structured tweet data (text, engagement stats, media, timestamps), computes posting patterns locally, then sends the structured data to a Profile Analyzer sub-agent for product extraction, writing style analysis, and engagement insights. Raw snapshots never enter the LLM context.

**Two-tool design:** `fetch_user` is pure Python (no LLM cost), `analyze_user` triggers one LLM call per user via a sub-agent.

**Caching:** Analyzed users are stored in `AgentContext` across conversation turns — same user is never re-fetched or re-analyzed.

## Key Implementation Details

**Camofox Browser API** (base URL from `CAMOFOX_URL`):
- `POST /tabs` → returns `tabId`
- `POST /tabs/:id/wait` with `{"selector": ".timeline-item"}` before every snapshot
- `GET /tabs/:id/snapshot?userId=...` → returns `{"snapshot": "..."}` (accessibility text tree)
- `POST /tabs/:id/navigate` with `{"url": "..."}` for cursor-based pagination
- `DELETE /tabs/:id` in a `finally` block — always clean up or sessions hit a tab limit (429)

**Tweet parsing** (`extract_tweet_data`): Detects tweets by bare-link anchors (`- link [eN]:` + `/url: /user/status/ID#m`), separates TOC anchors from content anchors, then parses each block for: author, text, engagement stats (replies, retweets, likes, views), media URLs, quoted text, and relative time. Falls back to a simpler pattern for non-standard snapshots.

**User info** (`extract_user_info`): Extracts display name, bio, joined date, followers, following, tweets count from the snapshot header.

**Author filtering:** `fetch_user` in `loop.py` filters out tweets where the author handle doesn't match the target username, removing retweets from other users.

**Nitter pagination** uses cursor query params extracted from the snapshot (`cursor=...` regex), not "Load more" clicks.

**Snowflake decoding**: `ts_ms = (tweet_id >> 22) + 1288834974657`. All times are UTC — no timezone conversion is performed.

**Nitter instance resolution** (`_resolve_nitter`): env var → probe `nitter.net` → fallback to LibreRedirect community list at `https://raw.githubusercontent.com/libredirect/instances/main/data.json`.

**Profile Analyzer sub-agent** (`user_profile_analyzer.py`): Uses OpenAI Agents SDK with Pydantic `output_type=UserProfile` for structured output. Returns: products (with AI-inferred categories), writing style, engagement insights and top posts.
