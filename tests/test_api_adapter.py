"""Unit tests for SideShiftAPIAdapter against a fake HTTP session.

No live API key is available in this environment, so these tests verify
the adapter's request/pagination/mapping logic against fixture responses
shaped like the published OpenAPI spec (app.sideshift.app/docs), not a
live SideShift account.
"""

from __future__ import annotations

from datetime import date

import pytest

from ugc_analytics.ingestion.api_adapter import SideShiftAPIAdapter


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: dict[str, list[dict]]):
        # responses: path -> list of page payloads (in page order), or a single dict for non-paginated paths
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, headers=None, params=None, timeout=None):
        path = url.split("/api/v1", 1)[1] if "/api/v1" in url else url
        self.calls.append((path, dict(params or {})))
        entry = self.responses[path]
        if isinstance(entry, list):
            page = (params or {}).get("page", 1)
            return FakeResponse(entry[page - 1])
        return FakeResponse(entry)


CREATORS_PAGE = {
    "data": [{"id": "cr1", "name": "Ava Chen", "status": "active"}],
    "page": 1,
    "total": 1,
    "totalPages": 1,
}

PROGRAMS_PAGE = {
    "data": [
        {
            "id": "p1",
            "name": "Spring Push",
            "description": "Unbox the new kit",
            "status": "active",
            "createdAt": 1700000000000,
            "updatedAt": 1700000000000,
        }
    ],
    "page": 1,
    "total": 1,
    "totalPages": 1,
}

POSTS_PAGE = {
    "data": [
        {
            "id": "post1",
            "title": "Unboxing",
            "description": "wait for it",
            "platform": "tiktok",
            "url": "https://tiktok.com/post1",
            "uploadedAt": 1700000000000,
            "createdAt": 1700000000000,
            "contract": {"contractorId": "cr1"},
            "program": {"id": "p1"},
        }
    ],
    "page": 1,
    "total": 1,
    "totalPages": 1,
}

METRICS_HISTORY = {
    "postId": "post1",
    "history": [
        {"date": "2025-03-01", "views": 1000, "likes": 100, "comments": 10, "shares": 5, "bookmarks": 20},
        {"date": "2025-03-08", "views": 2000, "likes": 200, "comments": 20, "shares": 10, "bookmarks": 40},
    ],
    "totalDataPoints": 2,
    "periodDays": 7,
}


def make_adapter():
    session = FakeSession(
        {
            "/creators": [CREATORS_PAGE],
            "/programs": [PROGRAMS_PAGE],
            "/posts": [POSTS_PAGE],
            "/posts/post1/metrics-history": METRICS_HISTORY,
        }
    )
    return SideShiftAPIAdapter(api_key="test-key", session=session), session


def test_fetch_creators_maps_fields():
    adapter, session = make_adapter()
    creators = adapter.fetch_creators()
    assert len(creators) == 1
    assert creators[0].creator_id == "cr1"
    assert creators[0].name == "Ava Chen"
    assert creators[0].status == "active"


def test_fetch_campaigns_maps_fields_and_dates():
    adapter, _ = make_adapter()
    campaigns = adapter.fetch_campaigns()
    assert campaigns[0].campaign_id == "p1"
    assert campaigns[0].brief_text == "Unbox the new kit"
    assert campaigns[0].start_date == "2023-11-14"  # 1700000000000ms


def test_fetch_content_items_pulls_creator_id_from_contract():
    adapter, _ = make_adapter()
    items = adapter.fetch_content_items()
    assert items[0].content_id == "post1"
    assert items[0].creator_id == "cr1"
    assert items[0].campaign_id == "p1"
    assert items[0].platform == "tiktok"


def test_fetch_performance_metrics_expands_history_to_snapshots():
    adapter, _ = make_adapter()
    metrics = adapter.fetch_performance_metrics()
    assert len(metrics) == 2
    assert metrics[0].content_id == "post1"
    assert metrics[0].views == 1000
    assert metrics[1].saves == 40  # bookmarks -> saves


def test_since_filters_out_older_records():
    adapter, _ = make_adapter()
    metrics = adapter.fetch_performance_metrics(since=date(2025, 3, 5))
    assert len(metrics) == 1
    assert metrics[0].snapshot_date == "2025-03-08"


def test_posts_are_only_fetched_once_across_calls():
    adapter, session = make_adapter()
    adapter.fetch_content_items()
    adapter.fetch_performance_metrics()
    posts_calls = [c for c in session.calls if c[0] == "/posts"]
    assert len(posts_calls) == 1


def test_pagination_stops_when_page_reaches_total_pages():
    two_pages = {
        "data": [{"id": f"cr{i}", "name": f"Creator {i}", "status": "active"} for i in range(1)],
        "page": 1,
        "total": 2,
        "totalPages": 2,
    }
    last_page = {
        "data": [{"id": "cr2", "name": "Creator 2", "status": "active"}],
        "page": 2,
        "total": 2,
        "totalPages": 2,
    }
    session = FakeSession({"/creators": [two_pages, last_page]})
    adapter = SideShiftAPIAdapter(api_key="k", session=session)
    creators = adapter.fetch_creators()
    assert [c.creator_id for c in creators] == ["cr0", "cr2"]
