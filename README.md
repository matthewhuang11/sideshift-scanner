# SideShift Scanner

An open-source MCP server for pulling UGC creator-program data out of
[SideShift](https://sideshift.app), profiling creators, tracking content
performance, and recommending creators for a given brief or format.

Full build spec: [docs/build-spec.md](docs/build-spec.md).

Not affiliated with or endorsed by SideShift. This is an independent
analysis layer built on top of program data you already have access to.

## Status

**Phase 0 is resolved.** SideShift publishes a public, API-key-authenticated
REST API — docs at [app.sideshift.app/docs](https://app.sideshift.app/docs),
no login required to view them, OpenAPI spec at
`app.sideshift.app/openapi/sideshift-api-public.yaml`. `ingestion/api_adapter.py`
implements the real adapter (`GET /creators`, `/programs`, `/posts`,
`/posts/{id}/metrics-history`); get a key from Settings → Integrations in the
SideShift dashboard (requires an active subscription). The **CSV adapter**
still ships alongside it as a zero-setup path for trying the tool against
`sample_data/` without any credentials.

## Layout

```
src/ugc_analytics/
  db.py              SQLite schema + connection helpers
  models.py           dataclasses for the internal schema
  ingestion/
    base.py            IngestionAdapter interface + SyncResult
    csv_adapter.py      reads creators.csv / content_items.csv / performance_metrics.csv
    api_adapter.py       real SideShift API adapter (GET /creators, /programs, /posts, /posts/{id}/metrics-history)
  analysis/
    profiling.py         creator niche/style tagging
    performance.py        aggregation + roster-baseline comparisons
    trends.py              format/hook clustering vs. baseline
    matching.py             creator-for-brief scoring
    briefs.py                generate_content_brief drafting
  server.py            MCP server wiring the tools below
  cli.py               local CLI (sync, list-creators, top-performers, ...)
  webapp.py            local read-only web dashboard (FastAPI)
  static/              dashboard frontend (vanilla HTML/CSS/JS, no build step)
sample_data/            example CSVs matching the ingestion adapter's expected shape
tests/                 unit tests for db, ingestion, and analysis
```

## MCP tools

| Tool | Purpose |
|---|---|
| `sync_data` | Pull latest data via `method='csv'` or `method='api'`, upsert into SQLite |
| `list_creators` | Filter creators by niche / platform / status |
| `get_creator_profile` | Full profile: niche, style, platforms, performance history, best formats |
| `get_performance_summary` | Aggregate metrics + trend direction, scoped to creator/campaign/format/global |
| `top_performers` | Ranked list by a chosen metric |
| `detect_trending_formats` | Format/hook clusters outperforming the roster baseline |
| `recommend_creators_for_brief` | Ranked creators for a brief/format, with rationale |
| `generate_content_brief` | Draft a brief in a creator's own style, targeting a given or trending format |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

To use the real SideShift API instead of sample data, copy `.env.example`
to `.env` and fill in `SIDESHIFT_API_KEY` (from Settings -> Integrations
in the SideShift dashboard). `.env` is gitignored and auto-loaded by the
CLI, MCP server, and web dashboard — no manual `export` needed.

## Ingest data

```bash
# zero-setup, against the bundled sample data
python -m ugc_analytics.cli sync --source sample_data

# against your real SideShift account (reads SIDESHIFT_API_KEY from .env)
python -m ugc_analytics.cli sync --method api
```

## Run the dashboard

```bash
python -m ugc_analytics.webapp
```

Opens a clean local dashboard at http://127.0.0.1:8420 — stat cards, a
creator grid, trending formats, and a ranked top-performers view, with
one "Sync Data" button. No accounts, no auth: it's a single local
SQLite file. Set `SIDESHIFT_API_KEY` before starting it to have Sync
pull from the real API instead of `sample_data/`.

## Run the MCP server

```bash
python -m ugc_analytics.server
```

## Run tests

```bash
pytest
```

## Open questions (from the spec)

- Does SideShift expose conversion/revenue attribution per creator, or only engagement metrics? (the public API's Post schema has `earnings`/`paid`, but no per-day revenue snapshot)
- Roster-only, or also profiling applicants who haven't posted yet?
- Single-user (local SQLite) or shared/hosted (Postgres)?

## Contributing

Issues and PRs welcome — in particular, someone with real SideShift
dashboard access smoke-testing `ingestion/api_adapter.py` against a live
API key (it's currently verified against fixture responses shaped like
the published OpenAPI spec, not a live account).

## License

[MIT](LICENSE)
