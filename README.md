# SideShift Scanner

An open-source MCP server for pulling UGC creator-program data out of
[SideShift](https://sideshift.app), profiling creators, tracking content
performance, and recommending creators for a given brief or format.

Full build spec: [docs/build-spec.md](docs/build-spec.md).

Not affiliated with or endorsed by SideShift. This is an independent
analysis layer built on top of program data you already have access to.

## Status

**Phase 0 (SideShift ingestion path) is still unconfirmed.** Nobody has
verified whether SideShift exposes a REST/GraphQL API, a CSV export, or
neither (see `docs/build-spec.md` section 4). Until that's confirmed, this
repo ships with a working **CSV ingestion adapter** so the data model,
storage, and analysis engine can be built and tested end-to-end against
real-shaped data. Swap in an API adapter later without touching anything
downstream of `ingestion/base.py`.

## Layout

```
src/ugc_analytics/
  db.py              SQLite schema + connection helpers
  models.py           dataclasses for the internal schema
  ingestion/
    base.py            IngestionAdapter interface + SyncResult
    csv_adapter.py      reads creators.csv / content_items.csv / performance_metrics.csv
    api_adapter.py       stub for a future SideShift API/webhook adapter
  analysis/
    profiling.py         creator niche/style tagging
    performance.py        aggregation + roster-baseline comparisons
    trends.py              format/hook clustering vs. baseline
    matching.py             creator-for-brief scoring
  server.py            MCP server wiring the tools below
sample_data/            example CSVs matching the ingestion adapter's expected shape
tests/                 unit tests for db + analysis
```

## MCP tools

| Tool | Purpose |
|---|---|
| `sync_data` | Pull latest data via the active ingestion adapter, upsert into SQLite |
| `list_creators` | Filter creators by niche / platform / status |
| `get_creator_profile` | Full profile: niche, style, platforms, performance history, best formats |
| `get_performance_summary` | Aggregate metrics + trend direction, scoped to creator/campaign/format/global |
| `top_performers` | Ranked list by a chosen metric |
| `detect_trending_formats` | Format/hook clusters outperforming the roster baseline |
| `recommend_creators_for_brief` | Ranked creators for a brief/format, with rationale |

`generate_content_brief` (v2 stretch) is not implemented yet.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Ingest sample data

```bash
python -m ugc_analytics.cli sync --source sample_data
```

## Run the MCP server

```bash
python -m ugc_analytics.server
```

## Run tests

```bash
pytest
```

## Open questions (from the spec)

- Does SideShift expose conversion/revenue attribution per creator, or only engagement metrics?
- Roster-only, or also profiling applicants who haven't posted yet?
- Single-user (local SQLite) or shared/hosted (Postgres)?

## Contributing

Issues and PRs welcome — especially confirmation of a real SideShift
API/export path (see `docs/build-spec.md` section 4) so `ingestion/api_adapter.py`
can be filled in for real.

## License

[MIT](LICENSE)
