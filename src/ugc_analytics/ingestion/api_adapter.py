"""Stub for a future SideShift API/webhook adapter.

Fill this in once Phase 0 (docs/build-spec.md section 4) is resolved and
SideShift confirms a REST/GraphQL API or webhook feed. Until then this
adapter exists so the shape of the swap is obvious: implement the same
four `fetch_*` methods as `CSVIngestionAdapter`, normalize whatever the
API returns into the models.py dataclasses, and nothing else in the
codebase needs to change.
"""

from __future__ import annotations

from datetime import date

from ugc_analytics.ingestion.base import IngestionAdapter
from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric


class SideShiftAPIAdapter(IngestionAdapter):
    method = "api"

    def __init__(self, api_base_url: str, api_key: str):
        self.api_base_url = api_base_url
        self.api_key = api_key

    def fetch_creators(self, since: date | None = None) -> list[Creator]:
        raise NotImplementedError(
            "SideShift API access has not been confirmed yet (build spec section 4). "
            "Once confirmed, implement this against the real endpoint."
        )

    def fetch_campaigns(self, since: date | None = None) -> list[Campaign]:
        raise NotImplementedError("See fetch_creators.")

    def fetch_content_items(self, since: date | None = None) -> list[ContentItem]:
        raise NotImplementedError("See fetch_creators.")

    def fetch_performance_metrics(self, since: date | None = None) -> list[PerformanceMetric]:
        raise NotImplementedError("See fetch_creators.")
