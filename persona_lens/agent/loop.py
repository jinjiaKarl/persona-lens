"""Interactive agent loop: conversational KOL analysis powered by OpenAI Agents SDK."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, Runner, RunContextWrapper, WebSearchTool, function_tool
from agents.extensions.memory import SQLAlchemySession
from openai.types.responses import ResponseTextDeltaEvent
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from sqlalchemy.ext.asyncio import create_async_engine

from persona_lens.fetchers.x import fetch_snapshot
from persona_lens.fetchers.tweet_parser import extract_tweet_data, extract_user_info
from persona_lens.fetchers.patterns import compute_posting_patterns
from persona_lens.analyzers.user_profile_analyzer import analyze_user_profile

console = Console()

MAIN_SYSTEM_PROMPT = """You are a helpful assistant.
- For general questions, use web_search to find up-to-date information.
- When the user asks to analyze an X/Twitter account or user, hand off to the KOL Analysis Agent.
- Always reply in English."""

KOL_SYSTEM_PROMPT = """You are a KOL (Key Opinion Leader) analysis agent for X/Twitter.

Tools: fetch_user (call first), then analyze_user.
- To analyze an account: call fetch_user, then analyze_user.
- Once analyzed, data is cached — do NOT re-fetch.
- Always reply in English."""


@dataclass
class AgentContext:
    tweet_cache: dict[str, dict] = field(default_factory=dict)
    analyzed_users: dict[str, Any] = field(default_factory=dict)
    tweet_count: int = 30


@function_tool
def fetch_user(
    ctx: RunContextWrapper[AgentContext],
    username: str,
    tweet_count: int = 30,
) -> str:
    """Fetch and cache tweets for an X/Twitter user. Must be called before analyze_user.

    Args:
        username: X username without @
        tweet_count: Number of tweets to fetch
    """
    username = username.lstrip("@")
    if username in ctx.context.tweet_cache:
        n = len(ctx.context.tweet_cache[username]["tweets"])
        return f"Already fetched {n} tweets for @{username}."

    console.print(f"  [dim]→ Fetching @{username}...[/]")
    count = tweet_count or ctx.context.tweet_count
    snapshot = fetch_snapshot(username, tweet_count=count)
    all_tweets = extract_tweet_data(snapshot)
    # Keep only tweets authored by this user (filter out retweets from others)
    tweets = [
        t for t in all_tweets
        if t.get("author") is None or t["author"].lstrip("@").lower() == username.lower()
    ]
    console.print_json(data=tweets)
    user_info = extract_user_info(snapshot, username)
    patterns = compute_posting_patterns(tweets)
    ctx.context.tweet_cache[username] = {"tweets": tweets, "patterns": patterns, "user_info": user_info}
    return f"Fetched {len(tweets)} tweets for @{username}. Call analyze_user next."


@function_tool
async def analyze_user(
    ctx: RunContextWrapper[AgentContext],
    username: str,
) -> str:
    """Analyze a previously fetched user's tweets: products, writing style, engagement.
    Requires fetch_user to be called first.

    Args:
        username: X username without @
    """
    username = username.lstrip("@")

    if username in ctx.context.analyzed_users:
        result = {**ctx.context.analyzed_users[username], "note": "cached — already analyzed"}
        return json.dumps(result, ensure_ascii=False)

    cached = ctx.context.tweet_cache.get(username)
    if not cached:
        return f"No tweets cached for @{username}. Call fetch_user first."

    console.print(f"  [dim]→ Analyzing @{username}...[/]")
    tweets = cached["tweets"]
    patterns = cached["patterns"]
    user_info = cached.get("user_info", {})
    profile = await analyze_user_profile(username, tweets)

    peak_days = patterns.get("peak_days", {})
    peak_hours = patterns.get("peak_hours", {})
    top_day = max(peak_days, key=peak_days.get) if peak_days else "N/A"
    top_hour = max(peak_hours, key=peak_hours.get) if peak_hours else "N/A"
    products = profile.get("products", [])
    engagement = profile.get("engagement", {})

    summary = {
        "username": username,
        "display_name": user_info.get("display_name", ""),
        "bio": user_info.get("bio", ""),
        "followers": user_info.get("followers", 0),
        "following": user_info.get("following", 0),
        "tweets_count": user_info.get("tweets_count", 0),
        "tweets_parsed": len(tweets),
        "peak_day": top_day,
        "peak_hour_utc": top_hour,
        "writing_style": profile.get("writing_style", ""),
        "products": [{"product": p["product"], "category": p["category"]} for p in products],
        "engagement_insights": engagement.get("insights", ""),
        "top_posts": engagement.get("top_posts", []),
    }
    ctx.context.analyzed_users[username] = summary
    return json.dumps(summary, ensure_ascii=False)


kol_agent = Agent[AgentContext](
    name="KOL X Analysis Agent",
    handoff_description="Specialist for fetching and analyzing X/Twitter user profiles, posting patterns, and engagement.",
    instructions=KOL_SYSTEM_PROMPT,
    model="gpt-4o",
    tools=[fetch_user, analyze_user],
)

main_agent = Agent[AgentContext](
    name="Assistant",
    instructions=MAIN_SYSTEM_PROMPT,
    model="gpt-4o",
    tools=[WebSearchTool()],
    handoffs=[kol_agent],
)


async def _run_loop(tweet_count: int = 30) -> None:
    ctx = AgentContext(tweet_count=tweet_count)
    # db_path = Path.home() / ".persona-lens" / "sessions.db"
    # db_path.parent.mkdir(parents=True, exist_ok=True)
    # engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    # In-memory session for testing
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    agent_session = SQLAlchemySession("kol-session", engine=engine, create_tables=True)
    prompt_session = PromptSession()

    console.print("[bold green]KOL Analysis Agent[/] [dim](type 'exit' to quit)[/]\n")

    while True:
        try:
            user_input = await prompt_session.prompt_async(HTML("<ansigreen><b>You</b></ansigreen>: "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye![/]")
            break

        result = Runner.run_streamed(
            main_agent,
            input=user_input,
            context=ctx,
            session=agent_session,
        )
        console.print("\n[bold cyan]Agent:[/]", end=" ")

        async for event in result.stream_events():
            if event.type == "raw_response_event":
                if isinstance(event.data, ResponseTextDeltaEvent):
                    print(event.data.delta, end="", flush=True)

        print("\n")


def run_interactive_loop(tweet_count: int = 30) -> None:
    """Start the interactive KOL analysis agent."""
    asyncio.run(_run_loop(tweet_count))
