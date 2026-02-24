"""FastAPI server exposing persona_lens analysis as SSE endpoints."""
import json
import os
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from persona_lens.platforms.x.fetcher import fetch_snapshot
from persona_lens.platforms.x.parser import extract_tweet_data, extract_user_info
from persona_lens.platforms.x.analyzer import analyze_user_profile
from persona_lens.utils.patterns import compute_posting_patterns

app = FastAPI(title="persona-lens API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    """Check that required env vars are set."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not set")
    return {"status": "ok"}


@app.post("/api/analyze/{username}")
async def analyze(username: str, tweets: int = 30):
    """Stream SSE events: progress stages then final result."""
    username = username.lstrip("@")

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
