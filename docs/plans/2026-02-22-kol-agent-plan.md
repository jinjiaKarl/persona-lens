# KOL Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a tool-use agent on top of persona-lens that batch-analyzes 5–20 X/Twitter KOLs, extracts product mentions + engagement patterns, and matches influencers to content briefs.

**Architecture:** A Python agent (`persona_lens/agent/`) wraps an LLM (OpenAI gpt-4o) with six tools. Three tools are pure Python (no LLM cost); three make a single focused LLM call each. The agent orchestrates the full workflow and outputs a Markdown report.

**Tech Stack:** Python 3.13, OpenAI SDK, httpx, typer, rich, pydantic, pytest

---

## Prerequisites

- Camofox Browser running on port 9377 (`npm start` in camofox-browser repo)
- `.env` with `OPENAI_API_KEY` set
- `uv sync` completed

---

## Task 1: Add pytest and write test scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/test_extract_tweet_data.py`

**Step 1: Add pytest dependency**

Edit `pyproject.toml` — add to `[project]` dependencies:

```toml
[project]
dependencies = [
  "httpx>=0.27",
  "openai>=1.0",
  "typer>=0.12",
  "rich>=13.0",
  "pydantic>=2.0",
  "python-dotenv",
  "pytest>=8.0",
]
```

**Step 2: Install**

```bash
uv sync
```

Expected: resolves and installs pytest.

**Step 3: Create test files**

```bash
touch tests/__init__.py tests/test_extract_tweet_data.py
```

**Step 4: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: add pytest, test scaffold"
```

---

## Task 2: `extract_tweet_data` — parse raw snapshot into structured tweets

This is the most critical function. It must run **before** `clean_snapshot()` since cleaning drops engagement numbers.

**Files:**
- Create: `persona_lens/fetchers/tweet_parser.py`
- Modify: `tests/test_extract_tweet_data.py`

**How the raw Nitter snapshot looks:**

Each tweet in the accessibility tree appears as a block like:
```
- text: "This is the tweet content here"
- text: "  3  12  847  4,291,023"       ← replies retweets likes views (dropped by clean_snapshot)
- link "/url: /username/status/1234567890123456789#m"
```

The numbers line matches `re.fullmatch(r'[\d,\s]+', content)` — that's exactly what `clean_snapshot` drops.

**Step 1: Write the failing test**

```python
# tests/test_extract_tweet_data.py
from persona_lens.fetchers.tweet_parser import extract_tweet_data

SAMPLE_SNAPSHOT = """
- text: "Just shipped a new feature for Cursor!"
- text: "3  12  847"
- link "status" [e1]:
  - /url: /karpathy/status/1750000000000000001#m
- text: "Trying out Claude 3.5 Sonnet today. Impressive."
- text: "1  5  210"
- link "status" [e2]:
  - /url: /karpathy/status/1750000000000000002#m
"""

def test_extract_returns_list_of_tweets():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    assert len(tweets) == 2

def test_tweet_has_required_fields():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    t = tweets[0]
    assert "id" in t
    assert "text" in t
    assert "timestamp_ms" in t

def test_tweet_text_is_captured():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    assert "Cursor" in tweets[0]["text"]

def test_tweet_id_decoded_to_timestamp():
    tweets = extract_tweet_data(SAMPLE_SNAPSHOT)
    # snowflake 1750000000000000001 → ~2022, so timestamp_ms > 0
    assert tweets[0]["timestamp_ms"] > 0
```

**Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_extract_tweet_data.py -v
```

Expected: `ModuleNotFoundError: No module named 'persona_lens.fetchers.tweet_parser'`

**Step 3: Implement `extract_tweet_data`**

Create `persona_lens/fetchers/tweet_parser.py`:

