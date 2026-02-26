"""Tests for session CRUD endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from persona_lens.api.server import app, DB_PATH
import aiosqlite

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def clean_sessions():
    """Wipe sessions table before each test; ensure profile_results exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id    TEXT NOT NULL DEFAULT 'default',
                session_id TEXT NOT NULL,
                title      TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, session_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_results (
                user_id     TEXT NOT NULL DEFAULT 'default',
                session_id  TEXT NOT NULL,
                username    TEXT NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (user_id, session_id, username)
            )
        """)
        await db.execute("DELETE FROM sessions")
        await db.commit()
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_sessions_empty(client):
    r = await client.get("/api/users/default/sessions")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_session(client):
    r = await client.post(
        "/api/users/default/sessions",
        json={"session_id": "s1", "title": "Chat 1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "s1"
    assert data["title"] == "Chat 1"
    assert "created_at" in data


async def test_list_sessions_returns_created(client):
    await client.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
    r = await client.get("/api/users/default/sessions")
    assert len(r.json()) == 1
    assert r.json()[0]["session_id"] == "s1"


async def test_rename_session(client):
    await client.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
    r = await client.patch("/api/users/default/sessions/s1", json={"title": "@karpathy"})
    assert r.status_code == 200
    assert r.json()["title"] == "@karpathy"


async def test_delete_session(client):
    await client.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
    r = await client.delete("/api/users/default/sessions/s1")
    assert r.status_code == 200
    sessions = (await client.get("/api/users/default/sessions")).json()
    assert sessions == []


async def test_delete_session_also_removes_profiles(client):
    """Deleting a session should cascade-delete its profile_results rows."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO profile_results (user_id, session_id, username, result_json) VALUES (?, ?, ?, ?)",
            ("default", "s1", "karpathy", "{}"),
        )
        await db.commit()
    await client.post("/api/users/default/sessions", json={"session_id": "s1", "title": "Chat 1"})
    await client.delete("/api/users/default/sessions/s1")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM profile_results WHERE session_id = ?", ("s1",)
        ) as cur:
            count = (await cur.fetchone())[0]
    assert count == 0


async def test_sessions_isolated_across_users(client):
    await client.post("/api/users/user-a/sessions", json={"session_id": "s1", "title": "A"})
    r = await client.get("/api/users/user-b/sessions")
    assert r.json() == []
