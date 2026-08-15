/* Trend / history page: tag picker + time range + SVG line chart.
 * Colors are the validated categorical palette from the dataviz skill
 * (fixed order, never cycled/reassigned when the selection changes). */

const TREND_PALETTE = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
];
const TREND_MAX_SERIES = TREND_PALETTE.length;

const TREND_RANGES = [
  { label: "15m", ms: 15 * 60 * 1000 },
  { label: "1h", ms: 60 * 60 * 1000 },
  { label: "6h", ms: 6 * 60 * 60 * 1000 },
  { label: "24h", ms: 24 * 60 * 60 * 1000 },
  { label: "7d", ms: 7 * 24 * 60 * 60 * 1000 },
];

let trendSelectedTags = [];
let trendRangeMs = TREND_RANGES[1].ms;
let trendAutoRefreshTimer = null;
let trendLastData = null;

function stopTrendAutoRefresh() { if (trendAutoRefreshTimer) { clearInterval(trendAutoRefreshTimer); trendAutoRefreshTimer = null; } }

function trendColor(tagName) {
  const idx = trendSelectedTags.indexOf(tagName);
  return TREND_PALETTE[idx % TREND_PALETTE.length];
}

async function viewTrend() {
  setHeader("Trend", "Historical values from the data historian", "");
  const content = document.getElementById("content");

  let knownTags = [];
  let status = null;
  try { knownTags = await Api.get("/api/tags/known"); } catch (e) { /* ignore */ }
  try { status = await Api.get("/api/history/status"); } catch (e) { /* ignore */ }

  content.innerHTML = `
    <div class="card">
      <div class="card-body">
        <div class="toolbar" style="flex-wrap:wrap;gap:14px">
          <div id="trend-range-buttons" class="toolbar" style="gap:6px"></div>
          <select id="trend-tag-add" style="min-width:200px">
            <option value="">+ Add tag to chart...</option>
            ${knownTags.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}
          </select>
          <label class="checkbox-row" style="margin-left:auto">
            <input type="checkbox" id="trend-auto-refresh" />
            <span style="font-size:12.5px;color:var(--text-dim)">Auto-refresh every 5s</span>
          </label>
          <button class="btn btn-sm" id="trend-reload">Reload</button>
        </div>
        <div id="trend-chips" style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px"></div>
      </div>
    </div>
    <div class="card">
      <div class="card-body">
        <div id="trend-chart-wrap"><div class="empty-state">Select one or more tags to plot.</div></div>
      </div>
    </div>
    ${status ? `<div class="hint" style="color:var(--text-dim)">Logging every ${(status.interval_ms / 1000).toFixed(0)}s &middot; keeping ${status.retention_days} days &middot; ${status.total_points.toLocaleString()} points stored</div>` : ""}
  `;

  document.getElementById("trend-range-buttons").innerHTML = TREND_RANGES.map((r) =>
    `<button class="btn btn-sm${r.ms === trendRangeMs ? " btn-primary" : ""}" data-range="${r.ms}">${r.label}</button>`).join("");
  document.querySelectorAll("#trend-range-buttons [data-range]").forEach((btn) => {
    btn.addEventListener("click", () => { trendRangeMs = Number(btn.dataset.range); viewTrend(); });
  });

  document.getElementById("trend-tag-add").addEventListener("change", (e) => {
    const tag = e.target.value;
    if (!tag) return;
    if (trendSelectedTags.includes(tag)) { e.target.value = ""; return; }
    if (trendSelectedTags.length >= TREND_MAX_SERIES) {
      toast(`You can plot up to ${TREND_MAX_SERIES} tags at once`, true);
      e.target.value = "";
      return;
    }
    trendSelectedTags.push(tag);
    e.target.value = "";
    renderTrendChips();
    loadTrendData();
  });

  document.getElementById("trend-reload").onclick = loadTrendData;
  document.getElementById("trend-auto-refresh").addEventListener("change", (e) => {
    stopTrendAutoRefresh();
    if (e.target.checked) trendAutoRefreshTimer = setInterval(loadTrendData, 5000);
  });

  renderTrendChips();
  if (trendSelectedTags.length) await loadTrendData();

  window.addEventListener("resize", trendResizeHandler);
}

function trendResizeHandler() {
  if (trendLastData) renderTrendChart(trendLastData);
}

