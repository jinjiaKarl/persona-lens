"""Agent core: LLM tool-use loop that orchestrates the full KOL analysis.

Architecture:
  Phase 1 (LLM-driven): for each user, LLM calls fetch_user_tweets then
    extract_and_analyze_user. The agent collects results internally.
  Phase 2 (direct Python): find_engagement_patterns and match_content_briefs
    are called directly — no LLM routing — to avoid large data serialization
    through tool arguments.
"""
import json
import os
from typing import Any

from openai import OpenAI

from persona_lens.agent.tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from persona_lens.analyzers.engagement_analyzer import find_engagement_patterns
from persona_lens.analyzers.content_matcher import match_content_briefs

SYSTEM_PROMPT = """You are a KOL (Key Opinion Leader) analysis agent for X/Twitter.

Your job: for each username in the list, call fetch_user_tweets then immediately
call extract_and_analyze_user with the returned snapshot. Process one user at a
time. When all users are done, stop — do not call any other tools."""


def run_agent(
    usernames: list[str],
    briefs: list[str],
    tweet_count: int = 30,
) -> dict[str, Any]:
    """Run the KOL analysis agent. Returns structured result dict."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    task_description = (
        f"Analyze these X/Twitter accounts one by one: {usernames}. "
        f"Fetch {tweet_count} tweets each."
    )

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_description},
    ]

    all_user_data: dict[str, Any] = {}

    # Phase 1: LLM drives per-user fetch + analyze
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
                result: Any = {"error": f"Unknown tool: {fn_name}"}
            else:
                result = fn(**fn_args)

            if fn_name == "extract_and_analyze_user":
                username = fn_args.get("username", "")
                all_user_data[username] = result

            # fetch_user_tweets: return full result so LLM can pass snapshot to next tool
            # extract_and_analyze_user: return compact ack (avoid token bloat)
            if fn_name == "fetch_user_tweets":
                tool_content = json.dumps(result, ensure_ascii=False)
            else:
                tool_content = json.dumps({"status": "ok", "username": fn_args.get("username", "")}, ensure_ascii=False)

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": tool_content,
            })

    # Phase 2: direct Python calls — no LLM routing, no data serialization risk
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
