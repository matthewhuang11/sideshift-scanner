"""Format/hook clustering vs. roster baseline (build spec section 7.3).

Groups content by format_tags, computes average performance per tag,
and surfaces which tags are outperforming the roster baseline — the
"what's working" / viral-format detection goal from spec section 2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ugc_analytics.analysis.performance import _latest_metrics_rows, roster_average


@dataclass
class FormatTrend:
    format_tag: str
    sample_size: int
    avg_metric: float
    baseline: float
    multiplier: float  # avg_metric / baseline


def detect_trending_formats(
    conn: sqlite3.Connection,
    metric: str = "engagement_rate",
    min_sample_size: int = 2,
    date_range: tuple[str, str] | None = None,
) -> list[FormatTrend]:
    baseline = roster_average(conn, metric, date_range)
    latest_rows = _latest_metrics_rows(conn, date_range)
    metric_by_content = {row["content_id"]: (row[metric] or 0) for row in latest_rows}

    content_rows = conn.execute("SELECT content_id, format_tags FROM content_items").fetchall()
    values_by_tag: dict[str, list[float]] = {}
    for row in content_rows:
        if row["content_id"] not in metric_by_content:
            continue
        tags = json.loads(row["format_tags"] or "[]")
        for tag in tags:
            values_by_tag.setdefault(tag, []).append(metric_by_content[row["content_id"]])

    trends = []
    for tag, values in values_by_tag.items():
        if len(values) < min_sample_size:
            continue
        avg = sum(values) / len(values)
        multiplier = round(avg / baseline, 2) if baseline else 0.0
        trends.append(
            FormatTrend(
                format_tag=tag,
                sample_size=len(values),
                avg_metric=round(avg, 4),
                baseline=round(baseline, 4),
                multiplier=multiplier,
            )
        )

    trends.sort(key=lambda t: t.multiplier, reverse=True)
    return trends
