"""SQLite schema and connection helpers.

Kept to plain sqlite3 + a thin upsert layer rather than an ORM, per the
build spec's "SQLite to start, DuckDB/Postgres only if it becomes necessary"
guidance. JSON-ish fields (platforms, tags) are stored as TEXT and
(de)serialized at the boundary.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "ugc_analytics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
    creator_id      TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    handle          TEXT,
    platforms       TEXT NOT NULL DEFAULT '{}',
    niche_tags      TEXT NOT NULL DEFAULT '[]',
    tone_style_tags TEXT NOT NULL DEFAULT '[]',
    audience_notes  TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'active',
    joined_date     TEXT
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    brief_text      TEXT DEFAULT '',
    target_format   TEXT DEFAULT '',
    start_date      TEXT
);

-- creator_id is intentionally not a foreign key: SideShift attributes some
-- posts to "ghost handles" or creators no longer returned by GET /creators,
-- so not every content item has a matching row in creators (confirmed
-- against a live account, see ingestion/api_adapter.py).
CREATE TABLE IF NOT EXISTS content_items (
    content_id             TEXT PRIMARY KEY,
    creator_id             TEXT NOT NULL,
    campaign_id            TEXT REFERENCES campaigns(campaign_id),
    platform               TEXT NOT NULL,
    format_tags            TEXT NOT NULL DEFAULT '[]',
    post_date              TEXT,
    url                    TEXT DEFAULT '',
    transcript_or_caption  TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_content_items_creator ON content_items(creator_id);
CREATE INDEX IF NOT EXISTS idx_content_items_campaign ON content_items(campaign_id);

CREATE TABLE IF NOT EXISTS performance_metrics (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id        TEXT NOT NULL REFERENCES content_items(content_id),
    snapshot_date     TEXT NOT NULL,
    views             INTEGER NOT NULL DEFAULT 0,
    likes             INTEGER NOT NULL DEFAULT 0,
    comments          INTEGER NOT NULL DEFAULT 0,
    shares            INTEGER NOT NULL DEFAULT 0,
    saves             INTEGER NOT NULL DEFAULT 0,
    ctr               REAL,
    conversions       INTEGER,
    revenue           REAL,
    engagement_rate   REAL NOT NULL DEFAULT 0,
    UNIQUE(content_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_metrics_content ON performance_metrics(content_id);
CREATE INDEX IF NOT EXISTS idx_metrics_snapshot ON performance_metrics(snapshot_date);

CREATE TABLE IF NOT EXISTS sync_log (
    sync_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT NOT NULL,
    method         TEXT NOT NULL,
    rows_ingested  INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,
    detail         TEXT DEFAULT ''
);

-- Logged by every MCP tool call (server.py) so the dashboard can show a
-- live feed of what's actually being asked through chat, instead of only
-- being a static snapshot.
CREATE TABLE IF NOT EXISTS agent_activity (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT NOT NULL,
    tool_name    TEXT NOT NULL,
    summary      TEXT NOT NULL
);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_creator(conn: sqlite3.Connection, creator: Creator) -> None:
    conn.execute(
        """
        INSERT INTO creators
            (creator_id, name, handle, platforms, niche_tags, tone_style_tags, audience_notes, status, joined_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(creator_id) DO UPDATE SET
            name=excluded.name, handle=excluded.handle, platforms=excluded.platforms,
            niche_tags=excluded.niche_tags, tone_style_tags=excluded.tone_style_tags,
            audience_notes=excluded.audience_notes, status=excluded.status,
            joined_date=excluded.joined_date
        """,
        (
            creator.creator_id,
            creator.name,
            creator.handle,
            json.dumps(creator.platforms),
            json.dumps(creator.niche_tags),
            json.dumps(creator.tone_style_tags),
            creator.audience_notes,
            creator.status,
            creator.joined_date,
        ),
    )


def upsert_campaign(conn: sqlite3.Connection, campaign: Campaign) -> None:
    conn.execute(
        """
        INSERT INTO campaigns (campaign_id, name, brief_text, target_format, start_date)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(campaign_id) DO UPDATE SET
            name=excluded.name, brief_text=excluded.brief_text,
            target_format=excluded.target_format, start_date=excluded.start_date
        """,
        (campaign.campaign_id, campaign.name, campaign.brief_text, campaign.target_format, campaign.start_date),
    )


def upsert_content_item(conn: sqlite3.Connection, item: ContentItem) -> None:
    conn.execute(
        """
        INSERT INTO content_items
            (content_id, creator_id, campaign_id, platform, format_tags, post_date, url, transcript_or_caption)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_id) DO UPDATE SET
            creator_id=excluded.creator_id, campaign_id=excluded.campaign_id,
            platform=excluded.platform, format_tags=excluded.format_tags,
            post_date=excluded.post_date, url=excluded.url,
            transcript_or_caption=excluded.transcript_or_caption
        """,
        (
            item.content_id,
            item.creator_id,
            item.campaign_id,
            item.platform,
            json.dumps(item.format_tags),
            item.post_date,
            item.url,
            item.transcript_or_caption,
        ),
    )


def upsert_performance_metric(conn: sqlite3.Connection, metric: PerformanceMetric) -> None:
    conn.execute(
        """
        INSERT INTO performance_metrics
            (content_id, snapshot_date, views, likes, comments, shares, saves, ctr, conversions, revenue, engagement_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_id, snapshot_date) DO UPDATE SET
            views=excluded.views, likes=excluded.likes, comments=excluded.comments,
            shares=excluded.shares, saves=excluded.saves, ctr=excluded.ctr,
            conversions=excluded.conversions, revenue=excluded.revenue,
            engagement_rate=excluded.engagement_rate
        """,
        (
            metric.content_id,
            metric.snapshot_date,
            metric.views,
            metric.likes,
            metric.comments,
            metric.shares,
            metric.saves,
            metric.ctr,
            metric.conversions,
            metric.revenue,
            metric.engagement_rate,
        ),
    )


def log_sync(conn: sqlite3.Connection, method: str, rows_ingested: int, status: str, detail: str = "") -> None:
    conn.execute(
        "INSERT INTO sync_log (timestamp, method, rows_ingested, status, detail) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), method, rows_ingested, status, detail),
    )


def log_activity(conn: sqlite3.Connection, tool_name: str, summary: str) -> None:
    conn.execute(
        "INSERT INTO agent_activity (timestamp, tool_name, summary) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), tool_name, summary),
    )
    conn.commit()


def recent_activity(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT timestamp, tool_name, summary FROM agent_activity ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def row_to_creator(row: sqlite3.Row) -> Creator:
    return Creator(
        creator_id=row["creator_id"],
        name=row["name"],
        handle=row["handle"] or "",
        platforms=json.loads(row["platforms"] or "{}"),
        niche_tags=json.loads(row["niche_tags"] or "[]"),
        tone_style_tags=json.loads(row["tone_style_tags"] or "[]"),
        audience_notes=row["audience_notes"] or "",
        status=row["status"],
        joined_date=row["joined_date"],
    )


def row_to_content_item(row: sqlite3.Row) -> ContentItem:
    return ContentItem(
        content_id=row["content_id"],
        creator_id=row["creator_id"],
        campaign_id=row["campaign_id"],
        platform=row["platform"],
        format_tags=json.loads(row["format_tags"] or "[]"),
        post_date=row["post_date"],
        url=row["url"] or "",
        transcript_or_caption=row["transcript_or_caption"] or "",
    )
