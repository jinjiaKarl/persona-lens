"""Unified per-user profile analyzer: products + engagement in one LLM call."""
import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.utils import llm_call_with_retry

SYSTEM_PROMPT = """You are a KOL analyst. Given tweets from a single user, perform a comprehensive profile analysis.

All output must be in English only.

Return JSON with key "profile" containing:
- products: list of {product, category, tweet_ids} objects
  category: infer the most appropriate category from context (e.g. "AI-Coding", "Hardware", "SaaS", etc.)
  Only include actual products/tools/services. Ignore vague references.
- writing_style: 2-3 sentence description of this user's writing style — tone, vocabulary, format preferences, and how they typically communicate with their audience.
- engagement: object with:
    top_posts: top 3 tweets by engagement, each {text, likes, retweets}
    insights: 1-2 sentence summary of what content or products drive the most engagement for this user"""


def analyze_user_profile(username: str, tweets: list[dict[str, Any]]) -> dict[str, Any]:
    """Single LLM call: extract products + engagement insights for one user."""
    if not tweets:
        return {"products": [], "writing_style": "", "engagement": {"top_posts": [], "insights": ""}}

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    tweet_lines = "\n".join(
        f'[ID:{t["id"]}] [{t.get("likes", 0)}L {t.get("retweets", 0)}RT] {t["text"]}'
        for t in tweets if t.get("text")
    )
    user_content = f"@{username} tweets ({len(tweets)} total):\n\n{tweet_lines}"

    response = llm_call_with_retry(
        client.chat.completions.create,
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    profile = data.get("profile", data)
    if isinstance(profile, str):
        return {"products": [], "engagement": {"top_posts": [], "insights": profile}}
    return profile
