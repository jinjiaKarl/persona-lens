"""FastAPI server exposing persona_lens analysis as SSE endpoints."""
import json
import os
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import create_async_engine

from agents import Runner
from agents.extensions.memory import SQLAlchemySession
from openai.types.responses import ResponseTextDeltaEvent

from persona_lens.agent.context import AgentContext
from persona_lens.agent.loop import main_agent
from persona_lens.platforms.x.fetcher import fetch_snapshot
from persona_lens.platforms.x.parser import extract_tweet_data, extract_user_info
from persona_lens.platforms.x.analyzer import analyze_user_profile
from persona_lens.utils.patterns import compute_posting_patterns

app = FastAPI(title="persona-lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Per-session state ────────────────────────────────────────────────────────

_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_contexts: dict[str, AgentContext] = {}
_chat_sessions: dict[str, SQLAlchemySession] = {}


def get_context(session_id: str) -> AgentContext:
    """Return AgentContext for the given session, creating if needed."""
    if session_id not in _contexts:
        _contexts[session_id] = AgentContext()
    return _contexts[session_id]


async def get_chat_session(session_id: str) -> SQLAlchemySession:
    """Return SQLAlchemySession for the given session, creating if needed."""
    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = SQLAlchemySession(
            session_id, engine=_engine, create_tables=True
        )
    return _chat_sessions[session_id]


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    """Check that required env vars are set."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not set")
    return {"status": "ok"}


@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30, session_id: str = "default"):
    """Stream SSE events: progress stages then final result."""
    username = username.lstrip("@")
    ctx = get_context(session_id)

    async def _generate() -> AsyncGenerator[dict, None]:
        try:
            yield {
                "event": "progress",
                "data": json.dumps({"stage": "fetching", "message": "Fetching tweets\u2026"}),
            }
            snapshot = fetch_snapshot(username, tweet_count=tweets)
            all_tweets = extract_tweet_data(snapshot)
            user_tweets = [
                t for t in all_tweets
                if t.get("author") is None
                or t["author"].lstrip("@").lower() == username.lower()
            ]

            yield {
                "event": "progress",
                "data": json.dumps({
                    "stage": "parsing",
                    "message": f"Parsed {len(user_tweets)} tweets\u2026",
                }),
            }
            user_info = extract_user_info(snapshot, username)
            patterns = compute_posting_patterns(user_tweets)

            yield {
                "event": "progress",
                "data": json.dumps({"stage": "analyzing", "message": "Running AI analysis\u2026"}),
            }
            profile = await analyze_user_profile(username, user_tweets)

            # Sync into per-session AgentContext so the chat agent can reuse without re-fetching.
            # analysis_cache entry mirrors the summary dict built by analyze_user in agent.py.
            peak_days = patterns.get("peak_days", {})
            peak_hours = patterns.get("peak_hours", {})
            engagement = profile.get("engagement", {})
            products = profile.get("products", [])
            ctx.profile_cache.setdefault("x", {})[username] = {
                "tweets": user_tweets,
                "patterns": patterns,
                "user_info": user_info,
            }
            ctx.analysis_cache.setdefault("x", {})[username] = {
                "username": username,
                "display_name": user_info.get("display_name", ""),
                "bio": user_info.get("bio", ""),
                "followers": user_info.get("followers", 0),
                "following": user_info.get("following", 0),
                "tweets_count": user_info.get("tweets_count", 0),
                "tweets_parsed": len(user_tweets),
                "peak_day": max(peak_days, key=peak_days.get) if peak_days else "N/A",
                "peak_hour_utc": max(peak_hours, key=peak_hours.get) if peak_hours else "N/A",
                "writing_style": profile.get("writing_style", ""),
                "products": [{"product": p["product"], "category": p["category"]} for p in products],
                "engagement_insights": engagement.get("insights", ""),
                "top_posts": engagement.get("top_posts", []),
            }

            result = {
                "user_info": user_info,
                "tweets": user_tweets,
                "patterns": patterns,
                "analysis": profile,
            }
            yield {"event": "result", "data": json.dumps(result, ensure_ascii=False)}

        except Exception as exc:
            msg = str(exc)
            fix = ""
            if "9377" in msg or "camofox" in msg.lower() or "Connection" in msg:
                fix = "Start Camofox Browser: cd camofox-browser && npm start"
            elif "OPENAI_API_KEY" in msg:
                fix = "Set OPENAI_API_KEY in your .env file"
            yield {
                "event": "error",
                "data": json.dumps({"error": msg, "fix": fix}),
            }

    return EventSourceResponse(_generate())


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream chat responses from the main agent via SSE."""
    ctx = get_context(req.session_id)
    session = await get_chat_session(req.session_id)

    async def _generate() -> AsyncGenerator[dict, None]:
        # Snapshot which users are already analyzed before this turn
        before_analyses: set[str] = set(ctx.analysis_cache.get("x", {}).keys())

        try:
            result = Runner.run_streamed(
                main_agent,
                input=req.message,
                context=ctx,
                session=session,
            )

            async for event in result.stream_events():
                # Stream text tokens
                if event.type == "raw_response_event":
                    if isinstance(event.data, ResponseTextDeltaEvent):
                        delta = event.data.delta
                        if delta:
                            yield {
                                "event": "token",
                                "data": json.dumps({"delta": delta}),
                            }
                # Show tool activity
                elif event.type == "run_item_stream_event":
                    item = event.item
                    item_type = getattr(item, "type", "")
                    if item_type == "tool_call_item":
                        raw = getattr(item, "raw_item", None)
                        tool_name = getattr(raw, "name", "") if raw else ""
                        if tool_name:
                            yield {
                                "event": "tool_call",
                                "data": json.dumps({"tool": tool_name, "status": "running"}),
                            }

            # After agent finishes: emit analysis_result for newly analyzed users.
            # The agent stores a flat summary in analysis_cache; reconstruct the
            # nested structure expected by the frontend's AnalysisResult type.
            after_analyses: set[str] = set(ctx.analysis_cache.get("x", {}).keys())
            new_users = after_analyses - before_analyses
            for username in new_users:
                x_profile = ctx.profile_cache.get("x", {}).get(username, {})
                x_summary = ctx.analysis_cache["x"][username]
                if x_profile:
                    analysis = {
                        "products": x_summary.get("products", []),
                        "writing_style": x_summary.get("writing_style", ""),
                        "engagement": {
                            "top_posts": x_summary.get("top_posts", []),
                            "insights": x_summary.get("engagement_insights", ""),
                        },
                    }
                    yield {
                        "event": "analysis_result",
                        "data": json.dumps({
                            "user_info": x_profile.get("user_info", {}),
                            "tweets": x_profile.get("tweets", []),
                            "patterns": x_profile.get("patterns", {}),
                            "analysis": analysis,
                        }, ensure_ascii=False),
                    }

            yield {"event": "done", "data": "{}"}

        except Exception as exc:
            msg = str(exc)
            fix = ""
            if "9377" in msg or "camofox" in msg.lower() or "Connection" in msg:
                fix = "Start Camofox Browser: cd camofox-browser && npm start"
            elif "OPENAI_API_KEY" in msg:
                fix = "Set OPENAI_API_KEY in your .env file"
            yield {
                "event": "error",
                "data": json.dumps({"error": msg, "fix": fix}),
            }

    return EventSourceResponse(_generate())
