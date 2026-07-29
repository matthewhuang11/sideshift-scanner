"""Performance aggregation with simple statistical baselines.

Per build spec section 7.2: "2x above roster average" instead of vague
qualitative claims. Everything here works off the *latest* snapshot per
content item unless a date_range is given, since performance_metrics is
a time series (spec section 5).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

METRIC_COLUMNS = ("views", "likes", "comments", "shares", "saves", "conversions", "revenue", "engagement_rate")


def _date_filter_sql(date_range: tuple[str, str] | None, alias: str = "pm") -> tuple[str, list[str]]:
    if not date_range:
        return "", []
    start, end = date_range
    return f" AND {alias}.snapshot_date BETWEEN ? AND ?", [start, end]


def _latest_metrics_rows(
    conn: sqlite3.Connection, date_range: tuple[str, str] | None = None
) -> list[sqlite3.Row]:
    """One row per content_id: its most recent snapshot (within date_range if given)."""
    clause, params = _date_filter_sql(date_range)
    query = f"""
        SELECT pm.* FROM performance_metrics pm
        WHERE pm.snapshot_date = (
            SELECT MAX(snapshot_date) FROM performance_metrics
            WHERE content_id = pm.content_id{clause.replace('pm.', '')}
        )
        {clause}
    """
    return conn.execute(query, params + params).fetchall()


@dataclass
class PerformanceSummary:
    scope: str
    scope_id: str | None
    sample_size: int
    totals: dict[str, float] = field(default_factory=dict)
    averages: dict[str, float] = field(default_factory=dict)
    trend_direction: str = "flat"
    trend_pct: float = 0.0


def roster_average(conn: sqlite3.Connection, metric: str, date_range: tuple[str, str] | None = None) -> float:
    rows = _latest_metrics_rows(conn, date_range)
    if not rows:
        return 0.0
    values = [row[metric] or 0 for row in rows]
    return sum(values) / len(values)


def _trend(conn: sqlite3.Connection, content_ids: list[str], metric: str) -> tuple[str, float]:
    """Compares each content item's first vs. latest snapshot for `metric`, averaged."""
    if not content_ids:
        return "flat", 0.0
    placeholders = ",".join("?" * len(content_ids))
    rows = conn.execute(
        f"""
        SELECT content_id, MIN(snapshot_date) as first_date, MAX(snapshot_date) as last_date
        FROM performance_metrics WHERE content_id IN ({placeholders})
        GROUP BY content_id
        """,
        content_ids,
    ).fetchall()
    pct_changes = []
    for row in rows:
        if row["first_date"] == row["last_date"]:
            continue
        first = conn.execute(
            "SELECT * FROM performance_metrics WHERE content_id=? AND snapshot_date=?",
            (row["content_id"], row["first_date"]),
        ).fetchone()
        last = conn.execute(
            "SELECT * FROM performance_metrics WHERE content_id=? AND snapshot_date=?",
            (row["content_id"], row["last_date"]),
        ).fetchone()
        if first[metric] and first[metric] > 0:
            pct_changes.append((last[metric] - first[metric]) / first[metric])
    if not pct_changes:
        return "flat", 0.0
    avg_pct = sum(pct_changes) / len(pct_changes)
    if avg_pct > 0.05:
        return "up", round(avg_pct * 100, 1)
    if avg_pct < -0.05:
        return "down", round(avg_pct * 100, 1)
    return "flat", round(avg_pct * 100, 1)


def get_performance_summary(
    conn: sqlite3.Connection,
    scope: str = "global",
    scope_id: str | None = None,
    date_range: tuple[str, str] | None = None,
) -> PerformanceSummary:
    """scope: 'global' | 'creator' | 'campaign' | 'format'. scope_id required unless global."""
    clause, params = _date_filter_sql(date_range, alias="pm")
    base_query = """
        SELECT pm.* FROM performance_metrics pm
        JOIN content_items ci ON ci.content_id = pm.content_id
        WHERE pm.snapshot_date = (
            SELECT MAX(snapshot_date) FROM performance_metrics WHERE content_id = pm.content_id
        )
    """
    scope_params: list = []
    if scope == "creator":
        base_query += " AND ci.creator_id = ?"
        scope_params.append(scope_id)
    elif scope == "campaign":
        base_query += " AND ci.campaign_id = ?"
        scope_params.append(scope_id)
    elif scope == "format":
        base_query += " AND ci.format_tags LIKE ?"
        scope_params.append(f'%"{scope_id}"%')

    base_query += clause
    rows = conn.execute(base_query, scope_params + params).fetchall()

    totals = {m: sum((row[m] or 0) for row in rows) for m in METRIC_COLUMNS}
    n = len(rows)
    averages = {m: round(totals[m] / n, 4) if n else 0.0 for m in METRIC_COLUMNS}

    content_ids = [row["content_id"] for row in rows]
    trend_direction, trend_pct = _trend(conn, content_ids, "views")

    return PerformanceSummary(
        scope=scope,
        scope_id=scope_id,
        sample_size=n,
        totals=totals,
        averages=averages,
        trend_direction=trend_direction,
        trend_pct=trend_pct,
    )


def top_performers(
    conn: sqlite3.Connection,
    metric: str = "views",
    n: int = 10,
    date_range: tuple[str, str] | None = None,
) -> list[dict]:
    if metric not in METRIC_COLUMNS:
        raise ValueError(f"Unsupported metric '{metric}'. Choose from {METRIC_COLUMNS}.")
    clause, params = _date_filter_sql(date_range, alias="pm")
    query = f"""
        SELECT ci.content_id, ci.creator_id, COALESCE(cr.name, 'Unknown creator') as creator_name, ci.platform,
               ci.format_tags, pm.{metric} as value, pm.snapshot_date
        FROM performance_metrics pm
        JOIN content_items ci ON ci.content_id = pm.content_id
        LEFT JOIN creators cr ON cr.creator_id = ci.creator_id
        WHERE pm.snapshot_date = (
            SELECT MAX(snapshot_date) FROM performance_metrics WHERE content_id = pm.content_id
        )
        {clause}
        ORDER BY value DESC
        LIMIT ?
    """
    rows = conn.execute(query, params + [n]).fetchall()
    return [dict(row) for row in rows]
