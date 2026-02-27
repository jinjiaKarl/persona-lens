"""FastAPI server exposing persona_lens analysis as SSE endpoints."""
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()
from typing import AsyncGenerator

import aiosqlite
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import create_async_engine

from agents import Runner
from openai.types.responses import ResponseTextDeltaEvent

from persona_lens.agent.context import AgentContext
from persona_lens.agent.loop import main_agent
from persona_lens.api.session_backend import make_session
from persona_lens.platforms.x.fetcher import fetch_snapshot
from persona_lens.platforms.x.parser import extract_tweet_data, extract_user_info
from persona_lens.platforms.x.analyzer import analyze_user_profile
from persona_lens.utils.patterns import compute_posting_patterns

app = FastAPI(title="persona-lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# ── Database ─────────────────────────────────────────────────────────────────
# Schema is user_id → session_id → username to support multi-tenancy.
# user_id defaults to "default" until auth is wired in.

DB_PATH = os.getenv("DB_PATH", "persona_lens.db")
_engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")


@app.on_event("startup")
async def _create_tables() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_results (
                user_id     TEXT NOT NULL DEFAULT 'default',
                session_id  TEXT NOT NULL,
                username    TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (user_id, session_id, username)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id    TEXT NOT NULL DEFAULT 'default',
                session_id TEXT NOT NULL,
                title      TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, session_id)
            )
        """)
        await db.commit()

    backend = os.getenv("SESSION_BACKEND", "sqlite").lower()
    if backend == "acontext":
        base_url = os.getenv("ACONTEXT_BASE_URL", "https://api.acontext.app/api/v1")
        print(f"[session] backend=acontext  url={base_url}")
    else:
        print(f"[session] backend=sqlite  db={DB_PATH}")


async def _save_profile(user_id: str, session_id: str, username: str, result: dict) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO profile_results
               (user_id, session_id, username, result_json) VALUES (?, ?, ?, ?)""",
            (user_id, session_id, username, json.dumps(result, ensure_ascii=False)),
        )
        await db.commit()


async def _load_profiles(user_id: str, session_id: str) -> dict[str, dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, result_json FROM profile_results WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ) as cursor:
            rows = await cursor.fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


async def _create_session(user_id: str, session_id: str, title: str, created_at: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sessions (user_id, session_id, title, created_at) VALUES (?, ?, ?, ?)",
            (user_id, session_id, title, created_at),
        )
        await db.commit()
    return {"user_id": user_id, "session_id": session_id, "title": title, "created_at": created_at}


async def _list_sessions(user_id: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT session_id, title, created_at FROM sessions WHERE user_id = ? ORDER BY created_at ASC",
            (user_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"session_id": r[0], "title": r[1], "created_at": r[2]} for r in rows]


