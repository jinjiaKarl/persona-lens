"""Interactive agent loop: conversational KOL analysis."""
import json
import os
from typing import Any

from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data
from persona_lens.fetchers.patterns import compute_posting_patterns
from persona_lens.analyzers.user_profile_analyzer import analyze_user_profile

console = Console()

SYSTEM_PROMPT = """You are a KOL (Key Opinion Leader) analysis agent for X/Twitter.

You have one tool: fetch_and_analyze_user — use it to fetch and analyze a user's tweets.

Guidelines:
- When the user asks to analyze accounts, call the tool for each one.
- Once a user is analyzed, their data is in the conversation history — do NOT re-fetch them.
- Answer follow-up questions directly from the conversation context.
- Be concise and insightful.
- Reply in the same language as the user."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_and_analyze_user",
            "description": (
                "Fetch tweets for an X/Twitter user, extract structured data, "
                "compute posting patterns, and analyze products + engagement. "
                "Call once per username. Do not call again for already-analyzed users."
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
    """Full pipeline for one user. Returns full data + compact LLM summary."""
    snapshot = fetch_snapshot(username, tweet_count=tweet_count)
    tweets = extract_tweet_data(snapshot)
    patterns = compute_posting_patterns(tweets)
    profile = analyze_user_profile(username, tweets)

    peak_days = patterns.get("peak_days", {})
    peak_hours = patterns.get("peak_hours", {})
    top_day = max(peak_days, key=peak_days.get) if peak_days else "N/A"
    top_hour = max(peak_hours, key=peak_hours.get) if peak_hours else "N/A"
    products = profile.get("products", [])
    engagement = profile.get("engagement", {})

    full = {
        "username": username,
        "tweets": tweets,
        "patterns": patterns,
        "products": products,
        "engagement": engagement,
    }
    summary = {
        "username": username,
        "tweets_parsed": len(tweets),
        "peak_day": top_day,
        "peak_hour_utc": top_hour,
        "writing_style": profile.get("writing_style", ""),
        "products": [{"product": p["product"], "category": p["category"]} for p in products],
        "engagement_insights": engagement.get("insights", ""),
        "top_posts": engagement.get("top_posts", []),
    }
    return {"_full": full, "_summary": summary}


def run_interactive_loop(tweet_count: int = 30) -> None:
    """Start the interactive KOL analysis agent."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages: list[Any] = [{"role": "system", "content": SYSTEM_PROMPT}]
    analyzed_users: dict[str, Any] = {}

    console.print("[bold green]KOL Analysis Agent[/] [dim](type 'exit' to quit)[/]\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/]")
            break

        messages.append({"role": "user", "content": user_input})

        # Inner loop: keep going until LLM stops calling tools
        while True:
            response = client.chat.completions.create(
                model="gpt-4o",
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                messages=messages,
            )
            msg = response.choices[0].message
            messages.append(msg)

            if not msg.tool_calls:
                console.print(f"\n[bold cyan]Agent:[/]")
                console.print(Markdown(msg.content or ""))
                console.print()
                break

            for call in msg.tool_calls:
                fn_args = json.loads(call.function.arguments)
                username = fn_args.get("username", "").lstrip("@")

                if username in analyzed_users:
                    tool_content = {
                        **analyzed_users[username]["_summary"],
                        "note": "cached — already analyzed",
                    }
                else:
                    console.print(f"  [dim]→ Fetching @{username}...[/]")
                    result = _fetch_and_analyze_user(username, fn_args.get("tweet_count", tweet_count))
                    analyzed_users[username] = result
                    tool_content = result["_summary"]

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(tool_content, ensure_ascii=False),
                })
