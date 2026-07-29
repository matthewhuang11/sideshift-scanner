"""SideShift API adapter.

Phase 0 (build spec section 4) is resolved: SideShift publishes a public,
API-key-authenticated REST API and OpenAPI spec at
https://app.sideshift.app/openapi/sideshift-api-public.yaml (docs at
https://app.sideshift.app/docs, no login required to view them). Get a
key from Settings -> Integrations in the SideShift dashboard; it requires
an active SideShift subscription.

Endpoints used here, per the published spec:
  GET /creators                    -> Creator
  GET /programs                    -> Campaign
  GET /posts                       -> ContentItem
  GET /posts/{id}/metrics-history  -> PerformanceMetric (daily snapshots)

The API's `/creators` response doesn't expose per-platform handles
directly (that lives on individual posts as a social-handle string), so
`platforms`/`handle` are left blank here and can be enriched later once
a stable per-creator handle field is confirmed. `format_tags` are always
empty from the API too, matching the build spec's note that style/format
tagging is derived analysis, not a SideShift field (see analysis/profiling.py).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import requests

from ugc_analytics.ingestion.base import IngestionAdapter
from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric

DEFAULT_BASE_URL = "https://app.sideshift.app/api/v1"


def _ms_to_date(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()


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
        return [
            Creator(
                creator_id=str(item["id"]),
                name=item.get("name") or "",
                status=item.get("status") or "active",
            )
            for item in self._get_paginated("/creators")
        ]

    def fetch_campaigns(self, since: date | None = None) -> list[Campaign]:
        campaigns = []
        for item in self._get_paginated("/programs"):
            start_date = _ms_to_date(item.get("createdAt"))
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
            post_date = _ms_to_date(item.get("uploadedAt") or item.get("createdAt"))
            if not _after(post_date, since):
                continue
            contract = item.get("contract") or {}
            program = item.get("program") or {}
            creator_id = str(contract.get("contractorId") or item.get("creator") or item["id"])
            items.append(
                ContentItem(
                    content_id=str(item["id"]),
                    creator_id=creator_id,
                    campaign_id=str(program["id"]) if program.get("id") else None,
                    platform=item.get("platform") or "",
                    post_date=post_date,
                    url=item.get("url") or "",
                    transcript_or_caption=item.get("description") or item.get("title") or "",
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
            for snapshot in resp.json().get("history", []):
                snap_date = snapshot.get("date")
                if not _after(snap_date, since):
                    continue
                metrics.append(
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
        return metrics