```python
import re
from typing import Any

_TWITTER_EPOCH_MS = 1288834974657


def _snowflake_to_ms(tweet_id: str) -> int:
    try:
        return (int(tweet_id) >> 22) + _TWITTER_EPOCH_MS
    except (ValueError, OverflowError):
        return 0


def extract_tweet_data(snapshot: str) -> list[dict[str, Any]]:
    """Parse raw Nitter accessibility snapshot into structured tweet list.

    Must be called on the raw snapshot, before clean_snapshot().
    Each returned dict has: id, text, timestamp_ms, likes, retweets, replies.

    Nitter snapshot structure (per tweet):
      - text: "<tweet content>"
      - text: "<replies>  <retweets>  <likes>"   ← pure-digit line
      - /url: /username/status/<id>#m
    """
    tweets: list[dict[str, Any]] = []

    # Split snapshot into lines, strip
    lines = [l.strip() for l in snapshot.splitlines()]

    # Find all tweet IDs and their line positions
    id_pattern = re.compile(r'/url: /\w+/status/(\d+)#m')

    # Walk lines; collect (text, engagement, id) triplets
    # Strategy: scan forward, when we hit an id line, look back for text + stats
    pending_texts: list[str] = []
    pending_stats: str | None = None

    for line in lines:
        id_match = id_pattern.search(line)
        if id_match:
            tweet_id = id_match.group(1)
            # Parse engagement from pending_stats
            likes = retweets = replies = 0
            if pending_stats:
                nums = re.findall(r'[\d,]+', pending_stats)
                nums_int = [int(n.replace(',', '')) for n in nums]
                if len(nums_int) >= 3:
                    replies, retweets, likes = nums_int[0], nums_int[1], nums_int[2]
                elif len(nums_int) == 2:
                    retweets, likes = nums_int[0], nums_int[1]
                elif len(nums_int) == 1:
                    likes = nums_int[0]

            text = " ".join(pending_texts).strip()
            if text or tweet_id:
                tweets.append({
                    "id": tweet_id,
                    "text": text,
                    "timestamp_ms": _snowflake_to_ms(tweet_id),
                    "likes": likes,
                    "retweets": retweets,
                    "replies": replies,
                })
            pending_texts = []
            pending_stats = None
            continue

        # Detect text lines
        if line.startswith("- text:"):
            content = line.removeprefix("- text:").strip().strip('"')
            # Is this a pure-digit engagement line?
            if re.fullmatch(r'[\d,\s]+', content):
                pending_stats = content
            else:
                pending_texts.append(content)

    return tweets
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_extract_tweet_data.py -v
```

Expected: all 4 tests PASS.

**Step 5: Commit**

```bash
git add persona_lens/fetchers/tweet_parser.py tests/test_extract_tweet_data.py
git commit -m "feat: add extract_tweet_data to parse raw snapshot"
```

---

## Task 3: `compute_posting_patterns` — reuse snowflake decoding

This wraps the existing `extract_activity` logic but takes the structured tweet list instead of raw snapshot.

**Files:**
- Create: `persona_lens/fetchers/patterns.py`
- Create: `tests/test_patterns.py`

**Step 1: Write the failing test**

```python
# tests/test_patterns.py
from persona_lens.fetchers.patterns import compute_posting_patterns

# snowflake 1750000000000000001 → 2022-01-20 ~UTC, a Thursday
TWEETS = [
    {"id": "1750000000000000001", "timestamp_ms": 1642723174657, "text": "x", "likes": 5, "retweets": 1, "replies": 0},
    {"id": "1750000000000000002", "timestamp_ms": 1642723174657, "text": "y", "likes": 10, "retweets": 2, "replies": 1},
]

def test_returns_peak_days_and_hours():
    result = compute_posting_patterns(TWEETS)
    assert "peak_days" in result
    assert "peak_hours" in result

def test_peak_days_is_dict_of_str_int():
    result = compute_posting_patterns(TWEETS)
    for k, v in result["peak_days"].items():
        assert isinstance(k, str)
        assert isinstance(v, int)

def test_empty_tweets_returns_empty():
    result = compute_posting_patterns([])
    assert result["peak_days"] == {}
    assert result["peak_hours"] == {}
```

**Step 2: Run to verify fails**

```bash
uv run pytest tests/test_patterns.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement**

Create `persona_lens/fetchers/patterns.py`:

```python
from collections import Counter
from datetime import datetime, timezone
from typing import Any

_TIME_SLOTS = [
    ("00-04", 0), ("04-08", 4), ("08-12", 8),
    ("12-16", 12), ("16-20", 16), ("20-24", 20),
]


def _hour_to_slot(hour: int) -> str:
    for label, start in reversed(_TIME_SLOTS):
        if hour >= start:
            return label
    return "00-04"


