"""Smoke tests calling tools through the real MCP protocol path
(mcp.call_tool), not just importing the underlying functions -- this is
what an agentic coding tool actually does when it uses this server."""

from __future__ import annotations

import asyncio

import pytest

from tests.conftest import SAMPLE_DATA_DIR


@pytest.fixture
def mcp_env(tmp_path, monkeypatch):
    db_path = tmp_path / "mcp_test.db"
    monkeypatch.setenv("UGC_ANALYTICS_DB_PATH", str(db_path))
    from ugc_analytics import server

    return server


def test_all_tools_are_registered(mcp_env):
    tools = asyncio.run(mcp_env.mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "sync_data",
        "list_creators",
        "get_creator_profile",
        "get_performance_summary",
        "top_performers",
        "detect_trending_formats",
        "recommend_creators_for_brief",
        "generate_content_brief",
    }


def test_sync_then_query_via_call_tool(mcp_env):
    asyncio.run(mcp_env.mcp.call_tool("sync_data", {"method": "csv", "source": str(SAMPLE_DATA_DIR)}))
    result = asyncio.run(mcp_env.mcp.call_tool("list_creators", {}))
    assert result.structured_content["result"]
    assert len(result.structured_content["result"]) == 5
