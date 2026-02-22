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

    messages: list[Any] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_description},
    ]

    all_user_data: dict[str, Any] = {}
    engagement_result: dict[str, Any] = {}
    match_result: list[dict[str, Any]] = []
    last_msg_content = ""

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
            last_msg_content = msg.content or ""
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
        "summary": last_msg_content,
    }