function renderTrendChips() {
  const el = document.getElementById("trend-chips");
  if (!el) return;
  el.innerHTML = trendSelectedTags.map((tag) => `
    <span style="display:inline-flex;align-items:center;gap:6px;background:#f2f4fa;border:1px solid var(--border);border-radius:20px;padding:4px 10px;font-size:12.5px">
      <span style="width:10px;height:10px;border-radius:2px;background:${trendColor(tag)};display:inline-block"></span>
      ${esc(tag)}
      <span data-remove-tag="${esc(tag)}" style="cursor:pointer;color:var(--text-dim);font-weight:700;padding-left:2px">&times;</span>
    </span>`).join("");
  el.querySelectorAll("[data-remove-tag]").forEach((x) => {
    x.addEventListener("click", () => {
      trendSelectedTags = trendSelectedTags.filter((t) => t !== x.dataset.removeTag);
      renderTrendChips();
      if (trendSelectedTags.length) loadTrendData();
      else document.getElementById("trend-chart-wrap").innerHTML = `<div class="empty-state">Select one or more tags to plot.</div>`;
    });
  });
}

async function loadTrendData() {
  if (!trendSelectedTags.length) return;
  const end = new Date();
  const start = new Date(end.getTime() - trendRangeMs);
  const params = new URLSearchParams({
    tags: trendSelectedTags.join(","), start: start.toISOString(), end: end.toISOString(), max_points: "2000",
  });
  let data;
  try { data = await Api.get(`/api/history?${params}`); }
  catch (e) { toast(e.message, true); return; }
  trendLastData = { data, start, end };
  renderTrendChart(trendLastData);
}

// --- SVG chart -------------------------------------------------------------

function niceTicks(min, max, count) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const niceMin = Math.floor(min / step) * step;
  const niceMax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = niceMin; v <= niceMax + step / 2; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return ticks;
}

