const ACTIVITY_POLL_MS = 5000;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function fmtNum(n) {
  if (n === null || n === undefined) return "—";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return Math.round(n).toLocaleString();
}

function fmtPct(n) {
  if (n === null || n === undefined) return "—";
  return (n * 100).toFixed(1) + "%";
}

function timeAgo(isoString) {
  const seconds = Math.max(0, (Date.now() - new Date(isoString).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function trendBadge(direction, pct) {
  const arrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "→";
  const cls = direction === "up" ? "trend-up" : direction === "down" ? "trend-down" : "trend-flat";
  const suffix = pct ? ` ${Math.abs(pct)}%` : "";
  return `<span class="trend ${cls}">${arrow}${suffix}</span>`;
}

function safeTags(raw) {
  try {
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function empty(msg) {
  return `<div class="empty">${msg}</div>`;
}

async function loadSummary() {
  const summary = await fetchJSON("/api/summary");
  document.getElementById("stat-creators").textContent = summary.creator_count ?? 0;
  document.getElementById("stat-active").textContent = `${summary.active_creator_count ?? 0} active`;
  document.getElementById("stat-views").textContent = fmtNum(summary.totals?.views);
  document.getElementById("stat-trend").innerHTML = trendBadge(summary.trend_direction, summary.trend_pct);
  document.getElementById("stat-engagement").textContent = fmtPct(summary.averages?.engagement_rate);
  document.getElementById("stat-content").textContent = summary.sample_size ?? 0;
}

async function loadTrending() {
  const trending = await fetchJSON("/api/trending");
  const list = document.getElementById("trending-list");
  list.innerHTML =
    trending
      .slice(0, 8)
      .map(
        (t) => `
      <div class="row">
        <span class="tag">${t.format_tag}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.min(t.multiplier * 40, 100)}%"></div></div>
        <span class="muted">${t.multiplier}x</span>
      </div>`
      )
      .join("") || empty("Not enough data yet — hit Sync.");
}

async function loadTopPerformers() {
  const top = await fetchJSON("/api/top-performers?n=6");
  const list = document.getElementById("top-performers-list");
  list.innerHTML =
    top
      .map(
        (row) => `
      <div class="row">
        <div>
          <div class="row-title">${row.creator_name}</div>
          <div class="muted small">${safeTags(row.format_tags).join(", ")}</div>
        </div>
        <span class="row-value">${fmtNum(row.value)}</span>
      </div>`
      )
      .join("") || empty("No content yet.");
}

async function loadCreators() {
  const creators = await fetchJSON("/api/creators");
  const list = document.getElementById("creators-list");
  list.innerHTML =
    creators
      .map(
        (c) => `
    <div class="row creator-row">
      <div class="creator-row-main">
        <span class="row-title">${c.name}</span>
        <span class="muted small">${c.handle ? "@" + c.handle : ""}</span>
      </div>
      <div class="tag-row">${(c.niche_tags || []).map((t) => `<span class="tag">${t}</span>`).join("")}</div>
      <span class="badge badge-${c.status}">${c.status}</span>
      <span class="muted small">${c.content_count} posts</span>
      ${trendBadge(c.trend_direction, c.trend_pct)}
    </div>`
      )
      .join("") || empty("No creators yet — hit Sync.");
}

async function loadActivity() {
  const entries = await fetchJSON("/api/activity?limit=8");
  const list = document.getElementById("activity-list");
  list.innerHTML =
    entries
      .map(
        (e) => `
    <div class="row">
      <span class="muted small activity-time">${timeAgo(e.timestamp)}</span>
      <span>${e.summary}</span>
    </div>`
      )
      .join("") ||
    empty('Nothing yet — ask something about your data in Claude Code/Desktop chat and it\'ll show up here.');
}

async function refresh() {
  try {
    await Promise.all([loadSummary(), loadTrending(), loadTopPerformers(), loadCreators()]);
  } catch (err) {
    console.error(err);
  }
}

async function sync() {
  const btn = document.getElementById("sync-btn");
  btn.disabled = true;
  btn.textContent = "Syncing…";
  try {
    const result = await fetchJSON("/api/sync", { method: "POST" });
    btn.textContent = result.status === "ok" ? "Synced ✓" : "Sync failed";
  } catch (err) {
    btn.textContent = "Sync failed";
  } finally {
    await refresh();
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = "Sync Data";
    }, 1500);
  }
}

document.getElementById("sync-btn").addEventListener("click", sync);

refresh();
loadActivity();
setInterval(loadActivity, ACTIVITY_POLL_MS);
