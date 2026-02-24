"""Integration tests for agents.extensions.memory.SQLAlchemySession using SQLite in-memory."""

import pytest
import pytest_asyncio
from agents.extensions.memory import SQLAlchemySession
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    return SQLAlchemySession("test-session", engine=engine, create_tables=True)


async def test_empty_session_returns_no_items(session):
    assert await session.get_items() == []


async def test_add_and_get_items(session):
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    await session.add_items(msgs)
    assert await session.get_items() == msgs


async def test_get_items_preserves_order(session):
    msgs = [{"role": "user", "content": str(i)} for i in range(5)]
    await session.add_items(msgs)
    items = await session.get_items()
    assert [m["content"] for m in items] == ["0", "1", "2", "3", "4"]


async def test_get_items_with_limit(session):
    msgs = [{"role": "user", "content": str(i)} for i in range(5)]
    await session.add_items(msgs)
    items = await session.get_items(limit=2)
    # SDK returns the last N items in chronological order
    assert [m["content"] for m in items] == ["3", "4"]


async def test_add_items_across_calls(session):
    await session.add_items([{"role": "user", "content": "first"}])
    await session.add_items([{"role": "assistant", "content": "second"}])
    items = await session.get_items()
    assert len(items) == 2
    assert items[0]["content"] == "first"
    assert items[1]["content"] == "second"


async def test_pop_item_removes_last(session):
    await session.add_items([{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
    popped = await session.pop_item()
    assert popped["content"] == "b"
    remaining = await session.get_items()
    assert len(remaining) == 1
    assert remaining[0]["content"] == "a"


async def test_pop_item_on_empty_returns_none(session):
    assert await session.pop_item() is None


async def test_clear_session(session):
    await session.add_items([{"role": "user", "content": "x"}])
    await session.clear_session()
    assert await session.get_items() == []


async def test_sessions_are_isolated():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    s1 = SQLAlchemySession("session-1", engine=engine, create_tables=True)
    s2 = SQLAlchemySession("session-2", engine=engine, create_tables=False)
    await s1.add_items([{"role": "user", "content": "from s1"}])
    await s2.add_items([{"role": "user", "content": "from s2"}])
    assert await s1.get_items() == [{"role": "user", "content": "from s1"}]
    assert await s2.get_items() == [{"role": "user", "content": "from s2"}]


async def test_add_empty_list_is_noop(session):
    await session.add_items([])
    assert await session.get_items() == []
