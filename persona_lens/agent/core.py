"""Agent core: LLM tool-use loop that orchestrates the full KOL analysis.

Architecture:
  Phase 1 (LLM-driven): for each user, LLM calls fetch_and_analyze_user once.
    Raw snapshot stays in Python — LLM only sees a compact ~100-token summary.
    Agent core stores the full structured result internally.
  Phase 2 (direct Python): find_engagement_patterns and match_content_briefs
    called directly without LLM routing.
"""
import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from persona_lens.analyzers.product_analyzer import analyze_products
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns
from persona_lens.analyzers.content_matcher import match_content_briefs

SYSTEM_PROMPT = """You are a KOL analysis agent. For each username in the list,
call fetch_and_analyze_user once. Process one user at a time.
When all users are done, stop."""


def run_agent(
    usernames: list[str],
    briefs: list[str],
    tweet_count: int = 30,
) -> dict[str, Any]:
    """Run the KOL analysis agent. Returns structured result dict."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze these accounts: {usernames}. Fetch {tweet_count} tweets each."},
    ]

    all_user_data: dict[str, Any] = {}

    # Phase 1: LLM calls fetch_and_analyze_user once per user
    for _ in range(50):
        response = client.chat.completions.create(
            model="gpt-4o",
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            messages=messages,
        )
        msg = response.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            break

        for call in msg.tool_calls:
            fn_name = call.function.name
            fn_args = json.loads(call.function.arguments)
            fn = TOOL_FUNCTIONS.get(fn_name)

            if fn is None:
                tool_result: Any = {"error": f"Unknown tool: {fn_name}"}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(tool_result)})
                continue

            result = fn(**fn_args)

            # Store full structured data internally
            if fn_name == "fetch_and_analyze_user":
                username = fn_args.get("username", "")
                all_user_data[username] = result["_full"]
                # Return only compact summary to LLM context
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result["_summary"], ensure_ascii=False),
                })
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

    # Phase 2: direct Python calls — full structured data, no LLM serialization
    for username, data in all_user_data.items():
        data["products"] = analyze_products(username, data["tweets"])

    engagement_result: dict[str, Any] = {}
    if all_user_data:
        engagement_result = find_engagement_patterns(all_user_data)

    match_result: list[dict[str, Any]] = []
    if briefs and all_user_data:
        profiles = {
            u: {
                "writing_style": ", ".join(p["category"] for p in d.get("products", [])),
                "products": [p["product"] for p in d.get("products", [])],
            }
            for u, d in all_user_data.items()
        }
        match_result = match_content_briefs(briefs, profiles)

    return {
        "users": all_user_data,
        "engagement": engagement_result,
        "matches": match_result,
    }
