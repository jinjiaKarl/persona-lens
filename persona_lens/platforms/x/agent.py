"""X/Twitter platform: fetch_user and analyze_user tools + x_kol_agent."""
import json

from agents import Agent, ModelSettings, RunContextWrapper, function_tool
from rich.console import Console

from persona_lens.agent.context import AgentContext
from persona_lens.platforms.x.fetcher import fetch_snapshot
from persona_lens.platforms.x.parser import extract_tweet_data, extract_user_info
from persona_lens.utils.patterns import compute_posting_patterns
from persona_lens.platforms.x.analyzer import analyze_user_profile

console = Console()

KOL_SYSTEM_PROMPT = """You are a KOL (Key Opinion Leader) analysis agent for X/Twitter.

Tools: fetch_user (call first), then analyze_user.
- To analyze an account: always call fetch_user first, then analyze_user.
- Once analyzed, data is cached — do NOT re-fetch the same user.
- After you have the data, answer based on what the user actually asked:
  - If the user asks a specific question (e.g. follower count, bio, writing style,
    products, top posts), answer ONLY that question — concisely and directly.
  - If the user asks for a full analysis, overview, or does not specify what they
    want, output the complete profile summary.
- After completing analysis, inform the user they can ask for a structured report.
- Always reply in English."""


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
    x_cache = ctx.context.profile_cache.setdefault("x", {})
    if username in x_cache:
        n = len(x_cache[username]["tweets"])
        return f"Already fetched {n} tweets for @{username}."

    console.print(f"  [dim]→ Fetching @{username}...[/]")
    count = tweet_count or ctx.context.post_count
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
    x_cache[username] = {"tweets": tweets, "patterns": patterns, "user_info": user_info}
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
    x_analysis = ctx.context.analysis_cache.setdefault("x", {})

    if username in x_analysis:
        result = {**x_analysis[username], "note": "cached — already analyzed"}
        return json.dumps(result, ensure_ascii=False)

    x_cache = ctx.context.profile_cache.get("x", {})
    cached = x_cache.get(username)
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
    x_analysis[username] = summary
    return json.dumps(summary, ensure_ascii=False)


x_kol_agent = Agent[AgentContext](
    name="KOL X Analysis Agent",
    handoff_description="Specialist for fetching and analyzing X/Twitter user profiles, posting patterns, and engagement.",
    instructions=KOL_SYSTEM_PROMPT,
    model="gpt-4o",
    model_settings=ModelSettings(prompt_cache_retention="24h"),
    tools=[fetch_user, analyze_user],
)
