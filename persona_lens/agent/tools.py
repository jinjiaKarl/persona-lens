"""Tool registry: OpenAI function schemas + Python function mapping.

Only fetch_user_tweets and extract_and_analyze_user are exposed as LLM tools.
find_engagement_patterns and match_content_briefs are called directly by
agent/core.py after the LLM loop completes — avoiding large data serialization
through LLM tool arguments.
"""
from typing import Any

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data
from persona_lens.fetchers.patterns import compute_posting_patterns
from persona_lens.analyzers.product_analyzer import analyze_products

# Tools exposed to the LLM — only the per-user fetch+analyze pair
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
]


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


TOOL_FUNCTIONS: dict[str, Any] = {
    "fetch_user_tweets": _fetch_user_tweets,
    "extract_and_analyze_user": _extract_and_analyze_user,
}
