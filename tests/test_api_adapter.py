"""Unit tests for SideShiftAPIAdapter against a fake HTTP session.

Fixtures are shaped like real responses from a live SideShift account,
not the published OpenAPI docs — those docs disagree with reality in
three ways this test suite pins down (see api_adapter.py's module
docstring): epoch units, top-level vs. nested contractorId/programId,
and metrics-history's wrapping "data" key.
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
    "data": [
        {
            "id": "cr1",
            "name": "Ava Chen",
            "campaigns": [
                {
                    "programId": "p1",
                    "programName": "Spring Push",
                    "contractId": "contract-1",
                    "contractStatus": "active",
                    "handles": [
                        {"platform": "tiktok", "handle": "avachen"},
                        {"platform": "instagram", "handle": "ava.chen"},
                    ],
                }
            ],
        }
    ],
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
            "createdAt": 1700000000,  # Unix seconds, not ms
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
            "platform": "tiktok",
            "postPage": "https://tiktok.com/post1",
            "uploadedAt": 1700000000,  # Unix seconds, not ms
            "creator": "avachen",
            "contractorId": "cr1",  # top-level, not nested under "contract"
            "programId": "p1",  # top-level, not nested under "program"
        }
    ],
    "page": 1,
    "total": 1,
    "totalPages": 1,
}

# /posts/{id}/metrics-history wraps its payload in a top-level "data" key.
METRICS_HISTORY = {
    "data": {
        "postId": "post1",
        "history": [
            {"date": "2025-03-01", "views": 1000, "likes": 100, "comments": 10, "shares": 5, "bookmarks": 20},
            {"date": "2025-03-08", "views": 2000, "likes": 200, "comments": 20, "shares": 10, "bookmarks": 40},
        ],
        "totalDataPoints": 2,
        "periodDays": 7,
    }
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


def test_fetch_creators_derives_platforms_from_campaign_handles():
    adapter, _ = make_adapter()
    creators = adapter.fetch_creators()
    assert creators[0].platforms == {"tiktok": "avachen", "instagram": "ava.chen"}
    assert creators[0].handle == "avachen"


def test_fetch_campaigns_maps_fields_and_dates():
    adapter, _ = make_adapter()
    campaigns = adapter.fetch_campaigns()
    assert campaigns[0].campaign_id == "p1"
    assert campaigns[0].brief_text == "Unbox the new kit"
    assert campaigns[0].start_date == "2023-11-14"  # 1700000000s


def test_fetch_content_items_pulls_creator_id_from_top_level_contractor_id():
    adapter, _ = make_adapter()
    items = adapter.fetch_content_items()
    assert items[0].content_id == "post1"
    assert items[0].creator_id == "cr1"
    assert items[0].campaign_id == "p1"
    assert items[0].platform == "tiktok"
    assert items[0].url == "https://tiktok.com/post1"


def test_fetch_performance_metrics_unwraps_data_key_and_expands_history():
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
        "data": [{"id": "cr0", "name": "Creator 0"}],
        "page": 1,
        "total": 2,
        "totalPages": 2,
    }
    last_page = {
        "data": [{"id": "cr2", "name": "Creator 2"}],
        "page": 2,
        "total": 2,
        "totalPages": 2,
    }
    session = FakeSession({"/creators": [two_pages, last_page]})
    adapter = SideShiftAPIAdapter(api_key="k", session=session)
    creators = adapter.fetch_creators()
    assert [c.creator_id for c in creators] == ["cr0", "cr2"]


def test_epoch_to_date_handles_milliseconds_too():
    """The published docs claim ms; live data is actually seconds. Handle both."""
    ms_session = FakeSession(
        {
            "/programs": [
                {
                    "data": [{"id": "p1", "name": "X", "createdAt": 1700000000000}],  # ms
                    "page": 1,
                    "total": 1,
                    "totalPages": 1,
                }
            ]
        }
    )
    adapter = SideShiftAPIAdapter(api_key="k", session=ms_session)
    campaigns = adapter.fetch_campaigns()
    assert campaigns[0].start_date == "2023-11-14"
