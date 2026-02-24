# KOL Agent Design Document

**Date**: 2026-02-22
**Status**: Implemented

---

## Background

persona-lens is an interactive AI agent for analyzing X/Twitter KOL (Key Opinion Leader) profiles. Users interact via a conversational CLI — asking the agent to analyze accounts, compare results, and answer questions about the data.

---

## Architecture

```
User (conversational CLI via prompt_toolkit)
          ↓
    Main Agent (GPT-4o, OpenAI Agents SDK)
    ├── WebSearchTool         ← general web questions
    └── handoff → KOL Analysis Agent
        ├── fetch_user         ← Camofox Browser / Nitter → structured tweets
        └── analyze_user       ← Profile Analyzer sub-agent (GPT-4o)
              └── products, writing_style, engagement insights
```

### Data Flow

1. User asks to analyze an account (e.g., "analyze @karpathy")
2. Main Agent hands off to KOL Analysis Agent
3. KOL Agent calls `fetch_user` tool:
   - Fetches Nitter accessibility snapshot via Camofox Browser
   - Parses structured tweets (`extract_tweet_data`)
   - Extracts user profile info (`extract_user_info`)
   - Computes posting patterns (`compute_posting_patterns`)
   - Filters out retweets from other users
   - Caches result; returns confirmation to LLM
4. KOL Agent calls `analyze_user` tool:
   - Runs Profile Analyzer sub-agent (single LLM call per user)
   - Returns: products, writing style, engagement insights, top posts
   - Caches result; returns structured summary to LLM
5. LLM synthesizes results and responds to user
6. User can ask follow-up questions — LLM answers from conversation context

### Key Design Decisions

- **No batch mode**: Analysis is driven interactively through conversation
- **Two-tool split**: `fetch_user` (pure Python, no LLM) + `analyze_user` (LLM sub-agent) — keeps fetch fast and LLM cost explicit
- **Caching**: Analyzed users are stored in `AgentContext` across turns — no re-fetching
- **Structured data only**: Raw Nitter snapshot never enters LLM context; only compact structured JSON
- **Agent handoff**: Main Agent delegates KOL tasks to a specialist, keeping general Q&A capability via WebSearch

---

## File Structure

```
persona_lens/
  agent/
    cli.py                        # Typer CLI entry point
    loop.py                       # Interactive agent loop (OpenAI Agents SDK)
  fetchers/
    x.py                          # Camofox Browser REST API → Nitter page
    tweet_parser.py               # Snapshot → structured tweets + user info
    patterns.py                   # Tweet timestamps → posting patterns
  analyzers/
    user_profile_analyzer.py      # GPT-4o sub-agent → products, style, engagement
  utils.py                        # LLM retry with exponential backoff
```

---

## Per-User Analysis Output

Each analyzed user produces:

| Field | Source | Description |
|-------|--------|-------------|
| `display_name`, `bio`, `followers`, `following` | `extract_user_info` | Profile metadata |
| `tweets` | `extract_tweet_data` | Structured tweet list with engagement stats |
| `patterns` | `compute_posting_patterns` | Peak posting days and hours (UTC) |
| `products` | Profile Analyzer sub-agent | Product/tool mentions with categories |
| `writing_style` | Profile Analyzer sub-agent | Tone, vocabulary, format description |
| `engagement` | Profile Analyzer sub-agent | Top posts and what drives engagement |

---

## LLM Calls Per User

| Call | Purpose |
|------|---------|
| Profile Analyzer sub-agent | Products + writing style + engagement (1 call) |
| Agent orchestration | Tool routing + response generation |

**Total for N users ≈ N + orchestration calls** (no separate product/engagement/matching calls).

---

## CLI Interface

```bash
# Start interactive agent
uv run persona-lens

# With custom tweet count
uv run persona-lens --tweets 50
```

Example conversation:
```
You: analyze karpathy and sama
  → Fetching @karpathy...
  → Analyzing @karpathy...
  → Fetching @sama...
  → Analyzing @sama...

Agent: Here's the analysis...

You: who mentions more AI tools?
Agent: (answers from context)

You: compare their writing styles
Agent: (answers from context)
```
