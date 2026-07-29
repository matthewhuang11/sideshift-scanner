"""Creator-for-brief matching (build spec section 7.4).

Scores creators by historical performance on similar formats + niche
fit, and returns the reasoning alongside the score rather than a
black-box number, per spec.
"""

from __future__ import annotations

import re
import sqlite3

from ugc_analytics.analysis.performance import roster_average
from ugc_analytics.analysis.profiling import best_formats_for_creator, derived_style_tags, list_creators

_WORD_RE = re.compile(r"[a-z0-9&]+")


def _keywords(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _creator_format_multiplier(
    conn: sqlite3.Connection, creator_id: str, format_tags: list[str], baseline: float
) -> float:
    if not format_tags or not baseline:
        return 0.0
    condition = " OR ".join(["ci.format_tags LIKE ?"] * len(format_tags))
    params = [f'%"{t}"%' for t in format_tags]
    rows = conn.execute(
        f"""
        SELECT pm.engagement_rate as value
        FROM content_items ci
        JOIN performance_metrics pm ON pm.content_id = ci.content_id
        WHERE ci.creator_id = ? AND ({condition})
        AND pm.snapshot_date = (SELECT MAX(snapshot_date) FROM performance_metrics WHERE content_id = ci.content_id)
        """,
        [creator_id] + params,
    ).fetchall()
    if not rows:
        return 0.0
    avg = sum((r["value"] or 0) for r in rows) / len(rows)
    return round(avg / baseline, 2)


def recommend_creators_for_brief(
    conn: sqlite3.Connection,
    brief_text: str | None = None,
    format_tags: list[str] | None = None,
    n: int = 5,
) -> list[dict]:
    if not brief_text and not format_tags:
        raise ValueError("Provide brief_text or format_tags.")

    format_tags = format_tags or []
    keywords = _keywords(brief_text) if brief_text else set()
    baseline = roster_average(conn, "engagement_rate")

    scored = []
    for c in list_creators(conn, status="active"):
        cid = c["creator_id"]
        top_formats = set(best_formats_for_creator(conn, cid, top_n=10))
        style_tags = set(derived_style_tags(conn, cid, top_n=10))
        candidate_tags = top_formats | style_tags

        format_overlap = candidate_tags & set(format_tags)
        niche_overlap = keywords & {t.lower() for t in c["niche_tags"]}
        keyword_format_overlap = keywords & {t.lower() for t in candidate_tags}

        match_formats = format_tags or list(candidate_tags)
        multiplier = _creator_format_multiplier(conn, cid, match_formats, baseline)

        score = round(
            len(format_overlap) * 2 + len(niche_overlap) * 1.5 + len(keyword_format_overlap) * 1 + multiplier, 2
        )
        if score <= 0:
            continue

        rationale_parts = []
        if format_overlap:
            rationale_parts.append(f"matches their top format(s): {', '.join(sorted(format_overlap))}")
        if niche_overlap:
            rationale_parts.append(f"niche fit: {', '.join(sorted(niche_overlap))}")
        if multiplier > 1:
            rationale_parts.append(f"historically {multiplier}x roster avg engagement on similar content")
        elif multiplier and multiplier <= 1:
            rationale_parts.append(f"{multiplier}x roster avg engagement on similar content")

        scored.append(
            {
                "creator_id": cid,
                "name": c["name"],
                "handle": c["handle"],
                "score": score,
                "rationale": "; ".join(rationale_parts) or "general roster fit",
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:n]
