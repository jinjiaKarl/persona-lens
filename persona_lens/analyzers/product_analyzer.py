import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.utils import llm_call_with_retry

SYSTEM_PROMPT = """You are a product intelligence analyst. Given a list of tweets, extract all product or tool mentions.

For each product found, return a JSON array with objects:
- product: product name (string)
- category: one of "AI-Coding", "AI-Writing", "AI-Image", "AI-Video", "AI-Agent", "SaaS", "Hardware/Consumer Electronics", "Dev Tools", "Other"
- tweet_ids: list of tweet IDs that mention this product

Only include actual products/tools/services. Ignore vague references.
All output must be in English only.
Return JSON with key 'products' containing the array."""


def analyze_products(username: str, tweets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract product mentions from tweets using a single LLM call."""
    if not tweets:
        return []

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    tweet_lines = "\n".join(
        f'[ID:{t["id"]}] {t["text"]}' for t in tweets if t.get("text")
    )
    user_content = f"Tweets from @{username}:\n\n{tweet_lines}"

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
    return data.get("products", [])