function fmtAxisTime(date, rangeMs) {
  if (rangeMs <= 6 * 60 * 60 * 1000) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  if (rangeMs <= 48 * 60 * 60 * 1000) return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return date.toLocaleDateString([], { month: "short", day: "numeric" }) + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderTrendChart({ data, start, end }) {
  const wrap = document.getElementById("trend-chart-wrap");
  if (!wrap) return;
  const tags = trendSelectedTags.filter((t) => (data[t] || []).length > 0);
  if (tags.length === 0) {
    wrap.innerHTML = `<div class="empty-state">No historical data yet for the selected tag(s) in this time range. Data is logged every few seconds once a connector is running.</div>`;
    return;
  }

  const width = Math.max(wrap.clientWidth || 800, 300);
  const height = 360;
  const margin = { top: 16, right: 20, bottom: 34, left: 56 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;

  let vMin = Infinity, vMax = -Infinity;
  for (const t of tags) for (const p of data[t]) { vMin = Math.min(vMin, p.v); vMax = Math.max(vMax, p.v); }
  const yTicks = niceTicks(vMin, vMax, 5);
  const yLo = yTicks[0], yHi = yTicks[yTicks.length - 1];
  const xLo = start.getTime(), xHi = end.getTime();

  const xScale = (t) => margin.left + ((t - xLo) / (xHi - xLo || 1)) * plotW;
  const yScale = (v) => margin.top + plotH - ((v - yLo) / (yHi - yLo || 1)) * plotH;

  const gridLines = yTicks.map((v) => {
    const y = yScale(v);
    return `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e1e0d9" stroke-width="1" />
            <text x="${margin.left - 8}" y="${y}" text-anchor="end" dominant-baseline="middle" font-size="11" fill="#898781">${fmtYTick(v)}</text>`;
  }).join("");

  const xTickCount = 6;
  const xTicks = [];
  for (let i = 0; i <= xTickCount; i++) xTicks.push(xLo + (i / xTickCount) * (xHi - xLo));
  const xAxis = xTicks.map((t) => {
    const x = xScale(t);
    return `<text x="${x}" y="${height - margin.bottom + 18}" text-anchor="middle" font-size="11" fill="#898781">${esc(fmtAxisTime(new Date(t), trendRangeMs))}</text>`;
  }).join("");

  const paths = tags.map((tag) => {
    const pts = data[tag];
    const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${xScale(new Date(p.t).getTime()).toFixed(1)},${yScale(p.v).toFixed(1)}`).join(" ");
    return `<path d="${d}" fill="none" stroke="${trendColor(tag)}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />`;
  }).join("");

  const legend = tags.length > 1 ? `
    <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:10px">
      ${tags.map((t) => `<span style="display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--text-dim)">
        <span style="width:14px;height:2px;background:${trendColor(t)};display:inline-block"></span>${esc(t)}</span>`).join("")}
    </div>` : "";

  wrap.innerHTML = `
    ${legend}
    <div style="position:relative">
      <svg id="trend-svg" width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="display:block;overflow:visible">
        <rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}" fill="none" />
        ${gridLines}
        <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${width - margin.right}" y2="${margin.top + plotH}" stroke="#c3c2b7" stroke-width="1" />
        ${xAxis}
        ${paths}
        <g id="trend-crosshair" style="display:none">
          <line id="trend-crosshair-line" y1="${margin.top}" y2="${margin.top + plotH}" stroke="#898781" stroke-width="1" stroke-dasharray="3,3" />
        </g>
      </svg>
      <div id="trend-tooltip" style="position:absolute;display:none;background:var(--navy);color:#fff;padding:8px 10px;border-radius:8px;font-size:12px;pointer-events:none;box-shadow:0 8px 20px rgba(0,0,0,.25);z-index:5;white-space:nowrap"></div>
    </div>`;

  wireTrendCrosshair({ width, height, margin, plotW, xLo, xHi, tags, data, xScale });
}

function fmtYTick(v) {
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return String(Math.round(v * 1000) / 1000);
}

function wireTrendCrosshair({ width, height, margin, plotW, xLo, xHi, tags, data, xScale }) {
  const svg = document.getElementById("trend-svg");
  const crosshair = document.getElementById("trend-crosshair");
  const crosshairLine = document.getElementById("trend-crosshair-line");
  const tooltip = document.getElementById("trend-tooltip");
  if (!svg) return;

  const allTimes = [];
  for (const t of tags) for (const p of data[t]) allTimes.push(new Date(p.t).getTime());
  allTimes.sort((a, b) => a - b);

  function nearestTime(targetT) {
    let lo = 0, hi = allTimes.length - 1;
    if (hi < 0) return null;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (allTimes[mid] < targetT) lo = mid + 1; else hi = mid;
    }
    if (lo > 0 && Math.abs(allTimes[lo - 1] - targetT) < Math.abs(allTimes[lo] - targetT)) return allTimes[lo - 1];
    return allTimes[lo];
  }
  function nearestPointForTag(tag, targetT) {
    const pts = data[tag];
    let best = null, bestDiff = Infinity;
    for (const p of pts) {
      const diff = Math.abs(new Date(p.t).getTime() - targetT);
      if (diff < bestDiff) { bestDiff = diff; best = p; }
    }
    return best;
  }

  function onMove(evt) {
    const rect = svg.getBoundingClientRect();
    const scaleX = width / rect.width;
    const px = (evt.clientX - rect.left) * scaleX;
    if (px < margin.left || px > width - margin.right) { hide(); return; }
    const targetT = xLo + ((px - margin.left) / plotW) * (xHi - xLo);
    const nearestT = nearestTime(targetT);
    if (nearestT === null) { hide(); return; }
    const x = xScale(nearestT);
    crosshair.style.display = "";
    crosshairLine.setAttribute("x1", x);
    crosshairLine.setAttribute("x2", x);

    const rows = tags.map((tag) => {
      const p = nearestPointForTag(tag, nearestT);
      return p ? { tag, v: p.v } : null;
    }).filter(Boolean);

    tooltip.innerHTML = `
      <div style="color:#aab4d4;margin-bottom:4px">${esc(new Date(nearestT).toLocaleString())}</div>
      ${rows.map((r) => `<div style="display:flex;align-items:center;gap:6px">
        <span style="width:10px;height:2px;background:${trendColor(r.tag)};display:inline-block"></span>
        <span style="color:#c7cde8">${esc(r.tag)}</span>
        <b style="margin-left:auto;padding-left:10px">${esc(fmtValue(r.v))}</b>
      </div>`).join("")}`;
    tooltip.style.display = "";
    const rectWrap = svg.parentElement.getBoundingClientRect();
    let left = (evt.clientX - rectWrap.left) + 14;
    if (left + 190 > rectWrap.width) left = (evt.clientX - rectWrap.left) - 200;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(0, (evt.clientY - rectWrap.top) - 40)}px`;
  }
  function hide() { crosshair.style.display = "none"; tooltip.style.display = "none"; }

  svg.addEventListener("pointermove", onMove);
  svg.addEventListener("pointerleave", hide);
}