def compute_posting_patterns(tweets: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute peak posting days and time slots from structured tweet list."""
    days: Counter = Counter()
    hours: Counter = Counter()
    for t in tweets:
        ts_ms = t.get("timestamp_ms", 0)
        if not ts_ms:
            continue
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
        days[dt.strftime("%A")] += 1
        hours[_hour_to_slot(dt.hour)] += 1
    return {"peak_days": dict(days), "peak_hours": dict(hours)}
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_patterns.py -v
```

Expected: all 3 PASS.

**Step 5: Commit**

```bash
git add persona_lens/fetchers/patterns.py tests/test_patterns.py
git commit -m "feat: add compute_posting_patterns"
```

---

## Task 4: `product_analyzer.py` — LLM call to extract product mentions

**Files:**
- Create: `persona_lens/analyzers/product_analyzer.py`
- Create: `tests/test_product_analyzer.py`

**Step 1: Write the failing test (mock LLM)**

```python
# tests/test_product_analyzer.py
from unittest.mock import patch, MagicMock
from persona_lens.analyzers.product_analyzer import analyze_products

TWEETS = [
    {"id": "1", "text": "Cursor is amazing for coding", "likes": 100, "retweets": 10, "replies": 5, "timestamp_ms": 1700000000000},
    {"id": "2", "text": "Claude API is fast", "likes": 50, "retweets": 5, "replies": 2, "timestamp_ms": 1700000001000},
]

MOCK_RESPONSE = '[{"product": "Cursor", "category": "AI工具-编程", "tweet_ids": ["1"]}, {"product": "Claude API", "category": "AI工具-Agent", "tweet_ids": ["2"]}]'

def test_analyze_products_returns_list():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.product_analyzer.OpenAI", return_value=mock_client):
        result = analyze_products("karpathy", TWEETS)
    assert isinstance(result, list)
    assert len(result) == 2

def test_product_has_required_fields():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.product_analyzer.OpenAI", return_value=mock_client):
        result = analyze_products("karpathy", TWEETS)
    assert "product" in result[0]
    assert "category" in result[0]
    assert "tweet_ids" in result[0]
```

**Step 2: Run to verify fails**

```bash
uv run pytest tests/test_product_analyzer.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement**

Create `persona_lens/analyzers/product_analyzer.py`:

```python
import json
import os
from typing import Any

from openai import OpenAI

SYSTEM_PROMPT = """You are a product intelligence analyst. Given a list of tweets, extract all product or tool mentions.

For each product found, return a JSON array with objects:
- product: product name (string)
- category: one of "AI工具-编程", "AI工具-写作", "AI工具-图像", "AI工具-视频", "AI工具-Agent", "SaaS工具", "硬件/消费电子", "开发工具", "其他"
- tweet_ids: list of tweet IDs that mention this product

Only include actual products/tools/services. Ignore vague references.
Return only a valid JSON array, no markdown."""


def analyze_products(username: str, tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract product mentions from tweets using a single LLM call."""
    if not tweets:
        return []

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    tweet_lines = "\n".join(
        f'[ID:{t["id"]}] {t["text"]}' for t in tweets if t.get("text")
    )
    user_content = f"Tweets from @{username}:\n\n{tweet_lines}"

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT + "\n\nReturn JSON with key 'products' containing the array."},
            {"role": "user", "content": user_content},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("products", [])
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_product_analyzer.py -v
```

Expected: 2 PASS.

**Step 5: Commit**

```bash
git add persona_lens/analyzers/product_analyzer.py tests/test_product_analyzer.py
git commit -m "feat: add analyze_products LLM analyzer"
```

---

## Task 5: `engagement_analyzer.py` — find high-engagement patterns

**Files:**
- Create: `persona_lens/analyzers/engagement_analyzer.py`
- Create: `tests/test_engagement_analyzer.py`

**Step 1: Write the failing test**

```python
# tests/test_engagement_analyzer.py
from unittest.mock import patch, MagicMock
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns

