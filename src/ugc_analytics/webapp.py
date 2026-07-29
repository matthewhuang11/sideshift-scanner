"""Local read-only dashboard on top of the analysis engine (build spec
section 9, Phase 4 stretch: "a simple dashboard artifact view on top of
the MCP data").

Run with:
    python -m ugc_analytics.webapp
    (or the `sideshift-scanner-web` entry point once installed)

Opens on http://127.0.0.1:8420. Single user, no auth, no accounts —
this reads the same local SQLite store the MCP server and CLI use.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from ugc_analytics.analysis.performance import get_performance_summary, top_performers
from ugc_analytics.analysis.profiling import get_creator_profile, list_creators
from ugc_analytics.analysis.trends import detect_trending_formats
from ugc_analytics.db import DEFAULT_DB_PATH, get_connection, init_db
from ugc_analytics.ingestion.api_adapter import SideShiftAPIAdapter
from ugc_analytics.ingestion.base import sync_all
from ugc_analytics.ingestion.csv_adapter import CSVIngestionAdapter

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="SideShift Scanner")


def _db_path() -> Path:
    return Path(os.environ.get("UGC_ANALYTICS_DB_PATH", DEFAULT_DB_PATH))


def _connect() -> sqlite3.Connection:
    conn = get_connection(_db_path())
    init_db(conn)
    return conn


@app.get("/api/summary")
def api_summary() -> dict:
    conn = _connect()
    try:
        summary = get_performance_summary(conn)
        creators = list_creators(conn)
        return {
            "creator_count": len(creators),
            "active_creator_count": sum(1 for c in creators if c["status"] == "active"),
            **asdict(summary),
        }
    finally:
        conn.close()


@app.get("/api/creators")
def api_creators() -> list[dict]:
    conn = _connect()
    try:
        creators = list_creators(conn)
        for c in creators:
            profile = get_creator_profile(conn, creator_id=c["creator_id"])
            c["content_count"] = profile.content_count if profile else 0
            c["avg_engagement_rate"] = (profile.performance["averages"].get("engagement_rate") if profile else 0) or 0
            c["trend_direction"] = profile.performance["trend_direction"] if profile else "flat"
            c["trend_pct"] = profile.performance["trend_pct"] if profile else 0
            c["best_formats"] = profile.best_formats if profile else []
        return creators
    finally:
        conn.close()


@app.get("/api/creators/{creator_id}")
def api_creator_profile(creator_id: str) -> dict:
    conn = _connect()
    try:
        profile = get_creator_profile(conn, creator_id=creator_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Creator not found")
        return asdict(profile)
    finally:
        conn.close()


@app.get("/api/trending")
def api_trending() -> list[dict]:
    conn = _connect()
    try:
        return [asdict(t) for t in detect_trending_formats(conn, min_sample_size=1)]
    finally:
        conn.close()


@app.get("/api/top-performers")
def api_top_performers(metric: str = "views", n: int = 10) -> list[dict]:
    conn = _connect()
    try:
        return top_performers(conn, metric=metric, n=n)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@app.post("/api/sync")
def api_sync() -> dict:
    conn = _connect()
    try:
        api_key = os.environ.get("SIDESHIFT_API_KEY")
        if api_key:
            adapter = SideShiftAPIAdapter(api_key=api_key)
        else:
            adapter = CSVIngestionAdapter(os.environ.get("UGC_ANALYTICS_SOURCE_DIR", "sample_data"))
        result = sync_all(conn, adapter)
        return asdict(result)
    finally:
        conn.close()


_NO_CACHE = {"Cache-Control": "no-store"}


def _asset_version(filename: str) -> int:
    return int((STATIC_DIR / filename).stat().st_mtime)


@app.get("/")
def index() -> HTMLResponse:
    # Query-string version busts any cached copy of app.js/style.css the moment
    # either file's mtime changes, without needing a manual version bump.
    html = (STATIC_DIR / "index.html").read_text()
    html = html.replace('href="/style.css"', f'href="/style.css?v={_asset_version("style.css")}"')
    html = html.replace('src="/app.js"', f'src="/app.js?v={_asset_version("app.js")}"')
    return HTMLResponse(html, headers=_NO_CACHE)


@app.get("/app.js")
def app_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript", headers=_NO_CACHE)


@app.get("/style.css")
def style_css() -> FileResponse:
    return FileResponse(STATIC_DIR / "style.css", media_type="text/css", headers=_NO_CACHE)


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8420)


if __name__ == "__main__":
    main()
