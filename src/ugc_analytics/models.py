"""Dataclasses for the internal schema described in docs/build-spec.md section 5.

Ingestion adapters normalize whatever SideShift gives them (API JSON, CSV
rows, scraped DOM) into these shapes before they ever touch the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Creator:
    creator_id: str
    name: str
    handle: str = ""
    platforms: dict[str, str] = field(default_factory=dict)
    niche_tags: list[str] = field(default_factory=list)
    tone_style_tags: list[str] = field(default_factory=list)
    audience_notes: str = ""
    status: str = "active"
    joined_date: str | None = None


@dataclass
class ContentItem:
    content_id: str
    creator_id: str
    platform: str
    campaign_id: str | None = None
    format_tags: list[str] = field(default_factory=list)
    post_date: str | None = None
    url: str = ""
    transcript_or_caption: str = ""


@dataclass
class PerformanceMetric:
    content_id: str
    snapshot_date: str
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    ctr: float | None = None
    conversions: int | None = None
    revenue: float | None = None

    @property
    def engagement_rate(self) -> float:
        if self.views <= 0:
            return 0.0
        return round((self.likes + self.comments + self.shares + self.saves) / self.views, 4)


@dataclass
class Campaign:
    campaign_id: str
    name: str
    brief_text: str = ""
    target_format: str = ""
    start_date: str | None = None


@dataclass
class SyncResult:
    method: str
    creators_ingested: int = 0
    content_items_ingested: int = 0
    metrics_ingested: int = 0
    status: str = "ok"
    detail: str = ""