ALL_USER_DATA = {
    "karpathy": {
        "tweets": [
            {"id": "1", "text": "Cursor rocks", "likes": 500, "retweets": 100, "replies": 20, "timestamp_ms": 1700000000000},
            {"id": "2", "text": "hello world", "likes": 5, "retweets": 1, "replies": 0, "timestamp_ms": 1700000001000},
        ],
        "products": [{"product": "Cursor", "category": "AI工具-编程", "tweet_ids": ["1"]}],
        "patterns": {"peak_days": {"Thursday": 2}, "peak_hours": {"12-16": 2}},
    }
}

MOCK_RESPONSE = '{"insights": "High engagement on AI coding tools", "patterns": [{"type": "product_type", "description": "AI编程工具互动最高"}]}'

def test_returns_insights_and_patterns():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.engagement_analyzer.OpenAI", return_value=mock_client):
        result = find_engagement_patterns(ALL_USER_DATA)
    assert "insights" in result
    assert "patterns" in result
```

**Step 2: Run to verify fails**

```bash
uv run pytest tests/test_engagement_analyzer.py -v
```

**Step 3: Implement**

Create `persona_lens/analyzers/engagement_analyzer.py`:

```python
import json
import os
from typing import Any

from openai import OpenAI

SYSTEM_PROMPT = """You are a social media analyst. Given engagement data for multiple KOL accounts, identify:
1. Which product types drive the highest engagement
2. Whether specific messaging patterns (comparison, personal experience, data-driven) correlate with higher engagement
3. Cross-account patterns

Return JSON with:
- insights: 2-3 sentence summary of key findings
- patterns: list of {type, description} objects (type: "product_type" | "messaging" | "timing")

Return only valid JSON with key "result" wrapping the above."""


def find_engagement_patterns(all_user_data: dict[str, Any]) -> dict[str, Any]:
    """Analyze high-engagement posts across all users to find patterns."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Build compact summary: only top 5 tweets per user by engagement
    summary_lines = []
    for username, data in all_user_data.items():
        tweets = data.get("tweets", [])
        top = sorted(tweets, key=lambda t: t.get("likes", 0) + t.get("retweets", 0) * 3, reverse=True)[:5]
        products = data.get("products", [])
        summary_lines.append(f"@{username} top tweets:")
        for t in top:
            summary_lines.append(f"  [{t['likes']}L {t['retweets']}RT] {t['text'][:120]}")
        summary_lines.append(f"  Products mentioned: {[p['product'] for p in products]}")

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "\n".join(summary_lines)},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("result", data)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_engagement_analyzer.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add persona_lens/analyzers/engagement_analyzer.py tests/test_engagement_analyzer.py
git commit -m "feat: add find_engagement_patterns analyzer"
```

---

## Task 6: `content_matcher.py` — match briefs to influencers

**Files:**
- Create: `persona_lens/analyzers/content_matcher.py`
- Create: `tests/test_content_matcher.py`

**Step 1: Write the failing test**

```python
# tests/test_content_matcher.py
from unittest.mock import patch, MagicMock
from persona_lens.analyzers.content_matcher import match_content_briefs

BRIEFS = ["AI产品测评，大众口吻", "技术深度分析，dev口吻"]
PROFILES = {
    "karpathy": {"writing_style": "technical but accessible", "products": ["Cursor", "Claude"]},
    "sama": {"writing_style": "formal, data-driven", "products": ["ChatGPT", "OpenAI API"]},
}

MOCK_RESPONSE = '{"matches": [{"brief": "AI产品测评，大众口吻", "matched_users": ["karpathy"], "reason": "accessible technical style"}, {"brief": "技术深度分析，dev口吻", "matched_users": ["sama"], "reason": "formal data-driven"}]}'

def test_returns_match_per_brief():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = MOCK_RESPONSE
    with patch("persona_lens.analyzers.content_matcher.OpenAI", return_value=mock_client):
        result = match_content_briefs(BRIEFS, PROFILES)
    assert len(result) == 2
    assert result[0]["brief"] == "AI产品测评，大众口吻"
    assert "matched_users" in result[0]
    assert "reason" in result[0]
```

**Step 2: Run to verify fails**

```bash
uv run pytest tests/test_content_matcher.py -v
```

**Step 3: Implement**

Create `persona_lens/analyzers/content_matcher.py`:

```python
import json
import os
from typing import Any

from openai import OpenAI

SYSTEM_PROMPT = """You are a content strategy expert. Given a list of content briefs and influencer profiles, match each brief to the most suitable influencers.

