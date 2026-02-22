import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.utils import llm_call_with_retry

SYSTEM_PROMPT = """You are a content strategy expert. Given a list of content briefs and influencer profiles, match each brief to the most suitable influencers.

For each brief, return which users best fit based on their writing style, tone, and past product mentions.

All output must be in English only.

Return JSON with key "matches" containing a list of:
- brief: the content brief text
- matched_users: list of usernames (best fit first, max 3)
- reason: 1-2 sentence explanation of why they fit (English only)"""


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
    return data.get("matches", [])
