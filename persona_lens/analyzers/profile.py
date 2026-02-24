"""Unified per-user profile analyzer: products + engagement via a dedicated sub-agent."""
from typing import Any

from agents import Agent, Runner
from pydantic import BaseModel


class ProductItem(BaseModel):
    product: str
    category: str
    tweet_ids: list[str]


class TopPost(BaseModel):
    text: str
    likes: int
    retweets: int


class Engagement(BaseModel):
    top_posts: list[TopPost]
    insights: str


class UserProfile(BaseModel):
    products: list[ProductItem]
    writing_style: str
    engagement: Engagement


_INSTRUCTIONS = """You are a KOL analyst. Given tweets from a single user, perform a comprehensive profile analysis.

All output must be in English only.

Analyze and return:
- products: list of products/tools/services mentioned. Each has: product name, category (infer from context, e.g. "AI-Coding", "Hardware", "SaaS"), and tweet_ids. Only include actual products — ignore vague references.
- writing_style: 2-3 sentence description of tone, vocabulary, format preferences, and how they communicate with their audience.
- engagement: top 3 tweets by engagement (text, likes, retweets) and a 1-2 sentence insight on what drives the most engagement."""

profile_analyzer_agent = Agent(
    name="Profile Analyzer",
    instructions=_INSTRUCTIONS,
    model="gpt-4o",
    output_type=UserProfile,
)


async def analyze_user_profile(username: str, tweets: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the profile analyzer sub-agent and return a plain dict."""
    if not tweets:
        return {"products": [], "writing_style": "", "engagement": {"top_posts": [], "insights": ""}}

    tweet_lines = "\n".join(
        f'[ID:{t["id"]}] [{t.get("likes", 0)}L {t.get("retweets", 0)}RT] {t["text"]}'
        for t in tweets if t.get("text")
    )
    user_content = f"@{username} tweets ({len(tweets)} total):\n\n{tweet_lines}"

    result = await Runner.run(profile_analyzer_agent, input=user_content)
    return result.final_output.model_dump()
