"""CSV ingestion adapter.

The working fallback while SideShift API/export access is unconfirmed
(build spec section 4, option 2). Reads a folder containing:

    creators.csv
    campaigns.csv              (optional)
    content_items.csv
    performance_metrics.csv

CSV column conventions (see sample_data/ for real examples):
  - `platforms` on creators.csv: "tiktok:@handle;instagram:@handle2"
  - `niche_tags` / `tone_style_tags` / `format_tags`: comma-separated
  - everything else maps 1:1 to the field names in models.py
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from ugc_analytics.ingestion.base import IngestionAdapter
from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_platforms(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    platforms = {}
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        key, _, value = pair.partition(":")
        platforms[key.strip()] = value.strip()
    return platforms


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _after(date_str: str | None, since: date | None) -> bool:
    if since is None or not date_str:
        return True
    try:
        return date.fromisoformat(date_str[:10]) >= since
    except ValueError:
        return True


class CSVIngestionAdapter(IngestionAdapter):
    method = "csv"

    def __init__(self, source_dir: Path | str):
        self.source_dir = Path(source_dir)

    def fetch_creators(self, since: date | None = None) -> list[Creator]:
        rows = _read_csv(self.source_dir / "creators.csv")
        creators = [
            Creator(
                creator_id=row["creator_id"],
                name=row["name"],
                handle=row.get("handle", ""),
                platforms=_parse_platforms(row.get("platforms")),
                niche_tags=_split_tags(row.get("niche_tags")),
                tone_style_tags=_split_tags(row.get("tone_style_tags")),
                audience_notes=row.get("audience_notes", ""),
                status=row.get("status") or "active",
                joined_date=row.get("joined_date") or None,
            )
            for row in rows
        ]
        return [c for c in creators if _after(c.joined_date, since)]

    def fetch_campaigns(self, since: date | None = None) -> list[Campaign]:
        rows = _read_csv(self.source_dir / "campaigns.csv")
        campaigns = [
            Campaign(
                campaign_id=row["campaign_id"],
                name=row["name"],
                brief_text=row.get("brief_text", ""),
                target_format=row.get("target_format", ""),
                start_date=row.get("start_date") or None,
            )
            for row in rows
        ]
        return [c for c in campaigns if _after(c.start_date, since)]

    def fetch_content_items(self, since: date | None = None) -> list[ContentItem]:
        rows = _read_csv(self.source_dir / "content_items.csv")
        items = [
            ContentItem(
                content_id=row["content_id"],
                creator_id=row["creator_id"],
                campaign_id=row.get("campaign_id") or None,
                platform=row["platform"],
                format_tags=_split_tags(row.get("format_tags")),
                post_date=row.get("post_date") or None,
                url=row.get("url", ""),
                transcript_or_caption=row.get("transcript_or_caption", ""),
            )
            for row in rows
        ]
        return [i for i in items if _after(i.post_date, since)]

    def fetch_performance_metrics(self, since: date | None = None) -> list[PerformanceMetric]:
        rows = _read_csv(self.source_dir / "performance_metrics.csv")
        metrics = [
            PerformanceMetric(
                content_id=row["content_id"],
                snapshot_date=row["snapshot_date"],
                views=int(row.get("views") or 0),
                likes=int(row.get("likes") or 0),
                comments=int(row.get("comments") or 0),
                shares=int(row.get("shares") or 0),
                saves=int(row.get("saves") or 0),
                ctr=float(row["ctr"]) if row.get("ctr") else None,
                conversions=int(row["conversions"]) if row.get("conversions") else None,
                revenue=float(row["revenue"]) if row.get("revenue") else None,
            )
            for row in rows
        ]
        return [m for m in metrics if _after(m.snapshot_date, since)]