For each brief, return which users best fit based on their writing style, tone, and past product mentions.

Return JSON with key "matches" containing a list of:
- brief: the content brief text
- matched_users: list of usernames (best fit first, max 3)
- reason: 1-2 sentence explanation of why they fit"""


def match_content_briefs(
    briefs: list[str],
    profiles: dict[str, Any],
) -> list[dict[str, Any]]:
    """Match content direction briefs to best-fit influencers."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    profile_text = "\n".join(
        f"@{u}: style={p.get('writing_style', 'unknown')}, products={p.get('products', [])}"
        for u, p in profiles.items()
    )
    briefs_text = "\n".join(f"- {b}" for b in briefs)

    user_content = f"Content briefs:\n{briefs_text}\n\nInfluencer profiles:\n{profile_text}"

    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    return data.get("matches", [])
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_content_matcher.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add persona_lens/analyzers/content_matcher.py tests/test_content_matcher.py
git commit -m "feat: add match_content_briefs analyzer"
```

---

## Task 7: `agent/tools.py` — tool registry

**Files:**
- Create: `persona_lens/agent/__init__.py`
- Create: `persona_lens/agent/tools.py`

**Step 1: Create the module and tool definitions**

```bash
touch persona_lens/agent/__init__.py
```

Create `persona_lens/agent/tools.py`:

```python
"""Tool registry: OpenAI function schemas + Python function mapping."""
from typing import Any

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data
from persona_lens.fetchers.patterns import compute_posting_patterns
from persona_lens.analyzers.product_analyzer import analyze_products
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns
from persona_lens.analyzers.content_matcher import match_content_briefs

# ── OpenAI tool schemas ────────────────────────────────────────────────────────

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_user_tweets",
            "description": "Fetch raw tweet snapshot for a single X/Twitter user via Nitter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "X username without @"},
                    "tweet_count": {"type": "integer", "description": "Number of tweets to fetch", "default": 30},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_and_analyze_user",
            "description": "Parse raw snapshot into structured tweets, compute posting patterns, and extract product mentions. Call this after fetch_user_tweets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "snapshot": {"type": "string", "description": "Raw snapshot from fetch_user_tweets"},
                },
                "required": ["username", "snapshot"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_engagement_patterns",
            "description": "Analyze high-engagement posts across all fetched users to find product and messaging patterns. Call after all users are analyzed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_data_json": {"type": "string", "description": "JSON string of all_user_data dict"},
                },
                "required": ["user_data_json"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_content_briefs",
            "description": "Match content direction briefs to best-fit influencers. Call after engagement patterns are found.",
            "parameters": {
                "type": "object",
                "properties": {
                    "briefs_json": {"type": "string", "description": "JSON array of brief strings"},
                    "profiles_json": {"type": "string", "description": "JSON dict of user profiles"},
                },
                "required": ["briefs_json", "profiles_json"],
            },
        },
    },
]

# ── Python implementations ─────────────────────────────────────────────────────

def _fetch_user_tweets(username: str, tweet_count: int = 30) -> dict[str, Any]:
    snapshot = fetch_snapshot(username, tweet_count=tweet_count)
    return {"username": username, "snapshot": snapshot}


def _extract_and_analyze_user(username: str, snapshot: str) -> dict[str, Any]:
    tweets = extract_tweet_data(snapshot)
    patterns = compute_posting_patterns(tweets)
    products = analyze_products(username, tweets)
    return {
        "username": username,
        "tweets": tweets,
        "patterns": patterns,
        "products": products,
    }


def _find_engagement_patterns(user_data_json: str) -> dict[str, Any]:
    import json
    all_user_data = json.loads(user_data_json)
    return find_engagement_patterns(all_user_data)


def _match_content_briefs(briefs_json: str, profiles_json: str) -> list[dict[str, Any]]:
    import json
    briefs = json.loads(briefs_json)
    profiles = json.loads(profiles_json)
    return match_content_briefs(briefs, profiles)


