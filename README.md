# SideShift Scanner

An open-source MCP server on top of [SideShift](https://sideshift.app)
UGC creator-program data. It syncs your program's creators, posts, and
performance history into a local SQLite file, then exposes it as MCP
tools — so you just *talk* to your data through an AI coding agent
(Claude Code, Claude Desktop, Cowork) instead of clicking through a UI.

The point isn't to re-display what SideShift's own dashboard already
shows you — it's to answer things it doesn't: real format-trend
detection (from hashtags, not a guess), which creator actually fits a
new brief and why, drafted content briefs in a creator's own style.

Full build spec: [docs/build-spec.md](docs/build-spec.md).

Not affiliated with or endorsed by SideShift. This is an independent
analysis layer built on top of program data you already have access to.

## How it works

Three steps, and the third one is the only one you repeat:

1. **Add your API key** — copy `.env.example` to `.env`, paste in
   `SIDESHIFT_API_KEY` (from Settings → Integrations in the SideShift
   dashboard). `.env` is gitignored and auto-loaded, no manual `export`.
2. **Sync** — pulls your creators/posts/metrics into a local SQLite
   file (`data/ugc_analytics.db`).
3. **Ask about it** — connect the MCP server to Claude Code/Desktop
   once, then just ask questions in normal chat. The model calls the
   tools itself; there's nothing else to run.

## Quickstart

Assumes [Setup](#setup) is already done. This is what to run if you're
coming back after closing your terminal.

**Wire up the agent connection** (one-time):

```bash
cp .mcp.json.example .mcp.json   # then edit: fill in the absolute path to .venv/bin/python
```

Restart your Claude Code/Desktop session so it picks up the new
project-scoped MCP server, then just ask, in normal chat:

- *"Sync my latest SideShift data"*
- *"What are my top performing creators this month?"*
- *"Recommend a creator for a hook-question style unboxing video"*

That's the whole workflow. No dashboard, no separate app to keep open —
sync and analysis both happen as tool calls inside the conversation.

**If you'd rather not use an agent**, the CLI does the same things:

```bash
python -m ugc_analytics.cli sync --method api
python -m ugc_analytics.cli top-performers --metric views -n 5
```

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
in the SideShift dashboard). `.env` is gitignored and auto-loaded by both
the CLI and the MCP server — no manual `export` needed.

## Ingest data

```bash
# zero-setup, against the bundled sample data
python -m ugc_analytics.cli sync --source sample_data

# against your real SideShift account (reads SIDESHIFT_API_KEY from .env)
python -m ugc_analytics.cli sync --method api
```

Or just ask an MCP-connected agent to sync it for you (see Quickstart).
Want it to refresh automatically instead of on request? A local cron
job calling the same command on a schedule works well:
```
0 8 * * * cd /path/to/sideshift-scanner && .venv/bin/python -m ugc_analytics.cli sync --method api >> data/sync.log 2>&1
```

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
