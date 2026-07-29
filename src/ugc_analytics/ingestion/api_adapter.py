"""SideShift API adapter.

Phase 0 (build spec section 4) is resolved: SideShift publishes a public,
API-key-authenticated REST API and OpenAPI spec at
https://app.sideshift.app/openapi/sideshift-api-public.yaml (docs at
https://app.sideshift.app/docs, no login required to view them). Get a
key from Settings -> Integrations in the SideShift dashboard; it requires
an active SideShift subscription.

Endpoints used here:
  GET /creators                    -> Creator
  GET /programs                    -> Campaign
  GET /posts                       -> ContentItem
  GET /posts/{id}/metrics-history  -> PerformanceMetric (daily snapshots)

Field mapping was corrected against a live account after the published
docs turned out to disagree with actual responses in three ways:
  - `uploadedAt`/`createdAt` are Unix **seconds**, not milliseconds as
    documented; `_epoch_to_date` detects the unit by magnitude so it
    handles either.
  - A post's creator/program links (`contractorId`, `programId`) are
    top-level fields, not nested under `contract`/`program` objects.
  - `GET /posts/{id}/metrics-history` wraps its payload in a `data` key.

`/creators` doesn't have a `status` field; a creator's contract status
per program (`campaigns[].contractStatus`) is used instead, and
per-platform handles come from `campaigns[].handles[]` — richer than
the docs implied, so `platforms`/`handle` are populated for real rather
than left blank.

SideShift doesn't tag content format/hook style at all, but post titles
carry real `#hashtags` (e.g. "...#whip #appcreation #partner"), so those
are extracted as `format_tags` — a real, already-present signal, rather
than empty tags or a guessed heuristic. This is what makes
`detect_trending_formats`/`recommend_creators_for_brief` work against
real synced data instead of the CSV sample only.

Each post's `earnings` (what SideShift paid out for it) is attached to
its most recent metrics-history snapshot as `revenue` — SideShift's own
dashboard doesn't appear to combine payout with engagement analytics in
one ranked view, so this unlocks that (`top_performers(metric="revenue")`,
revenue-aware creator profiles). It's a running total, not a daily
breakdown, so it's only set on the latest snapshot per post rather than
backdated across history (we don't know what it was on earlier dates).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import requests

from ugc_analytics.ingestion.base import IngestionAdapter
from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric

DEFAULT_BASE_URL = "https://app.sideshift.app/api/v1"

# Above this, a value is almost certainly milliseconds; live data has shown
# both claimed (ms) and actual (seconds) units depending on endpoint/field.
_MS_THRESHOLD = 1_000_000_000_000

_HASHTAG_RE = re.compile(r"#(\w+)")


def _epoch_to_date(value: int | None) -> str | None:
    if not value:
        return None
    seconds = value / 1000 if value > _MS_THRESHOLD else value
    return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()


def _extract_hashtags(text: str | None) -> list[str]:
    if not text:
        return []
    # dict.fromkeys dedupes while preserving first-seen order; some post
    # titles repeat their caption text verbatim, which would otherwise
    # double-count the same tag for one post.
    return list(dict.fromkeys(tag.lower() for tag in _HASHTAG_RE.findall(text)))


def _after(date_str: str | None, since: date | None) -> bool:
    if since is None or not date_str:
        return True
    try:
        return date.fromisoformat(date_str[:10]) >= since
    except ValueError:
        return True


class SideShiftAPIAdapter(IngestionAdapter):
    method = "api"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        page_size: int = 100,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.page_size = page_size
        self._posts_cache: list[dict] | None = None

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key}

    def _get_paginated(self, path: str, params: dict | None = None) -> list[dict]:
        params = dict(params or {})
        params.setdefault("limit", self.page_size)
        page = 1
        results: list[dict] = []
        while True:
            params["page"] = page
            resp = self.session.get(f"{self.base_url}{path}", headers=self._headers(), params=params, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", [])
            results.extend(data)
            total_pages = body.get("totalPages")
            if total_pages is not None:
                if page >= total_pages:
                    break
            elif len(data) < params["limit"]:
                break
            page += 1
        return results

    def _get_posts(self) -> list[dict]:
        if self._posts_cache is None:
            self._posts_cache = self._get_paginated("/posts")
        return self._posts_cache

    def fetch_creators(self, since: date | None = None) -> list[Creator]:
        creators = []
        for item in self._get_paginated("/creators"):
            platforms: dict[str, str] = {}
            statuses = []
            for campaign in item.get("campaigns") or []:
                if campaign.get("contractStatus"):
                    statuses.append(campaign["contractStatus"])
                for h in campaign.get("handles") or []:
                    platform, handle = h.get("platform"), h.get("handle")
                    if platform and handle:
                        platforms.setdefault(platform, handle)
            status = "active" if "active" in statuses else (statuses[0] if statuses else "active")
            creators.append(
                Creator(
                    creator_id=str(item["id"]),
                    name=item.get("name") or "",
                    handle=next(iter(platforms.values()), ""),
                    platforms=platforms,
                    status=status,
                )
            )
        return creators

    def fetch_campaigns(self, since: date | None = None) -> list[Campaign]:
        campaigns = []
        for item in self._get_paginated("/programs"):
            start_date = _epoch_to_date(item.get("createdAt"))
            if not _after(start_date, since):
                continue
            campaigns.append(
                Campaign(
                    campaign_id=str(item["id"]),
                    name=item.get("name") or "",
                    brief_text=item.get("description") or "",
                    start_date=start_date,
                )
            )
        return campaigns

    def fetch_content_items(self, since: date | None = None) -> list[ContentItem]:
        items = []
        for item in self._get_posts():
            post_date = _epoch_to_date(item.get("uploadedAt") or item.get("createdAt"))
            if not _after(post_date, since):
                continue
            creator_id = str(item.get("contractorId") or item.get("creator") or item["id"])
            program_id = item.get("programId")
            title = item.get("title") or item.get("description") or ""
            items.append(
                ContentItem(
                    content_id=str(item["id"]),
                    creator_id=creator_id,
                    campaign_id=str(program_id) if program_id else None,
                    platform=item.get("platform") or "",
                    format_tags=_extract_hashtags(title),
                    post_date=post_date,
                    url=item.get("postPage") or item.get("url") or "",
                    transcript_or_caption=title,
                )
            )
        return items

    def fetch_performance_metrics(self, since: date | None = None) -> list[PerformanceMetric]:
        metrics = []
        for post in self._get_posts():
            post_id = str(post["id"])
            resp = self.session.get(
                f"{self.base_url}/posts/{post_id}/metrics-history", headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            payload = resp.json()
            body = payload.get("data", payload)
            post_metrics = []
            for snapshot in body.get("history", []):
                snap_date = snapshot.get("date")
                if not _after(snap_date, since):
                    continue
                post_metrics.append(
                    PerformanceMetric(
                        content_id=post_id,
                        snapshot_date=snap_date,
                        views=int(snapshot.get("views") or 0),
                        likes=int(snapshot.get("likes") or 0),
                        comments=int(snapshot.get("comments") or 0),
                        shares=int(snapshot.get("shares") or 0),
                        saves=int(snapshot.get("bookmarks") or 0),
                    )
                )
            if post_metrics and post.get("earnings") is not None:
                # earnings is a running total as of now, not a per-day figure,
                # so it only belongs on the most recent snapshot (don't assume
                # the API returns history in date order).
                latest = max(post_metrics, key=lambda m: m.snapshot_date)
                latest.revenue = float(post["earnings"])
            metrics.extend(post_metrics)
        return metrics
