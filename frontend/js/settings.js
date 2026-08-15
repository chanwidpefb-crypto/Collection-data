/* Settings page (admin only): choose where the historian stores its data. */

async function viewSettings() {
  setHeader("Settings", "Configure where historical tag data is stored", "");
  const content = document.getElementById("content");
  content.innerHTML = `<div class="card"><div class="card-body"><div class="empty-state">Loading...</div></div></div>`;

  let settings, status;
  try {
    settings = await Api.get("/api/settings/historian");
    status = await Api.get("/api/history/status");
  } catch (e) {
    content.innerHTML = `<div class="card"><div class="card-body"><div class="empty-state">${esc(e.message)}</div></div></div>`;
    return;
  }

  const fellBack = settings.active_backend !== settings.backend;
  const warningHtml = (fellBack || settings.last_error) ? `
    <div style="background:var(--bad-bg);color:var(--bad);border-radius:8px;padding:10px 14px;font-size:12.5px;margin-bottom:16px">
      ${fellBack ? `<b>Currently running on <code>${esc(settings.active_backend)}</code></b>, not the configured <code>${esc(settings.backend)}</code>. ` : ""}
      ${settings.last_error ? esc(settings.last_error) : ""}
    </div>` : "";

  content.innerHTML = `
    <div class="card">
      <div class="card-header"><h2>Historian Storage</h2></div>
      <div class="card-body">
        ${warningHtml}
        <div class="hint" style="color:var(--text-dim);margin-bottom:16px">
          Currently logging every ${(status.interval_ms / 1000).toFixed(1)}s &middot;
          keeping ${status.retention_days} days &middot; ${status.total_points.toLocaleString()} points stored
        </div>
        <div class="form-grid">
          ${ff("Backend", `
            <select name="backend" id="backend-select">
              <option value="sqlite" ${settings.backend === "sqlite" ? "selected" : ""}>SQLite (default -- local file, no setup)</option>
              <option value="timescaledb" ${settings.backend === "timescaledb" ? "selected" : ""}>TimescaleDB (PostgreSQL + Timescale extension)</option>
            </select>`)}
          ${ff("Log Interval (ms)", `<input type="number" name="interval_ms" value="${settings.interval_ms}" min="1000" step="500" />`, "how often every tag is snapshotted")}
          ${ff("Retention (days)", `<input type="number" name="retention_days" value="${settings.retention_days}" min="1" />`, "older samples are purged automatically")}
        </div>

        <div id="timescale-fields" style="display:${settings.backend === "timescaledb" ? "" : "none"};margin-top:18px">
          <div style="font-weight:700;font-size:12.5px;color:var(--text-dim);margin-bottom:10px">TimescaleDB Connection</div>
          <div class="form-grid">
            ${ff("Host", `<input type="text" name="ts_host" value="${esc(settings.ts_host)}" placeholder="timescale.example.com" />`)}
            ${ff("Port", `<input type="number" name="ts_port" value="${settings.ts_port}" min="1" max="65535" />`)}
            ${ff("Database", `<input type="text" name="ts_database" value="${esc(settings.ts_database)}" />`)}
            ${ff("Username", `<input type="text" name="ts_user" value="${esc(settings.ts_user)}" />`)}
            ${ff("Password", `<input type="password" name="ts_password" placeholder="${settings.ts_password_set ? "leave blank to keep current" : ""}" />`)}
            ${ff("Table Name", `<input type="text" name="ts_table" value="${esc(settings.ts_table)}" />`)}
            ${ff("SSL Mode", `
              <select name="ts_sslmode">
                ${["disable", "prefer", "require"].map((m) => `<option value="${m}" ${settings.ts_sslmode === m ? "selected" : ""}>${m}</option>`).join("")}
              </select>`)}
          </div>
          <div style="margin-top:14px;display:flex;align-items:center;gap:12px">
            <button class="btn btn-sm" id="btn-test-connection">Test Connection</button>
            <span id="test-connection-result" style="font-size:12.5px"></span>
          </div>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" id="btn-save-settings">Save</button>
        </div>
      </div>
    </div>`;

  document.getElementById("backend-select").addEventListener("change", (e) => {
    document.getElementById("timescale-fields").style.display = e.target.value === "timescaledb" ? "" : "none";
  });

  document.getElementById("btn-test-connection").onclick = async () => {
    const resultEl = document.getElementById("test-connection-result");
    resultEl.textContent = "Testing...";
    resultEl.style.color = "var(--text-dim)";
    try {
      const result = await Api.post("/api/settings/historian/test-connection", {
        ts_host: qv("ts_host"), ts_port: parseInt(qv("ts_port"), 10), ts_database: qv("ts_database"),
        ts_user: qv("ts_user"), ts_password: document.querySelector('[name="ts_password"]').value,
        ts_table: qv("ts_table"), ts_sslmode: qv("ts_sslmode"),
      });
      resultEl.textContent = result.ok ? "Connected successfully" : `Failed: ${result.message}`;
      resultEl.style.color = result.ok ? "var(--good)" : "var(--bad)";
    } catch (e) {
      resultEl.textContent = e.message;
      resultEl.style.color = "var(--bad)";
    }
  };

  document.getElementById("btn-save-settings").onclick = async () => {
    const backend = qv("backend");
    const body = {
      backend, interval_ms: parseInt(qv("interval_ms"), 10), retention_days: parseInt(qv("retention_days"), 10),
    };
    if (backend === "timescaledb") {
      Object.assign(body, {
        ts_host: qv("ts_host"), ts_port: parseInt(qv("ts_port"), 10), ts_database: qv("ts_database"),
        ts_user: qv("ts_user"), ts_table: qv("ts_table"), ts_sslmode: qv("ts_sslmode"),
      });
      const pw = document.querySelector('[name="ts_password"]').value;
      if (pw) body.ts_password = pw;
    }
    try {
      await Api.put("/api/settings/historian", body);
      toast("Historian settings saved");
      viewSettings();
    } catch (e) {
      toast(e.message, true);
    }
  };
}