TOOL_FUNCTIONS: dict[str, Any] = {
    "fetch_user_tweets": _fetch_user_tweets,
    "extract_and_analyze_user": _extract_and_analyze_user,
    "find_engagement_patterns": _find_engagement_patterns,
    "match_content_briefs": _match_content_briefs,
}
```

**Step 2: Smoke test**

```bash
uv run python -c "from persona_lens.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS; print('tools ok', len(TOOL_SCHEMAS))"
```

Expected: `tools ok 4`

**Step 3: Commit**

```bash
git add persona_lens/agent/
git commit -m "feat: add agent tool registry"
```

---

## Task 8: `agent/core.py` — agent main loop

**Files:**
- Create: `persona_lens/agent/core.py`

Create `persona_lens/agent/core.py`:

```python
"""Agent core: LLM tool-use loop that orchestrates the full KOL analysis."""
import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

SYSTEM_PROMPT = """You are a KOL (Key Opinion Leader) analysis agent for X/Twitter.

Your job:
1. For each username in the list, call fetch_user_tweets then extract_and_analyze_user
2. After ALL users are analyzed, call find_engagement_patterns with all collected data
3. If content briefs are provided, call match_content_briefs
4. Return a final structured summary

Process users sequentially (one at a time) to avoid rate limits.
Always pass full snapshot strings between tool calls."""


