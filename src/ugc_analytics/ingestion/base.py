"""Ingestion adapter interface.

Per docs/build-spec.md section 4, the SideShift access method (API, CSV
export, or browser scrape) is an open question. Everything downstream —
the schema, the analysis engine, the MCP tools — is written against the
normalized dataclasses in models.py, not against any particular ingestion
mechanism. To add a new source, implement `IngestionAdapter` and hand it
to `sync_all`.
"""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from datetime import date

from ugc_analytics.db import (
    log_sync,
    upsert_campaign,
    upsert_content_item,
    upsert_creator,
    upsert_performance_metric,
)
from ugc_analytics.models import Campaign, ContentItem, Creator, PerformanceMetric, SyncResult


class IngestionAdapter(ABC):
    """Pulls data from a source and yields normalized records.

    Implementations should be side-effect-free with respect to the
    database — `sync_all` handles all upserts and logging so every
    adapter is exercised the same way.
    """

    method: str = "unknown"

    @abstractmethod
    def fetch_creators(self, since: date | None = None) -> list[Creator]:
        ...

    @abstractmethod
    def fetch_campaigns(self, since: date | None = None) -> list[Campaign]:
        ...

    @abstractmethod
    def fetch_content_items(self, since: date | None = None) -> list[ContentItem]:
        ...

    @abstractmethod
    def fetch_performance_metrics(self, since: date | None = None) -> list[PerformanceMetric]:
        ...


def sync_all(conn: sqlite3.Connection, adapter: IngestionAdapter, since: date | None = None) -> SyncResult:
    """Runs a full sync through the given adapter and upserts into `conn`.

    Order matters: campaigns and creators before content_items (FK),
    content_items before performance_metrics (FK).
    """
    try:
        campaigns = adapter.fetch_campaigns(since)
        for c in campaigns:
            upsert_campaign(conn, c)

        creators = adapter.fetch_creators(since)
        for c in creators:
            upsert_creator(conn, c)

        content_items = adapter.fetch_content_items(since)
        for item in content_items:
            upsert_content_item(conn, item)

        metrics = adapter.fetch_performance_metrics(since)
        for m in metrics:
            upsert_performance_metric(conn, m)

        rows = len(creators) + len(content_items) + len(metrics) + len(campaigns)
        result = SyncResult(
            method=adapter.method,
            creators_ingested=len(creators),
            content_items_ingested=len(content_items),
            metrics_ingested=len(metrics),
            status="ok",
        )
        log_sync(conn, adapter.method, rows, "ok")
        conn.commit()
        return result
    except Exception as exc:  # noqa: BLE001 - surfaced to caller via SyncResult + sync_log
        conn.rollback()
        log_sync(conn, adapter.method, 0, "error", detail=str(exc))
        conn.commit()
        return SyncResult(method=adapter.method, status="error", detail=str(exc))
