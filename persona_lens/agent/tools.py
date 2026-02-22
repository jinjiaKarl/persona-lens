"""Tool registry: OpenAI function schemas + Python function mapping.

Single tool exposed to the LLM: fetch_and_analyze_user.

The raw Nitter snapshot never enters the LLM context — it is fetched,
parsed into structured JSON, and analyzed entirely within Python. The LLM
only receives a compact summary (~100 tokens) as the tool result.
"""
from typing import Any

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data
from persona_lens.fetchers.patterns import compute_posting_patterns

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_and_analyze_user",
            "description": (
                "Fetch tweets for one X/Twitter user, extract structured data "
                "(tweet text, likes, retweets, timestamps), compute posting patterns, "
                "and identify product mentions. Call once per username."
            ),
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
]


def _fetch_and_analyze_user(username: str, tweet_count: int = 30) -> dict[str, Any]:
    """Fetch + parse + analyze a single user entirely in Python.

    The raw snapshot never leaves this function.
    Returns structured data stored by the agent core; returns a compact
    summary to the LLM context.
    """
    snapshot = fetch_snapshot(username, tweet_count=tweet_count)
    tweets = extract_tweet_data(snapshot)
    patterns = compute_posting_patterns(tweets)

    # Full structured result (kept internally by agent core)
    full = {
        "username": username,
        "tweets": tweets,
        "patterns": patterns,
    }

    # Compact summary returned to LLM (avoids token bloat)
    peak_days = patterns.get("peak_days", {})
    peak_hours = patterns.get("peak_hours", {})
    top_day = max(peak_days, key=peak_days.get) if peak_days else "N/A"
    top_hour = max(peak_hours, key=peak_hours.get) if peak_hours else "N/A"
    summary = {
        "username": username,
        "tweets_parsed": len(tweets),
        "peak_day": top_day,
        "peak_hour_utc": top_hour,
    }

    return {"_full": full, "_summary": summary}


TOOL_FUNCTIONS: dict[str, Any] = {
    "fetch_and_analyze_user": _fetch_and_analyze_user,
}
