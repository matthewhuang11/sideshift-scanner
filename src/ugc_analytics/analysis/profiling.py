"""Creator profiling (build spec section 7.1).

`tone_style_tags` on the creators table can come from SideShift or be
seeded manually; `derived_style_tags` here is a lightweight baseline
that infers a creator's most frequent format tags from their own
content history, since SideShift doesn't provide style/tone natively.
This is intentionally a simple frequency heuristic, not an LLM call —
swap in a real classification step (e.g. via an MCP sampling call back
to Claude) if richer tagging is needed later.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from ugc_analytics.analysis.performance import METRIC_COLUMNS, get_performance_summary
from ugc_analytics.db import row_to_creator


@dataclass
class CreatorProfile:
    creator_id: str
    name: str
    handle: str
    platforms: dict[str, str]
    niche_tags: list[str]
    tone_style_tags: list[str]
    derived_style_tags: list[str]
    status: str
    content_count: int
    best_formats: list[str]
    performance: dict = field(default_factory=dict)


def list_creators(
    conn: sqlite3.Connection,
    niche: str | None = None,
    platform: str | None = None,
    status: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM creators WHERE 1=1"
    params: list = []
    if niche:
        query += " AND niche_tags LIKE ?"
        params.append(f'%"{niche}"%')
    if platform:
        query += " AND platforms LIKE ?"
        params.append(f'%"{platform}"%')
    if status:
        query += " AND status = ?"
        params.append(status)
    rows = conn.execute(query, params).fetchall()
    creators = [row_to_creator(r) for r in rows]
    return [
        {
            "creator_id": c.creator_id,
            "name": c.name,
            "handle": c.handle,
            "platforms": c.platforms,
            "niche_tags": c.niche_tags,
            "tone_style_tags": c.tone_style_tags,
            "status": c.status,
        }
        for c in creators
    ]


def derived_style_tags(conn: sqlite3.Connection, creator_id: str, top_n: int = 5) -> list[str]:
    rows = conn.execute("SELECT format_tags FROM content_items WHERE creator_id = ?", (creator_id,)).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(json.loads(row["format_tags"] or "[]"))
    return [tag for tag, _ in counter.most_common(top_n)]


def best_formats_for_creator(
    conn: sqlite3.Connection, creator_id: str, metric: str = "engagement_rate", top_n: int = 3
) -> list[str]:
    if metric not in METRIC_COLUMNS:
        raise ValueError(f"Unsupported metric '{metric}'. Choose from {METRIC_COLUMNS}.")
    rows = conn.execute(
        """
        SELECT ci.format_tags, pm.{metric} as value
        FROM content_items ci
        JOIN performance_metrics pm ON pm.content_id = ci.content_id
        WHERE ci.creator_id = ? AND pm.snapshot_date = (
            SELECT MAX(snapshot_date) FROM performance_metrics WHERE content_id = ci.content_id
        )
        """.format(metric=metric),
        (creator_id,),
    ).fetchall()
    tag_values: dict[str, list[float]] = {}
    for row in rows:
        for tag in json.loads(row["format_tags"] or "[]"):
            tag_values.setdefault(tag, []).append(row["value"] or 0)
    ranked = sorted(tag_values.items(), key=lambda kv: sum(kv[1]) / len(kv[1]), reverse=True)
    return [tag for tag, _ in ranked[:top_n]]


def get_creator_profile(
    conn: sqlite3.Connection, creator_id: str | None = None, handle: str | None = None
) -> CreatorProfile | None:
    if creator_id:
        row = conn.execute("SELECT * FROM creators WHERE creator_id = ?", (creator_id,)).fetchone()
    elif handle:
        row = conn.execute("SELECT * FROM creators WHERE handle = ?", (handle,)).fetchone()
    else:
        raise ValueError("Provide creator_id or handle.")
    if row is None:
        return None

    creator = row_to_creator(row)
    content_count = conn.execute(
        "SELECT COUNT(*) FROM content_items WHERE creator_id = ?", (creator.creator_id,)
    ).fetchone()[0]
    summary = get_performance_summary(conn, scope="creator", scope_id=creator.creator_id)

    return CreatorProfile(
        creator_id=creator.creator_id,
        name=creator.name,
        handle=creator.handle,
        platforms=creator.platforms,
        niche_tags=creator.niche_tags,
        tone_style_tags=creator.tone_style_tags,
        derived_style_tags=derived_style_tags(conn, creator.creator_id),
        status=creator.status,
        content_count=content_count,
        best_formats=best_formats_for_creator(conn, creator.creator_id),
        performance={
            "sample_size": summary.sample_size,
            "averages": summary.averages,
            "trend_direction": summary.trend_direction,
            "trend_pct": summary.trend_pct,
        },
    )
