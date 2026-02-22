"""Tool registry: OpenAI function schemas + Python function mapping."""
import json
from typing import Any

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data
from persona_lens.fetchers.patterns import compute_posting_patterns
from persona_lens.analyzers.product_analyzer import analyze_products
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns
from persona_lens.analyzers.content_matcher import match_content_briefs

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
    all_user_data = json.loads(user_data_json)
    return find_engagement_patterns(all_user_data)


def _match_content_briefs(briefs_json: str, profiles_json: str) -> list[dict[str, Any]]:
    briefs = json.loads(briefs_json)
    profiles = json.loads(profiles_json)
    return match_content_briefs(briefs, profiles)


TOOL_FUNCTIONS: dict[str, Any] = {
    "fetch_user_tweets": _fetch_user_tweets,
    "extract_and_analyze_user": _extract_and_analyze_user,
    "find_engagement_patterns": _find_engagement_patterns,
    "match_content_briefs": _match_content_briefs,
}
