# SideShift Scanner

An open-source analysis layer on top of [SideShift](https://sideshift.app)
UGC creator-program data. The point isn't to re-display what SideShift's
own dashboard already shows you — it's to answer things SideShift
doesn't: real format-trend detection (from hashtags, not a guess), which
creator actually fits a new brief and why, and being able to just *ask*
about your data in plain language through an AI coding agent instead of
clicking through filters.

Full build spec: [docs/build-spec.md](docs/build-spec.md).

Not affiliated with or endorsed by SideShift. This is an independent
analysis layer built on top of program data you already have access to.

## Quickstart

Everything below assumes setup is already done (see [Setup](#setup)).
This is what to run if you're coming back after closing your terminal.

**Talk to your data through an agent** — this is the core way to use
this tool, not an afterthought. Wire the MCP server into Claude Code,
Claude Desktop, or Cowork once:

```bash
cp .mcp.json.example .mcp.json   # then edit: fill in the absolute path to .venv/bin/python
```

Restart your Claude Code/Desktop session, then just ask, in normal chat:
- *"What are my top performing creators this month?"*
- *"Recommend a creator for a hook-question style unboxing video"*
- *"Sync my latest data and tell me what's trending"*

No commands to remember — the model calls the tools itself. Details in
[Run the MCP server](#run-the-mcp-server).

**Or open the dashboard** for an at-a-glance view:

```bash
cd /path/to/sideshift-scanner && source .venv/bin/activate && python -m ugc_analytics.webapp
```

Then open <http://127.0.0.1:8420>. It's a plain local process — Ctrl+C
stops it, running the same command starts it again, nothing else to
manage. The dashboard stays intentionally minimal (stat cards, trending
formats, a creator grid); anything more specific — a different metric,
a date range, filtering unlisted creators — is a chat question away
once the MCP server's connected, not another button to add.

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
| `top_performers` | Ranked list by a chosen metric; `include_unlisted` toggles ghost-handle/removed-creator content |
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

Opens a clean local dashboard at http://127.0.0.1:8420 — one page, no
tabs: stat cards, a live feed of what's being asked through Claude Code/
Desktop chat ("From your agent chat", polls every 5s), trending
formats, top performers, and a compact creator list, plus one "Sync
Data" button. No accounts, no auth: it's a single local SQLite file. Set
`SIDESHIFT_API_KEY` before starting it to have Sync pull from the real
API instead of `sample_data/`. Kept deliberately minimal — for a
different metric, a date range, or filtering out unlisted/ghost-handle
creators, ask via chat (see Quickstart) instead of hunting for a toggle.

## Run the MCP server

```bash
python -m ugc_analytics.server
```

To use it directly from Claude Code, Claude Desktop, or Cowork instead
of the CLI, copy `.mcp.json.example` to `.mcp.json` (project-scoped, for
Claude Code) and fill in the absolute path to your `.venv/bin/python`.
`.mcp.json` is gitignored since that path is machine-specific. Once
connected, you can ask things like "who are my top performing creators"
or "recommend a creator for an unboxing brief" directly in chat — the
model calls the tools itself.

## Run tests

```bash
pytest
```

## Open questions (from the spec)

- Roster-only, or also profiling applicants who haven't posted yet?
- Single-user (local SQLite) or shared/hosted (Postgres)?

(Resolved: SideShift's Post schema does carry `earnings` — ingested as
`revenue` on each post's latest metrics snapshot. It's a running total,
not a per-day breakdown, and reads null across the board on accounts
where no payouts have run yet.)

## Ideas not built yet

- Real content-style classification from captions/titles beyond
  hashtag extraction (e.g. an LLM tagging pass for tone/hook style).

## Contributing

Issues and PRs welcome — in particular, someone with real SideShift
dashboard access smoke-testing `ingestion/api_adapter.py` against a live
API key (it's currently verified against fixture responses shaped like
the published OpenAPI spec, not a live account).

## License

[MIT](LICENSE)
