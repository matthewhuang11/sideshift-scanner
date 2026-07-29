const state = { view: "dashboard" };
const titles = {
  dashboard: "Dashboard",
  creators: "Creators",
  trending: "Trending Formats",
  "top-performers": "Top Performers",
};

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

async function loadDashboard() {
  const [summary, trending, top] = await Promise.all([
    fetchJSON("/api/summary"),
    fetchJSON("/api/trending"),
    fetchJSON("/api/top-performers?n=5"),
  ]);

  document.getElementById("stat-creators").textContent = summary.creator_count ?? 0;
  document.getElementById("stat-active").textContent = `${summary.active_creator_count ?? 0} active`;
  document.getElementById("stat-views").textContent = fmtNum(summary.totals?.views);
  document.getElementById("stat-trend").innerHTML = trendBadge(summary.trend_direction, summary.trend_pct);
  document.getElementById("stat-engagement").textContent = fmtPct(summary.averages?.engagement_rate);
  document.getElementById("stat-content").textContent = summary.sample_size ?? 0;

  const trendList = document.getElementById("trending-list");
  trendList.innerHTML =
    trending
      .slice(0, 6)
      .map(
        (t) => `
      <div class="row">
        <span class="tag">${t.format_tag}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.min(t.multiplier * 40, 100)}%"></div></div>
        <span class="muted">${t.multiplier}x</span>
      </div>`
      )
      .join("") || empty("Not enough data yet — hit Sync.");

  const topList = document.getElementById("top-performers-list");
  topList.innerHTML =
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
  const grid = document.getElementById("creators-grid");
  grid.innerHTML =
    creators
      .map(
        (c) => `
    <div class="card creator-card">
      <div class="creator-card-header">
        <div>
          <div class="row-title">${c.name}</div>
          <div class="muted small">${c.handle || ""}</div>
        </div>
        <span class="badge badge-${c.status}">${c.status}</span>
      </div>
      <div class="tag-row">${(c.niche_tags || []).map((t) => `<span class="tag">${t}</span>`).join("")}</div>
      <div class="creator-stats">
        <div><span class="muted small">Posts</span><br>${c.content_count}</div>
        <div><span class="muted small">Avg Eng.</span><br>${fmtPct(c.avg_engagement_rate)}</div>
        <div><span class="muted small">Trend</span><br>${trendBadge(c.trend_direction, c.trend_pct)}</div>
      </div>
    </div>`
      )
      .join("") || empty("No creators yet — hit Sync.");
}

async function loadTrending() {
  const trending = await fetchJSON("/api/trending");
  const list = document.getElementById("trending-full-list");
  list.innerHTML =
    trending
      .map(
        (t) => `
    <div class="row">
      <span class="tag">${t.format_tag}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.min(t.multiplier * 40, 100)}%"></div></div>
      <span class="muted small">${t.multiplier}x baseline &middot; n=${t.sample_size}</span>
    </div>`
      )
      .join("") || empty("Not enough data yet — hit Sync.");
}

async function loadTopPerformers() {
  const metric = document.getElementById("metric-select").value;
  const top = await fetchJSON(`/api/top-performers?metric=${metric}&n=20`);
  const format = metric === "engagement_rate" ? fmtPct : fmtNum;
  const list = document.getElementById("top-performers-full-list");
  list.innerHTML =
    top
      .map(
        (row, i) => `
    <div class="row">
      <span class="rank">${i + 1}</span>
      <div>
        <div class="row-title">${row.creator_name}</div>
        <div class="muted small">${row.platform} &middot; ${safeTags(row.format_tags).join(", ")}</div>
      </div>
      <span class="row-value">${format(row.value)}</span>
    </div>`
      )
      .join("") || empty("No content yet.");
}

async function refresh() {
  try {
    if (state.view === "dashboard") await loadDashboard();
    if (state.view === "creators") await loadCreators();
    if (state.view === "trending") await loadTrending();
    if (state.view === "top-performers") await loadTopPerformers();
  } catch (err) {
    console.error(err);
  }
}

function showView(view) {
  state.view = view;
  document.getElementById("page-title").textContent = titles[view];
  document.querySelectorAll(".view").forEach((el) => el.classList.toggle("hidden", el.dataset.view !== view));
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  refresh();
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

document.querySelectorAll(".nav-item").forEach((el) => el.addEventListener("click", () => showView(el.dataset.view)));
document.getElementById("sync-btn").addEventListener("click", sync);
document.getElementById("metric-select")?.addEventListener("change", loadTopPerformers);

showView("dashboard");
