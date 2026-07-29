"""generate_content_brief (build spec section 6, v2 stretch).

Drafts a brief tailored to a creator's own style plus a target format —
either one given explicitly, a trending format they haven't leaned into
yet, or their own best-performing format as a fallback. Kept as a
template fill rather than an LLM call so it works without external
dependencies; swap in a real generation step later if richer copy is
needed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ugc_analytics.analysis.profiling import get_creator_profile
from ugc_analytics.analysis.trends import detect_trending_formats


@dataclass
class ContentBrief:
    creator_id: str
    creator_name: str
    target_format: str
    draft_brief: str
    rationale: str


def _choose_target_format(conn: sqlite3.Connection, profile, based_on_format: str | None) -> tuple[str, str]:
    if based_on_format:
        return based_on_format, "format explicitly requested"

    their_formats = set(profile.best_formats) | set(profile.derived_style_tags)
    trends = detect_trending_formats(conn, min_sample_size=1)
    untried = next((t for t in trends if t.format_tag not in their_formats), None)
    if untried:
        return untried.format_tag, f"trending format they haven't used yet ({untried.multiplier}x roster baseline)"

    if profile.best_formats:
        return profile.best_formats[0], "their own best-performing format"

    if trends:
        return trends[0].format_tag, f"top trending format on the roster ({trends[0].multiplier}x roster baseline)"

    return "unboxing", "no performance data yet; defaulting to a standard format"


def generate_content_brief(
    conn: sqlite3.Connection, creator_id: str, based_on_format: str | None = None
) -> ContentBrief:
    profile = get_creator_profile(conn, creator_id=creator_id)
    if profile is None:
        raise ValueError(f"No creator found with creator_id={creator_id!r}")

    target_format, rationale = _choose_target_format(conn, profile, based_on_format)

    tone = ", ".join(profile.tone_style_tags or profile.derived_style_tags) or "your usual tone"
    niche = ", ".join(profile.niche_tags) or "your niche"

    draft_brief = (
        f"Brief for {profile.name} ({profile.handle or profile.creator_id}): "
        f"create a {target_format} piece in your {tone} style, staying in your {niche} lane. "
        f"Open with a hook in the first 2 seconds, keep pacing consistent with what's worked for you before, "
        f"and land the core message before a soft call-to-action at the end."
    )

    return ContentBrief(
        creator_id=profile.creator_id,
        creator_name=profile.name,
        target_format=target_format,
        draft_brief=draft_brief,
        rationale=rationale,
    )
