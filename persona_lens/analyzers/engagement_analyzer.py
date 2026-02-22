import json
import os
from typing import Any

from openai import OpenAI

SYSTEM_PROMPT = """You are a social media analyst. Given engagement data for multiple KOL accounts, identify:
1. Which product types drive the highest engagement
2. Whether specific messaging patterns (comparison, personal experience, data-driven) correlate with higher engagement
3. Cross-account patterns

Return JSON with key "result" containing:
- insights: 2-3 sentence summary of key findings
- patterns: list of {type, description} objects (type: "product_type" | "messaging" | "timing")"""


def find_engagement_patterns(all_user_data: dict[str, Any]) -> dict[str, Any]:
    """Analyze high-engagement posts across all users to find patterns."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
