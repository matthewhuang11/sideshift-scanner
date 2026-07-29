"""End-to-end test: calling an MCP tool the way an agent actually would
(mcp.call_tool, not importing the underlying function) logs to
agent_activity, since that's what the dashboard's activity feed reads."""

from __future__ import annotations

import asyncio

import pytest

from ugc_analytics.db import get_connection, init_db, recent_activity


@pytest.fixture
def mcp_env(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp_test.db"
    monkeypatch.setenv("UGC_ANALYTICS_DB_PATH", str(db_path))
    from ugc_analytics import server

    return server, db_path


def test_calling_a_tool_logs_agent_activity(mcp_env):
    server, db_path = mcp_env
    asyncio.run(server.mcp.call_tool("list_creators", {}))

    conn = get_connection(db_path)
    init_db(conn)
    entries = recent_activity(conn)
    conn.close()

    assert len(entries) == 1
    assert entries[0]["tool_name"] == "list_creators"


def test_multiple_tool_calls_logged_newest_first(mcp_env):
    server, db_path = mcp_env
    asyncio.run(server.mcp.call_tool("list_creators", {}))
    asyncio.run(server.mcp.call_tool("detect_trending_formats", {}))

    conn = get_connection(db_path)
    init_db(conn)
    entries = recent_activity(conn)
    conn.close()

    assert [e["tool_name"] for e in entries] == ["detect_trending_formats", "list_creators"]
