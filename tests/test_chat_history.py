"""Tests for GET /api/users/{user_id}/sessions/{session_id}/messages endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport
from persona_lens.api.server import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_empty_history_returns_empty_list(client):
    """New session with no messages returns []."""
    async with client as c:
        r = await c.get("/api/users/default/sessions/brand-new-session/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_history_converts_user_and_agent_messages(client):
    """Simulate the SDK storing messages, then verify the endpoint converts them."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("default", "hist-test-1")
    # Clear any stale data from previous runs before testing.
    await session.clear_session()
    # Add a user message and an assistant response the same way the SDK does
    await session.add_items([
        {"type": "message", "role": "user", "content": "Hello"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi there!"}]},
    ])

    async with client as c:
        r = await c.get("/api/users/default/sessions/hist-test-1/messages")
    data = r.json()
    assert len(data) == 2
    assert data[0] == {"role": "user", "content": "Hello", "toolCalls": []}
    assert data[1] == {"role": "agent", "content": "Hi there!", "toolCalls": []}

    # Cleanup
    await session.clear_session()


async def test_history_attaches_tool_calls_to_agent_message(client):
    """Tool call items should be collected and attached to the following agent message."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("default", "hist-test-2")
    # Clear any stale data from previous runs before testing.
    await session.clear_session()
    await session.add_items([
        {"type": "message", "role": "user", "content": "Analyze @karpathy"},
        {"type": "function_call", "name": "fetch_user", "call_id": "c1", "arguments": "{}"},
        {"type": "function_call", "name": "analyze_user", "call_id": "c2", "arguments": "{}"},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done!"}]},
    ])

    async with client as c:
        r = await c.get("/api/users/default/sessions/hist-test-2/messages")
    data = r.json()
    assert len(data) == 2
    assert data[0]["role"] == "user"
    assert data[1]["role"] == "agent"
    assert data[1]["content"] == "Done!"
    assert len(data[1]["toolCalls"]) == 2
    assert data[1]["toolCalls"][0] == {"tool": "fetch_user", "status": "done"}
    assert data[1]["toolCalls"][1] == {"tool": "analyze_user", "status": "done"}

    await session.clear_session()


async def test_history_isolated_across_users(client):
    """Messages for user-a are not visible to user-b."""
    from persona_lens.api.server import get_chat_session

    session = await get_chat_session("user-a", "shared-session")
    # Clear any stale data from previous runs before testing.
    await session.clear_session()
    await session.add_items([
        {"type": "message", "role": "user", "content": "Secret"},
    ])

    async with client as c:
        r = await c.get("/api/users/user-b/sessions/shared-session/messages")
    assert r.json() == []

    await session.clear_session()
