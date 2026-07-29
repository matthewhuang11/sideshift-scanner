"""Small CLI for local use without going through an MCP client.

    python -m ugc_analytics.cli sync --source sample_data
    python -m ugc_analytics.cli top-performers --metric views -n 5
    python -m ugc_analytics.cli trending-formats
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from ugc_analytics.analysis.briefs import generate_content_brief
from ugc_analytics.analysis.performance import get_performance_summary, top_performers
from ugc_analytics.analysis.profiling import get_creator_profile, list_creators
from ugc_analytics.analysis.trends import detect_trending_formats
from ugc_analytics.db import DEFAULT_DB_PATH, get_connection, init_db
from ugc_analytics.ingestion.api_adapter import SideShiftAPIAdapter
from ugc_analytics.ingestion.base import sync_all
from ugc_analytics.ingestion.csv_adapter import CSVIngestionAdapter

load_dotenv()


def _print(obj) -> None:
    if hasattr(obj, "__dataclass_fields__"):
        obj = asdict(obj)
    elif isinstance(obj, list) and obj and hasattr(obj[0], "__dataclass_fields__"):
        obj = [asdict(o) for o in obj]
    print(json.dumps(obj, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ugc-analytics")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to the SQLite store")
    sub = parser.add_subparsers(dest="command", required=True)

    sync_p = sub.add_parser("sync", help="Ingest data via the CSV or SideShift API adapter")
    sync_p.add_argument("--method", default="csv", choices=["csv", "api"])
    sync_p.add_argument("--source", default="sample_data", help="Directory containing the CSV files (method=csv)")
    sync_p.add_argument("--api-key", default=None, help="SideShift API key (method=api; defaults to $SIDESHIFT_API_KEY)")
    sync_p.add_argument("--since", default=None, help="Only ingest records on/after this date (YYYY-MM-DD)")

    creators_p = sub.add_parser("list-creators")
    creators_p.add_argument("--niche", default=None)
    creators_p.add_argument("--platform", default=None)
    creators_p.add_argument("--status", default=None)

    profile_p = sub.add_parser("creator-profile")
    profile_p.add_argument("--creator-id", default=None)
    profile_p.add_argument("--handle", default=None)

    summary_p = sub.add_parser("performance-summary")
    summary_p.add_argument("--scope", default="global", choices=["global", "creator", "campaign", "format"])
    summary_p.add_argument("--scope-id", default=None)

    top_p = sub.add_parser("top-performers")
    top_p.add_argument("--metric", default="views")
    top_p.add_argument("-n", type=int, default=10)

    sub.add_parser("trending-formats")

    brief_p = sub.add_parser("content-brief")
    brief_p.add_argument("--creator-id", required=True)
    brief_p.add_argument("--format", dest="based_on_format", default=None)

    args = parser.parse_args(argv)
    conn = get_connection(Path(args.db))
    init_db(conn)

    if args.command == "sync":
        since = date.fromisoformat(args.since) if args.since else None
        if args.method == "api":
            api_key = args.api_key or os.environ.get("SIDESHIFT_API_KEY")
            if not api_key:
                parser.error("--api-key or $SIDESHIFT_API_KEY is required for --method api")
            adapter = SideShiftAPIAdapter(api_key=api_key)
        else:
            adapter = CSVIngestionAdapter(args.source)
        result = sync_all(conn, adapter, since)
        _print(result)
    elif args.command == "list-creators":
        _print(list_creators(conn, niche=args.niche, platform=args.platform, status=args.status))
    elif args.command == "creator-profile":
        if not args.creator_id and not args.handle:
            parser.error("--creator-id or --handle is required")
        profile = get_creator_profile(conn, creator_id=args.creator_id, handle=args.handle)
        _print(profile)
    elif args.command == "performance-summary":
        _print(get_performance_summary(conn, scope=args.scope, scope_id=args.scope_id))
    elif args.command == "top-performers":
        _print(top_performers(conn, metric=args.metric, n=args.n))
    elif args.command == "trending-formats":
        _print(detect_trending_formats(conn))
    elif args.command == "content-brief":
        _print(generate_content_brief(conn, creator_id=args.creator_id, based_on_format=args.based_on_format))

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