async def _rename_session(user_id: str, session_id: str, title: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE sessions SET title = ? WHERE user_id = ? AND session_id = ?",
            (title, user_id, session_id),
        )
        # Check rowcount before commit to detect missing session without a separate SELECT.
        if cursor.rowcount == 0:
            return None
        await db.commit()
        async with db.execute(
            "SELECT session_id, title, created_at FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return {"session_id": row[0], "title": row[1], "created_at": row[2]}


async def _delete_session(user_id: str, session_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sessions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        await db.execute(
            "DELETE FROM profile_results WHERE user_id = ? AND session_id = ?",
            (user_id, session_id),
        )
        await db.commit()


def _items_to_display_messages(items: list) -> list[dict]:
    """Convert TResponseInputItem objects to frontend-displayable message dicts."""
    messages = []
    pending_tool_calls: list[dict] = []

    for item in items:
        # Items may be Pydantic models or plain dicts — normalise to dict.
        if hasattr(item, "model_dump"):
            item = item.model_dump()

        item_type = item.get("type", "")

        # Handle both typed messages {"type": "message", "role": "..."} and
        # EasyInputMessageParam (no "type" field) {"role": "user", "content": "..."}.
        if item_type == "message" or (not item_type and "role" in item):
            role = item.get("role", "")
            content = item.get("content", "")

            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "".join(
                    part.get("text", "")
                    for part in content
                    if part.get("type") in ("text", "input_text", "output_text")
                )
            else:
                text = ""

            if not text:
                continue

            if role == "user":
                messages.append({"role": "user", "content": text, "toolCalls": []})
                pending_tool_calls = []
            elif role in ("assistant", "agent"):
                messages.append({
                    "role": "agent",
                    "content": text,
                    "toolCalls": pending_tool_calls,
                })
                pending_tool_calls = []

        elif item_type == "function_call":
            name = item.get("name", "")
            if name:
                pending_tool_calls.append({"tool": name, "status": "done"})
        # function_call_output and other internal items are skipped

    return messages


# ── Per-session in-memory state ───────────────────────────────────────────────
# Keyed by "user_id:session_id" to ensure isolation across tenants.

_contexts: dict[str, AgentContext] = {}


def _ctx_key(user_id: str, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def get_context(user_id: str, session_id: str) -> AgentContext:
    key = _ctx_key(user_id, session_id)
    if key not in _contexts:
        _contexts[key] = AgentContext()
    return _contexts[key]


def _warm_context(ctx: AgentContext, username: str, result: dict) -> None:
    """Restore a stored profile result into an AgentContext cache."""
    user_info = result.get("user_info", {})
    patterns = result.get("patterns", {})
    analysis = result.get("analysis", {})
    tweets = result.get("tweets", [])
    engagement = analysis.get("engagement", {})
    peak_days = patterns.get("peak_days", {})
    peak_hours = patterns.get("peak_hours", {})
    ctx.profile_cache.setdefault("x", {})[username] = {
        "tweets": tweets,
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
        "tweets_parsed": len(tweets),
        "peak_day": max(peak_days, key=peak_days.get) if peak_days else "N/A",
        "peak_hour_utc": max(peak_hours, key=peak_hours.get) if peak_hours else "N/A",
        "writing_style": analysis.get("writing_style", ""),
        "products": analysis.get("products", []),
        "engagement_insights": engagement.get("insights", ""),
        "top_posts": engagement.get("top_posts", []),
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    session_id: str
    title: str = Field(max_length=30)


class RenameSessionRequest(BaseModel):
    title: str = Field(max_length=30)


@app.get("/api/users/{user_id}/sessions")
async def list_sessions(user_id: str):
    """List all sessions for a user, ordered by creation time."""
    return await _list_sessions(user_id)


@app.post("/api/users/{user_id}/sessions")
async def create_session(user_id: str, req: CreateSessionRequest):
    """Create a new session. Idempotent — ignores duplicate session_id."""
    return await _create_session(user_id, req.session_id, req.title, int(time.time() * 1000))


@app.patch("/api/users/{user_id}/sessions/{session_id}")
async def rename_session(user_id: str, session_id: str, req: RenameSessionRequest):
    """Rename an existing session."""
    result = await _rename_session(user_id, session_id, req.title)
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


@app.delete("/api/users/{user_id}/sessions/{session_id}")
async def delete_session(user_id: str, session_id: str):
    """Delete a session and all its stored profiles."""
    await _delete_session(user_id, session_id)
    return {"deleted": session_id}


@app.get("/api/users/{user_id}/sessions/{session_id}/messages")
async def get_chat_history(user_id: str, session_id: str):
    """Return the full chat history for a session in display format."""
    session = make_session(_ctx_key(user_id, session_id), engine=_engine, user_id=user_id, session_id=session_id)
    history = await session.get_history()
    return _items_to_display_messages(history)


@app.get("/api/sessions/{session_id}/profiles")
async def get_profiles(session_id: str, user_id: str = "default"):
    """Return all stored analysis results for a session, warming the AgentContext cache."""
    profiles = await _load_profiles(user_id, session_id)
    if profiles:
        ctx = get_context(user_id, session_id)
        for username, result in profiles.items():
            _warm_context(ctx, username, result)
    return profiles


@app.get("/api/health")
def health():
    """Check that required env vars are set."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not set")
    return {"status": "ok"}


@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30, session_id: str = "default", user_id: str = "default"):
    """Stream SSE events: progress stages then final result."""
    username = username.lstrip("@")
    ctx = get_context(user_id, session_id)

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

            # Sync into AgentContext so the chat agent can reuse without re-fetching.
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
            await _save_profile(user_id, session_id, username, result)
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
    user_id: str = "default"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Stream chat responses from the main agent via SSE."""
    ctx = get_context(req.user_id, req.session_id)
    session = make_session(_ctx_key(req.user_id, req.session_id), engine=_engine, user_id=req.user_id, session_id=req.session_id)

    async def _generate() -> AsyncGenerator[dict, None]:
        before_analyses: set[str] = set(ctx.analysis_cache.get("x", {}).keys())

        try:
            # 1. Load history, build full input.
            history = await session.get_history()
            full_input = list(history) + [{"role": "user", "content": req.message}]
            history_len = len(history)

            # 2. Run agent (no session= arg — we manage history manually).
            result = Runner.run_streamed(
                main_agent,
                input=full_input,
                context=ctx,
            )

            # 3. Stream events.
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    if isinstance(event.data, ResponseTextDeltaEvent):
                        delta = event.data.delta
                        if delta:
                            yield {
                                "event": "token",
                                "data": json.dumps({"delta": delta}),
                            }
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

            # 4. Persist new turn (user msg + agent response).
            all_items = result.to_input_list()
            new_items = all_items[history_len:]  # slice off prior history
            await session.save_messages(new_items)

            # 5. Emit analysis_result for newly analyzed users and persist them.
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
                    profile_result = {
                        "user_info": x_profile.get("user_info", {}),
                        "tweets": x_profile.get("tweets", []),
                        "patterns": x_profile.get("patterns", {}),
                        "analysis": analysis,
                    }
                    await _save_profile(req.user_id, req.session_id, username, profile_result)
                    yield {
                        "event": "analysis_result",
                        "data": json.dumps(profile_result, ensure_ascii=False),
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