def run_agent(
    usernames: list[str],
    briefs: list[str],
    tweet_count: int = 30,
) -> dict[str, Any]:
    """Run the KOL analysis agent. Returns structured result dict."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    task_description = (
        f"Analyze these X/Twitter accounts: {usernames}. "
        f"Fetch {tweet_count} tweets each. "
        + (f"Then match these content briefs: {briefs}" if briefs else "No content briefs needed.")
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_description},
    ]

    all_user_data: dict[str, Any] = {}
    engagement_result: dict[str, Any] = {}
    match_result: list[dict[str, Any]] = []

    # Tool-use loop — max 50 iterations to prevent runaway
    for _ in range(50):
        response = client.chat.completions.create(
            model="gpt-4o",
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            messages=messages,
        )
        msg = response.choices[0].message
        messages.append(msg)

        # No more tool calls → done
        if not msg.tool_calls:
            break

        # Execute each tool call
        for call in msg.tool_calls:
            fn_name = call.function.name
            fn_args = json.loads(call.function.arguments)
            fn = TOOL_FUNCTIONS.get(fn_name)

            if fn is None:
                result = {"error": f"Unknown tool: {fn_name}"}
            else:
                result = fn(**fn_args)

            # Collect side-effects for final report
            if fn_name == "extract_and_analyze_user":
                username = fn_args.get("username", "")
                all_user_data[username] = result
            elif fn_name == "find_engagement_patterns":
                engagement_result = result
            elif fn_name == "match_content_briefs":
                match_result = result

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return {
        "users": all_user_data,
        "engagement": engagement_result,
        "matches": match_result,
        "summary": msg.content or "",
    }
```

**Smoke test:**

```bash
uv run python -c "from persona_lens.agent.core import run_agent; print('core ok')"
```

Expected: `core ok`

**Commit:**

```bash
git add persona_lens/agent/core.py
git commit -m "feat: add agent core loop"
```

---

## Task 9: `agent/cli.py` + pyproject.toml entry point

**Files:**
- Create: `persona_lens/agent/cli.py`
- Modify: `pyproject.toml`

**Step 1: Create CLI**

Create `persona_lens/agent/cli.py`:

```python
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

load_dotenv()
app = typer.Typer()
console = Console()


@app.command()
def analyze(
    accounts: Path = typer.Option(..., "--accounts", "-a", help="File with one username per line"),
    tweets: int = typer.Option(30, "--tweets", "-t", help="Tweets to fetch per account"),
    briefs: Optional[Path] = typer.Option(None, "--briefs", "-b", help="File with content briefs (one per line)"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save report to file"),
):
    usernames = [u.strip().lstrip("@") for u in accounts.read_text().splitlines() if u.strip()]
    brief_list = []
    if briefs:
        brief_list = [b.strip() for b in briefs.read_text().splitlines() if b.strip()]

    console.print(f"[bold green]Analyzing {len(usernames)} accounts...[/]")

    from persona_lens.agent.core import run_agent
    result = run_agent(usernames, brief_list, tweet_count=tweets)

    from persona_lens.agent.formatter import format_agent_report
    md = format_agent_report(result)

    if output:
        output.write_text(md)
        console.print(f"[bold green]Report saved to[/] [cyan]{output}[/]")
    else:
        console.print(Markdown(md))
```

**Step 2: Add entry point to pyproject.toml**

```toml
[project.scripts]
persona-lens = "persona_lens.cli:app"
persona-lens-agent = "persona_lens.agent.cli:app"
```

**Step 3: Commit**

```bash
git add persona_lens/agent/cli.py pyproject.toml
git commit -m "feat: add agent CLI entry point"
```

---

## Task 10: `agent/formatter.py` — Markdown report

**Files:**
- Create: `persona_lens/agent/formatter.py`

Create `persona_lens/agent/formatter.py`:

```python
from datetime import date
from typing import Any


def format_agent_report(result: dict[str, Any]) -> str:
    users = result.get("users", {})
    engagement = result.get("engagement", {})
    matches = result.get("matches", [])

    sections = [f"# KOL Batch Analysis Report\n\n*Generated {date.today()}*\n"]

    # Engagement insights
    if engagement:
        sections.append("## Insights\n")
        sections.append(engagement.get("insights", "") + "\n")
        patterns = engagement.get("patterns", [])
        if patterns:
            sections.append("\n**Key patterns:**\n")
            for p in patterns:
                sections.append(f"- **{p.get('type', '')}**: {p.get('description', '')}")
        sections.append("")

    # Per-user analysis
    sections.append("## Per-Account Analysis\n")
    for username, data in users.items():
        patterns = data.get("patterns", {})
        products = data.get("products", [])
        peak_days = patterns.get("peak_days", {})
        peak_hours = patterns.get("peak_hours", {})

        top_day = max(peak_days, key=peak_days.get) if peak_days else "N/A"
        top_hour = max(peak_hours, key=peak_hours.get) if peak_hours else "N/A"

        sections.append(f"### @{username}\n")
        sections.append(f"- **Peak posting**: {top_day}, {top_hour} UTC")
        if products:
            product_names = ", ".join(p["product"] for p in products[:8])
            sections.append(f"- **Products mentioned**: {product_names}")
            categories = list({p["category"] for p in products})
            sections.append(f"- **Categories**: {', '.join(categories)}")
        sections.append("")

    # Content matching
    if matches:
        sections.append("## Content Brief Matching\n")
        sections.append("| Content Brief | Best Fit | Reason |")
        sections.append("|---|---|---|")
        for m in matches:
            users_str = ", ".join(f"@{u}" for u in m.get("matched_users", []))
            brief = m.get("brief", "")[:50]
            reason = m.get("reason", "")
            sections.append(f"| {brief} | {users_str} | {reason} |")
        sections.append("")

    return "\n".join(sections)
```

**Smoke test:**

```bash
uv run python -c "
from persona_lens.agent.formatter import format_agent_report
md = format_agent_report({'users': {}, 'engagement': {}, 'matches': []})
print(md[:100])
"
```

**Commit:**

```bash
git add persona_lens/agent/formatter.py
git commit -m "feat: add agent report formatter"
```

---

## Task 11: Run full test suite

```bash
uv run pytest tests/ -v
```

Expected: all tests pass.

```bash
git add .
git commit -m "test: verify all unit tests pass"
```

---

## Task 12: End-to-end smoke test (requires Camofox + .env)

```bash
echo "karpathy" > /tmp/test_accounts.txt
uv run persona-lens-agent --accounts /tmp/test_accounts.txt --tweets 20
```

Expected: Markdown report printed to terminal with per-account section and insights.

If Camofox is not running, you will see:
`httpx.ConnectError: [Errno 61] Connection refused`

Start Camofox first: `npm start` in camofox-browser repo.

---

## Summary of LLM calls (total per run)

| Call | When | Purpose |
|------|------|---------|
| Agent loop calls | N (one per tool-call round) | Orchestration decisions |
| `analyze_products` | Once per user | Product extraction |
| `find_engagement_patterns` | Once total | Cross-account insights |
| `match_content_briefs` | Once (if briefs given) | Content matching |

**Total for 10 users + 3 briefs ≈ 10 + 10 + 1 + 1 = 22 LLM calls** (agent loop calls are lightweight, tools carry the real work).
