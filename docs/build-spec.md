# UGC Creator Intelligence Tool — Build Spec

**For:** Matthew
**Purpose:** Give Claude Code a spec to build a tool that pulls UGC program data out of SideShift, profiles creators, tracks performance, and helps decide who gets which content format.
**Status:** Draft v1 — open questions flagged inline.

---

## 1. Problem

Program data (creators, submissions, views/engagement/conversions) lives inside SideShift's web dashboard. There's no fast way to query it, profile creators by content style/niche, spot what's performing, or figure out who to send a new format to. This tool closes that loop: pull the data out, structure it, analyze it, and surface recommendations.

## 2. Goals

- Get SideShift data into a queryable local store on a repeatable basis (not a one-time export).
- Build a **creator profile** per person: niche, content style/tone, platforms, historical performance, best-performing formats.
- Build **performance analytics**: per-creator, per-content-piece, per-format, trended over time.
- Support **"what's working" / viral-format detection**: cluster content by format/hook, correlate with performance.
- Support **creator recommendation**: given a format or brief, suggest which creators are the best fit based on past data.
- Ship as an **MCP server** so it's usable from Claude Code, Claude Desktop/Cowork, or any MCP client — not a one-off script.

## 3. Non-goals (v1)

- No auto-posting or campaign management (SideShift already does that).
- No payments/invoicing.
- No creator outreach/DMing automation.
- Not rebuilding SideShift's UI — this is an analysis layer on top of the data.

## 4. Data source: SideShift — key open question

I checked publicly for a SideShift developer API and didn't find one documented (their `/docs` page is behind login, at `app.sideshift.app/docs`). This materially affects the build, so **first task for whoever builds this is to confirm access method** by checking that docs page while logged in, or asking SideShift support directly whether they offer:

1. **A REST/GraphQL API or webhooks** (best case — build a real-time adapter).
2. **CSV/data export** from the dashboard (common fallback — scheduled export + ingest).
3. **Neither** — in which case the tool falls back to browser automation (Claude in Chrome) to read the dashboard tables directly.

The spec below is written so the **ingestion layer is swappable** — build the data model and analysis engine against a stable internal schema, and plug in whichever ingestion method SideShift actually supports behind an adapter interface. Don't hard-couple the analysis logic to how the data arrives.

```
SideShift (API | CSV export | browser scrape)
        │
        ▼
  Ingestion Adapter  →  normalizes to internal schema
        │
        ▼
  Local Data Store (SQLite/DuckDB)
        │
        ▼
  Analysis Engine  (profiling, performance, trends, matching)
        │
        ▼
  MCP Server tools  ←→  Claude (chat / Claude Code / Cowork)
```

## 5. Data model

Local store (SQLite to start — DuckDB if analytical queries get heavy; upgrade to Postgres only if this becomes multi-user).

**`creators`**
| field | notes |
|---|---|
| creator_id | SideShift ID if available, else generated |
| name, handle, platforms | e.g. `{tiktok: "@x", instagram: "@y"}` |
| niche_tags | e.g. `["health & wellness", "unboxing"]` — seeded from SideShift categories, refined by content analysis |
| tone_style_tags | e.g. `["casual", "voiceover", "fast-cut"]` — derived, not from SideShift |
| audience_notes | demographics/engagement quality if SideShift exposes it |
| status | active / inactive / applied |
| joined_date | |

**`content_items`**
| field | notes |
|---|---|
| content_id | |
| creator_id | FK |
| campaign_id | FK, nullable |
| platform | tiktok / instagram / youtube / etc |
| format_tags | e.g. `["unboxing", "voiceover", "15-30s", "hook-question"]` |
| post_date | |
| url | |
| transcript_or_caption | for content analysis, if retrievable |

**`performance_metrics`**
| field | notes |
|---|---|
| content_id | FK |
| views, likes, comments, shares, saves | as available |
| ctr, conversions, revenue | if SideShift tracks conversion attribution |
| engagement_rate | computed |
| snapshot_date | metrics change over time — store time series, not just latest |

**`campaigns`** (optional, if briefs are tracked)
| field | notes |
|---|---|
| campaign_id, name, brief_text, target_format, start_date | |

**`sync_log`**
| field | notes |
|---|---|
| sync_id, timestamp, method (api/csv/scrape), rows_ingested, status | for debugging ingestion |

