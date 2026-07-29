"""MCP server exposing the tools listed in docs/build-spec.md section 6."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from ugc_analytics.analysis.briefs import generate_content_brief as _generate_content_brief
from ugc_analytics.analysis.matching import recommend_creators_for_brief as _recommend_creators_for_brief
from ugc_analytics.analysis.performance import get_performance_summary as _get_performance_summary
from ugc_analytics.analysis.performance import top_performers as _top_performers
from ugc_analytics.analysis.profiling import get_creator_profile as _get_creator_profile
from ugc_analytics.analysis.profiling import list_creators as _list_creators
from ugc_analytics.analysis.trends import detect_trending_formats as _detect_trending_formats
from ugc_analytics.db import DEFAULT_DB_PATH, get_connection, init_db
from ugc_analytics.ingestion.api_adapter import SideShiftAPIAdapter
from ugc_analytics.ingestion.base import sync_all
from ugc_analytics.ingestion.csv_adapter import CSVIngestionAdapter

load_dotenv()

mcp = MCPServer("sideshift-scanner")


def _db_path() -> Path:
    return Path(os.environ.get("UGC_ANALYTICS_DB_PATH", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    conn = get_connection(_db_path())
    init_db(conn)
    return conn


@mcp.tool()
def sync_data(method: str = "csv", source: str = "sample_data", since: str | None = None) -> dict:
    """Pull latest data via the active ingestion adapter and upsert into the local store.

    method='csv': `source` is a directory containing creators.csv / campaigns.csv /
      content_items.csv / performance_metrics.csv (see sample_data/).
    method='api': pulls from the real SideShift API. Requires the SIDESHIFT_API_KEY
      env var (Settings -> Integrations in the SideShift dashboard).
    `since` (YYYY-MM-DD) limits ingestion to records on/after that date.
    """
    from datetime import date

    since_date = date.fromisoformat(since) if since else None
    conn = _connect()
    try:
        if method == "csv":
            adapter = CSVIngestionAdapter(source)
        elif method == "api":
            api_key = os.environ.get("SIDESHIFT_API_KEY")
            if not api_key:
                raise ValueError("SIDESHIFT_API_KEY env var is required for method='api'.")
            adapter = SideShiftAPIAdapter(api_key=api_key)
        else:
            raise ValueError(f"Unknown method '{method}'. Use 'csv' or 'api'.")
        result = sync_all(conn, adapter, since_date)
        return asdict(result)
    finally:
        conn.close()


@mcp.tool()
def list_creators(niche: str | None = None, platform: str | None = None, status: str | None = None) -> list[dict]:
    """List creators, optionally filtered by niche tag, platform, or status."""
    conn = _connect()
    try:
        return _list_creators(conn, niche=niche, platform=platform, status=status)
    finally:
        conn.close()


@mcp.tool()
def get_creator_profile(creator_id: str | None = None, handle: str | None = None) -> dict | None:
    """Full creator profile: niche, style, platforms, performance history, best formats."""
    conn = _connect()
    try:
        profile = _get_creator_profile(conn, creator_id=creator_id, handle=handle)
        return asdict(profile) if profile else None
    finally:
        conn.close()


@mcp.tool()
def get_performance_summary(
    scope: str = "global",
    scope_id: str | None = None,
    date_range_start: str | None = None,
    date_range_end: str | None = None,
) -> dict:
    """Aggregate metrics + trend direction.

    scope: 'global' | 'creator' | 'campaign' | 'format'. scope_id required unless scope='global'.
    """
    date_range = (date_range_start, date_range_end) if date_range_start and date_range_end else None
    conn = _connect()
    try:
        return asdict(_get_performance_summary(conn, scope=scope, scope_id=scope_id, date_range=date_range))
    finally:
        conn.close()


@mcp.tool()
def top_performers(
    metric: str = "views",
    n: int = 10,
    date_range_start: str | None = None,
    date_range_end: str | None = None,
) -> list[dict]:
    """Ranked content items by a chosen metric (views/likes/comments/shares/saves/conversions/revenue/engagement_rate)."""
    date_range = (date_range_start, date_range_end) if date_range_start and date_range_end else None
    conn = _connect()
    try:
        return _top_performers(conn, metric=metric, n=n, date_range=date_range)
    finally:
        conn.close()


@mcp.tool()
def detect_trending_formats(
    metric: str = "engagement_rate",
    min_sample_size: int = 2,
    date_range_start: str | None = None,
    date_range_end: str | None = None,
) -> list[dict]:
    """Format/hook tags whose average performance beats the roster baseline, ranked by multiplier."""
    date_range = (date_range_start, date_range_end) if date_range_start and date_range_end else None
    conn = _connect()
    try:
        trends = _detect_trending_formats(conn, metric=metric, min_sample_size=min_sample_size, date_range=date_range)
        return [asdict(t) for t in trends]
    finally:
        conn.close()


@mcp.tool()
def recommend_creators_for_brief(
    brief_text: str | None = None, format_tags: list[str] | None = None, n: int = 5
) -> list[dict]:
    """Rank active creators for a brief or set of format tags, with rationale for each match."""
    conn = _connect()
    try:
        return _recommend_creators_for_brief(conn, brief_text=brief_text, format_tags=format_tags, n=n)
    finally:
        conn.close()


@mcp.tool()
def generate_content_brief(creator_id: str, based_on_format: str | None = None) -> dict:
    """Draft a brief tailored to a creator's style, targeting a given or trending format."""
    conn = _connect()
    try:
        return asdict(_generate_content_brief(conn, creator_id=creator_id, based_on_format=based_on_format))
    finally:
        conn.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