## 6. MCP server tools

Expose these as MCP tools so Claude can call them naturally in conversation:

| Tool | Input | Output |
|---|---|---|
| `sync_data` | `{since?: date}` | Pulls latest from SideShift via the ingestion adapter, upserts into local store, returns sync summary |
| `list_creators` | `{filters?: niche, platform, status}` | Table of creators matching filters |
| `get_creator_profile` | `{creator_id or handle}` | Full profile: niche, style, platforms, performance history, best formats |
| `get_performance_summary` | `{scope: creator/campaign/format/global, date_range?}` | Aggregate metrics, trend direction |
| `top_performers` | `{metric: views/engagement/conversions, n, date_range?}` | Ranked list |
| `detect_trending_formats` | `{date_range?, min_sample_size?}` | Format/hook clusters correlated with above-average performance |
| `recommend_creators_for_brief` | `{brief_text or format_tags}` | Ranked creators with rationale ("matches their top format, historically 2.3x avg engagement on similar content") |
| `generate_content_brief` | `{creator_id, based_on?: trending_format_id}` | Draft brief tailored to that creator's style + a chosen format (stretch goal, v2) |

## 7. Analysis engine — what "analyze" actually means here

1. **Creator profiling**: classify each creator's typical format, tone, and niche from their content history (captions/transcripts + SideShift category tags). Use an LLM call (Claude via the MCP tool, or a lightweight local classification step) to tag style attributes that SideShift doesn't provide natively.
2. **Performance tracking**: standard aggregation — per creator, per format, per platform, trended over time, with simple statistical baselines (e.g., "2x above roster average") rather than vague qualitative claims.
3. **Trend/viral format detection**: group content by format tags (hook type, length, structure), compute average performance per group, surface which formats are outperforming the roster baseline.
4. **Creator-format matching**: given a target format or new brief, score creators by historical performance on similar formats + niche fit, return ranked recommendations with the reasoning shown (not a black-box score).

## 8. Tech stack recommendation

- **Language**: Python (pandas/duckdb for analysis, fast to iterate) or TypeScript if you want tighter integration with an MCP ecosystem already in TS. Python is the more common choice for this kind of data/analysis-heavy MCP server.
- **MCP server framework**: official `mcp` Python SDK (or `@modelcontextprotocol/sdk` if TS).
- **Storage**: SQLite file, single-file, zero-ops. Move to DuckDB if analytical queries (grouping, window functions over large content sets) get slow.
- **Ingestion**:
  - If SideShift has an API/webhooks → scheduled poll or webhook receiver.
  - If CSV export only → a `sync_data` step that reads a dropped-in export file (manual or via a watched folder).
  - If neither → Claude in Chrome browser automation to read dashboard tables (slowest, most brittle — last resort).
- **Scheduling**: use a scheduled task (daily sync) once the ingestion adapter is stable, so profiles/analytics stay current without manual syncing.

## 9. Build phases

**Phase 0 — Confirm ingestion path.** Log into SideShift, check `app.sideshift.app/docs` for API docs, or ask their support about API/export access. This determines Phase 1 scope. (Do this before writing ingestion code.)

**Phase 1 — Ingestion + data model.** Build the adapter for whichever method is available, stand up the SQLite schema, get one full sync working end-to-end.

**Phase 2 — Core MCP tools.** `sync_data`, `list_creators`, `get_creator_profile`, `get_performance_summary`, `top_performers`. This alone gets you "access and analyze the data quickly."

**Phase 3 — Trend + matching engine.** `detect_trending_formats`, `recommend_creators_for_brief`. This is the "know enough about creators to tailor formats" layer.

**Phase 4 (stretch)** — `generate_content_brief` auto-drafting, scheduled daily sync, a simple dashboard artifact view on top of the MCP data.

## 10. Open questions for you

- Does SideShift expose conversion/revenue attribution per creator, or only engagement metrics? Changes what "performance" can mean.
- Do you want this scoped to your current roster only, or should it also help evaluate applicants who haven't posted yet (profile from portfolio/past work elsewhere)?
- Single-user tool (local SQLite, runs on your machine) or something a small team needs shared access to (would push toward Postgres + hosted MCP server)?
