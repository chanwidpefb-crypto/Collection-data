/* Collection Data - frontend (vanilla JS, no build step) */

const DATA_TYPES = ["bool", "int16", "uint16", "int32", "uint32", "float32", "int64", "uint64", "float64"];
const WORD_ORDERS = ["ABCD", "BADC", "CDAB", "DCBA"];
const MODBUS_AREAS = [
  { value: "holding_register", label: "Holding Register (4xxxx)" },
  { value: "input_register", label: "Input Register (3xxxx)" },
  { value: "coil", label: "Coil (0xxxx)" },
  { value: "discrete_input", label: "Discrete Input (1xxxx)" },
];
const CONNECTOR_TYPES = [
  { value: "modbus_tcp_client", title: "Modbus TCP Client", icon: "⬇",
    desc: "Poll registers from a remote PLC / device acting as a Modbus TCP server." },
  { value: "modbus_tcp_server", title: "Modbus TCP Server", icon: "⬆",
    desc: "Open a Modbus TCP port and expose collected tags to external masters." },
  { value: "opcua_client", title: "OPC UA Client", icon: "⬇",
    desc: "Poll nodes from a remote OPC UA server." },
  { value: "opcua_server", title: "OPC UA Server", icon: "⬆",
    desc: "Run an OPC UA server exposing collected tags as nodes." },
];

function connType(value) { return CONNECTOR_TYPES.find((t) => t.value === value); }
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtValue(v) {
  if (v === null || v === undefined) return "--";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  return String(v);
}
function fmtTime(ts) {
  if (!ts) return "--";
  const d = new Date(ts + "Z");
  return d.toLocaleTimeString();
}

// --- toast ---------------------------------------------------------------
function toast(message, isError) {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), isError ? 5000 : 2800);
}

// --- modal -----------------------------------------------------------------
function showModal(title, bodyHtml) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="modal-backdrop">
      <div class="modal">
        <div class="modal-header"><h2>${esc(title)}</h2><button class="modal-close" id="modal-close">&times;</button></div>
        <div class="modal-body">${bodyHtml}</div>
      </div>
    </div>`;
  document.getElementById("modal-close").onclick = closeModal;
  document.getElementById("modal-backdrop").addEventListener("click", (e) => {
    if (e.target.id === "modal-backdrop") closeModal();
  });
}
function closeModal() { document.getElementById("modal-root").innerHTML = ""; }

// --- router ------------------------------------------------------------
let liveRefreshTimer = null;
function stopLiveRefresh() { if (liveRefreshTimer) { clearInterval(liveRefreshTimer); liveRefreshTimer = null; } }

function homeRoute() {
  return currentUser && currentUser.role !== "admin" ? "#/live" : "#/connectors";
}

async function route() {
  if (!currentUser) return; // not logged in yet -- auth.js drives the login screen
  stopLiveRefresh();
  if (typeof stopTrendAutoRefresh === "function") stopTrendAutoRefresh();
  if (!location.hash) { location.hash = homeRoute(); return; }

  const parts = location.hash.replace(/^#\//, "").split("/");
  const adminOnlyRoutes = ["connectors", "users", "settings"];
  if (adminOnlyRoutes.includes(parts[0]) && (!currentUser || currentUser.role !== "admin")) {
    location.hash = homeRoute();
    return;
  }

  document.querySelectorAll("#nav a").forEach((a) => a.classList.remove("active"));
  const activate = (name) => { const a = document.querySelector(`#nav a[data-route=${name}]`); if (a) a.classList.add("active"); };

  if (parts[0] === "connectors" && parts[1]) {
    activate("connectors");
    await viewConnectorDetail(Number(parts[1]));
  } else if (parts[0] === "connectors") {
    activate("connectors");
    await viewConnectorsList();
  } else if (parts[0] === "live") {
    activate("live");
    await viewLiveMonitor();
  } else if (parts[0] === "trend") {
    activate("trend");
    await viewTrend();
  } else if (parts[0] === "users") {
    activate("users");
    await viewUsers();
  } else if (parts[0] === "settings") {
    activate("settings");
    await viewSettings();
  } else {
    location.hash = homeRoute();
  }
}
window.addEventListener("hashchange", route);

function setHeader(title, sub, actionsHtml) {
  document.getElementById("page-title").textContent = title;
  document.getElementById("page-sub").textContent = sub || "";
  document.getElementById("topbar-actions").innerHTML = actionsHtml || "";
}

// --- Connectors list ------------------------------------------------------
async function viewConnectorsList() {
  setHeader("Connectors", "Modbus TCP and OPC UA data source / sink drivers",
    `<button class="btn btn-primary" id="btn-add-connector">+ Add Connector</button>`);
  document.getElementById("btn-add-connector").onclick = openAddConnectorModal;

  const content = document.getElementById("content");
  content.innerHTML = `<div class="card"><div class="card-body" id="connectors-table"><div class="empty-state">Loading...</div></div></div>`;

  let connectors;
  try {
    connectors = await Api.get("/api/connectors");
  } catch (e) {
    document.getElementById("connectors-table").innerHTML = `<div class="empty-state">Failed to load: ${esc(e.message)}</div>`;
    return;
  }

  const wrap = document.getElementById("connectors-table");
  if (connectors.length === 0) {
    wrap.innerHTML = `<div class="empty-state">No connectors yet. Click "+ Add Connector" to create a Modbus TCP or OPC UA driver.</div>`;
    return;
  }

  wrap.innerHTML = `
    <table>
      <thead><tr><th>Name</th><th>Type</th><th>Status</th><th>Enabled</th><th></th></tr></thead>
      <tbody>
        ${connectors.map((c) => {
          const t = connType(c.type);
          const statusPill = c.running
            ? `<span class="pill pill-good">Running</span>`
            : (c.enabled ? `<span class="pill pill-warn">Stopped</span>` : `<span class="pill pill-neutral">Disabled</span>`);
          return `
          <tr>
            <td><a href="#/connectors/${c.id}" style="color:var(--accent);font-weight:700;text-decoration:none">${esc(c.name)}</a>
                ${c.last_error ? `<div style="color:var(--bad);font-size:11px;margin-top:2px">${esc(c.last_error)}</div>` : ""}</td>
            <td><span class="type-tag">${t ? t.icon : ""} ${t ? t.title : c.type}</span></td>
            <td>${statusPill}</td>
            <td>
              <label class="checkbox-row"><input type="checkbox" data-toggle-enabled="${c.id}" ${c.enabled ? "checked" : ""} /></label>
            </td>
            <td class="actions-cell">
              <button class="btn btn-sm" data-action="restart" data-id="${c.id}">Restart</button>
              <button class="btn btn-sm btn-danger" data-action="delete" data-id="${c.id}">Delete</button>
            </td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>`;

  wrap.querySelectorAll("[data-toggle-enabled]").forEach((cb) => {
    cb.addEventListener("change", async () => {
      const id = cb.getAttribute("data-toggle-enabled");
      try {
        await Api.patch(`/api/connectors/${id}`, { enabled: cb.checked });
        toast(cb.checked ? "Connector enabled" : "Connector disabled");
        viewConnectorsList();
      } catch (e) { toast(e.message, true); cb.checked = !cb.checked; }
    });
  });
  wrap.querySelectorAll('[data-action="restart"]').forEach((btn) => {
    btn.addEventListener("click", async () => {
      try { await Api.post(`/api/connectors/${btn.dataset.id}/restart`); toast("Connector restarted"); viewConnectorsList(); }
      catch (e) { toast(e.message, true); }
    });
  });
  wrap.querySelectorAll('[data-action="delete"]').forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this connector and all its registers/nodes?")) return;
      try { await Api.del(`/api/connectors/${btn.dataset.id}`); toast("Connector deleted"); viewConnectorsList(); }
      catch (e) { toast(e.message, true); }
    });
  });
}

function openAddConnectorModal() {
  showModal("Add Connector", `
    <div class="form-field full">
      <label>Connector Type</label>
      <div class="type-picker" id="type-picker">
        ${CONNECTOR_TYPES.map((t) => `
          <div class="type-card" data-type="${t.value}">
            <div class="t-title">${t.icon} ${t.title}</div>
            <div class="t-desc">${t.desc}</div>
          </div>`).join("")}
      </div>
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>Name</label>
      <input type="text" id="new-connector-name" placeholder="e.g. PLC1, Line2-Server, SCADA-OPC" />
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel-add">Cancel</button>
      <button class="btn btn-primary" id="confirm-add">Create</button>
    </div>
  `);
  let selectedType = null;
  document.querySelectorAll("#type-picker .type-card").forEach((card) => {
    card.addEventListener("click", () => {
      document.querySelectorAll("#type-picker .type-card").forEach((c) => c.classList.remove("selected"));
      card.classList.add("selected");
      selectedType = card.dataset.type;
    });
  });
  document.getElementById("cancel-add").onclick = closeModal;
  document.getElementById("confirm-add").onclick = async () => {
    const name = document.getElementById("new-connector-name").value.trim();
    if (!selectedType) { toast("Please choose a connector type", true); return; }
    if (!name) { toast("Please enter a name", true); return; }
    try {
      const created = await Api.post("/api/connectors", { name, type: selectedType, enabled: true });
      closeModal();
      toast("Connector created");
      location.hash = `#/connectors/${created.id}`;
    } catch (e) { toast(e.message, true); }
  };
}

// --- Connector detail -------------------------------------------------
async function viewConnectorDetail(id) {
  const content = document.getElementById("content");
  content.innerHTML = `<div class="empty-state">Loading...</div>`;
  let c;
  try { c = await Api.get(`/api/connectors/${id}`); }
  catch (e) { content.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; return; }

  const t = connType(c.type);
  setHeader(c.name, `${t.title} · #${c.id}`,
    `<button class="btn" id="btn-back">&larr; All Connectors</button>`);
  document.getElementById("btn-back").onclick = () => { location.hash = "#/connectors"; };

  let status;
  try { status = (await Api.get("/api/connectors")).find((x) => x.id === id); } catch (e) { status = null; }
  const running = status ? status.running : false;

  content.innerHTML = `
    <div class="breadcrumb"><a href="#/connectors">Connectors</a> / ${esc(c.name)}</div>
    <div class="card">
      <div class="card-header">
        <h2>Status</h2>
        <div class="actions-cell">
          <button class="btn btn-sm" id="btn-start" ${running ? "disabled" : ""}>Start</button>
          <button class="btn btn-sm" id="btn-stop" ${running ? "" : "disabled"}>Stop</button>
          <button class="btn btn-sm" id="btn-restart">Restart</button>
        </div>
      </div>
      <div class="card-body">
        ${running ? `<span class="pill pill-good">Running</span>` : `<span class="pill pill-neutral">Stopped</span>`}
        ${status && status.last_error ? `<div style="color:var(--bad);font-size:12.5px;margin-top:8px">${esc(status.last_error)}</div>` : ""}
      </div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Connection Settings</h2></div>
      <div class="card-body" id="config-form"></div>
    </div>
    <div class="card">
      <div class="card-header">
        <h2 id="registers-title"></h2>
        <div class="toolbar" style="gap:8px" id="registers-toolbar">
          <span id="grid-tag-insert-wrap"></span>
          <button class="btn btn-sm" id="btn-export-csv">Export CSV</button>
          <button class="btn btn-sm" id="btn-import-csv">Import CSV</button>
          <input type="file" id="csv-file-input" accept=".csv" style="display:none" />
          <button class="btn btn-sm" id="btn-add-row">+ Add Row</button>
          <button class="btn btn-primary btn-sm" id="btn-save-grid">Save Changes</button>
        </div>
      </div>
      <div class="card-body" id="registers-table"></div>
    </div>
  `;
  document.getElementById("btn-start").onclick = async () => { await Api.post(`/api/connectors/${id}/start`); viewConnectorDetail(id); };
  document.getElementById("btn-stop").onclick = async () => { await Api.post(`/api/connectors/${id}/stop`); viewConnectorDetail(id); };
  document.getElementById("btn-restart").onclick = async () => { await Api.post(`/api/connectors/${id}/restart`); toast("Restarted"); viewConnectorDetail(id); };

  renderConfigForm(c);
  renderRegistersSection(c, running);
}

function renderConfigForm(c) {
  const el = document.getElementById("config-form");
  if (c.type === "modbus_tcp_client") {
    const cfg = c.modbus_client_config || {};
    el.innerHTML = `
      <div class="form-grid">
        ${ff("Host / IP Address", `<input type="text" name="host" value="${esc(cfg.host || "")}" placeholder="192.168.1.10" />`)}
        ${ff("Port", `<input type="number" name="port" value="${cfg.port ?? 502}" min="1" max="65535" />`)}
        ${ff("Unit ID (Slave ID)", `<input type="number" name="unit_id" value="${cfg.unit_id ?? 1}" min="0" max="255" />`)}
        ${ff("Timeout (ms)", `<input type="number" name="timeout_ms" value="${cfg.timeout_ms ?? 3000}" min="100" />`)}
        ${ff("Poll Interval (ms)", `<input type="number" name="poll_interval_ms" value="${cfg.poll_interval_ms ?? 1000}" min="50" />`)}
      </div>
      <div class="form-actions"><button class="btn btn-primary" id="save-config">Save</button></div>`;
    document.getElementById("save-config").onclick = () => saveConfig(c.id, "modbus-client-config", ["host", "port", "unit_id", "timeout_ms", "poll_interval_ms"], { port: "int", unit_id: "int", timeout_ms: "int", poll_interval_ms: "int" });
  } else if (c.type === "modbus_tcp_server") {
    const cfg = c.modbus_server_config || {};
    el.innerHTML = `
      <div class="form-grid">
        ${ff("Listen Address", `<input type="text" name="host" value="${esc(cfg.host || "0.0.0.0")}" />`, "0.0.0.0 = all network interfaces")}
        ${ff("Port", `<input type="number" name="port" value="${cfg.port ?? 502}" min="1" max="65535" />`)}
        ${ff("Unit ID (Slave ID)", `<input type="number" name="unit_id" value="${cfg.unit_id ?? 1}" min="0" max="255" />`)}
      </div>
      <div class="form-actions"><button class="btn btn-primary" id="save-config">Save</button></div>`;
    document.getElementById("save-config").onclick = () => saveConfig(c.id, "modbus-server-config", ["host", "port", "unit_id"], { port: "int", unit_id: "int" });
  } else if (c.type === "opcua_client") {
    const cfg = c.opcua_client_config || {};
    el.innerHTML = `
      <div class="form-grid">
        ${ff("Endpoint URL", `<input type="text" name="endpoint_url" value="${esc(cfg.endpoint_url || "")}" placeholder="opc.tcp://192.168.1.10:4840" />`, "", true)}
        ${ff("Username (optional)", `<input type="text" name="username" value="${esc(cfg.username || "")}" />`)}
        ${ff("Password (optional)", `<input type="password" name="password" value="${esc(cfg.password || "")}" />`)}
        ${ff("Poll Interval (ms)", `<input type="number" name="poll_interval_ms" value="${cfg.poll_interval_ms ?? 1000}" min="50" />`)}
      </div>
      <div class="form-actions"><button class="btn btn-primary" id="save-config">Save</button></div>`;
    document.getElementById("save-config").onclick = () => saveConfig(c.id, "opcua-client-config", ["endpoint_url", "username", "password", "poll_interval_ms"], { poll_interval_ms: "int" });
  } else if (c.type === "opcua_server") {
    const cfg = c.opcua_server_config || {};
    el.innerHTML = `
      <div class="form-grid">
        ${ff("Endpoint URL", `<input type="text" name="endpoint_url" value="${esc(cfg.endpoint_url || "")}" placeholder="opc.tcp://0.0.0.0:4840/collection-data/" />`, "", true)}
        ${ff("Server Name", `<input type="text" name="server_name" value="${esc(cfg.server_name || "")}" />`)}
        ${ff("Namespace URI", `<input type="text" name="namespace_uri" value="${esc(cfg.namespace_uri || "")}" />`)}
        ${ff("Publish Interval (ms)", `<input type="number" name="publish_interval_ms" value="${cfg.publish_interval_ms ?? 1000}" min="50" />`)}
      </div>
      <div class="form-actions"><button class="btn btn-primary" id="save-config">Save</button></div>`;
    document.getElementById("save-config").onclick = () => saveConfig(c.id, "opcua-server-config", ["endpoint_url", "server_name", "namespace_uri", "publish_interval_ms"], { publish_interval_ms: "int" });
  }
}

function ff(label, inputHtml, hint, full) {
  return `<div class="form-field${full ? " full" : ""}"><label>${esc(label)}${hint ? ` <span class="hint">- ${esc(hint)}</span>` : ""}</label>${inputHtml}</div>`;
}

async function saveConfig(connectorId, endpoint, fields, types) {
  const body = {};
  for (const f of fields) {
    const input = document.querySelector(`[name="${f}"]`);
    let v = input.value;
    if (types && types[f] === "int") v = v === "" ? null : parseInt(v, 10);
    if (v === "") v = null;
    body[f] = v;
  }
  try {
    await Api.put(`/api/connectors/${connectorId}/${endpoint}`, body);
    toast("Settings saved");
    viewConnectorDetail(connectorId);
  } catch (e) { toast(e.message, true); }
}

// --- Registers / nodes sections (spreadsheet-style grid, see grid.js) --
let currentGrid = null;

function registerGridConfig(c) {
  const base = `/api/connectors/${c.id}`;
  if (c.type === "modbus_tcp_client") {
    return {
      title: "Registers", apiBase: `${base}/modbus-client-registers`, rows: c.modbus_client_registers,
      idKey: "id", hasExpression: false,
      columns: [
        { key: "tag_name", label: "Tag Name", type: "text", placeholder: "tank1_level" },
        { key: "area", label: "Area", type: "select", options: MODBUS_AREAS },
        { key: "address", label: "Address", type: "number" },
        { key: "data_type", label: "Type", type: "select", options: DATA_TYPES.map((d) => ({ value: d, label: d })) },
        { key: "word_order", label: "Order", type: "select", options: WORD_ORDERS.map((d) => ({ value: d, label: d })) },
        { key: "factor", label: "Factor", type: "number", step: "any" },
        { key: "offset", label: "Offset", type: "number", step: "any" },
        { key: "enabled", label: "On", type: "checkbox" },
        { key: "description", label: "Description", type: "text" },
      ],
      defaultRow: { tag_name: "", area: "holding_register", address: 0, data_type: "uint16", word_order: "ABCD", factor: 1, offset: 0, enabled: true, description: "" },
    };
  }
  if (c.type === "modbus_tcp_server") {
    return {
      title: "Registers (exposed to Modbus masters)", apiBase: `${base}/modbus-server-registers`, rows: c.modbus_server_registers,
      idKey: "id", hasExpression: true,
      columns: [
        { key: "name", label: "Name", type: "text", placeholder: "tank1_out" },
        { key: "area", label: "Area", type: "select", options: MODBUS_AREAS },
        { key: "address", label: "Address", type: "number" },
        { key: "data_type", label: "Type", type: "select", options: DATA_TYPES.map((d) => ({ value: d, label: d })) },
        { key: "word_order", label: "Order", type: "select", options: WORD_ORDERS.map((d) => ({ value: d, label: d })) },
        { key: "expression", label: "Value / Factor Expression", type: "expression", placeholder: "tank1_level * 1.0" },
        { key: "enabled", label: "On", type: "checkbox" },
      ],
      defaultRow: { name: "", area: "holding_register", address: 0, data_type: "uint16", word_order: "ABCD", expression: "", enabled: true },
    };
  }
  if (c.type === "opcua_client") {
    return {
      title: "Nodes", apiBase: `${base}/opcua-client-nodes`, rows: c.opcua_client_nodes,
      idKey: "id", hasExpression: false,
      columns: [
        { key: "tag_name", label: "Tag Name", type: "text", placeholder: "tank1_level" },
        { key: "node_id", label: "Node ID", type: "text", placeholder: "ns=2;s=Channel1.Device1.Tag1" },
        { key: "factor", label: "Factor", type: "number", step: "any" },
        { key: "offset", label: "Offset", type: "number", step: "any" },
        { key: "enabled", label: "On", type: "checkbox" },
        { key: "description", label: "Description", type: "text" },
      ],
      defaultRow: { tag_name: "", node_id: "", factor: 1, offset: 0, enabled: true, description: "" },
    };
  }
  // opcua_server
  return {
    title: "Nodes (exposed to OPC UA clients)", apiBase: `${base}/opcua-server-nodes`, rows: c.opcua_server_nodes,
    idKey: "id", hasExpression: true,
    columns: [
      { key: "node_name", label: "Node Name", type: "text", placeholder: "Tank1Level" },
      { key: "expression", label: "Value / Factor Expression", type: "expression", placeholder: "tank1_level * 1.0" },
      { key: "enabled", label: "On", type: "checkbox" },
    ],
    defaultRow: { node_name: "", expression: "", enabled: true },
  };
}

async function renderRegistersSection(c, isRunning) {
  const config = registerGridConfig(c);
  document.getElementById("registers-title").textContent = config.title;

  const tagInsertWrap = document.getElementById("grid-tag-insert-wrap");
  if (config.hasExpression) {
    let knownTags = [];
    try { knownTags = await Api.get("/api/tags/known"); } catch (e) { /* ignore */ }
    tagInsertWrap.innerHTML = `<select id="grid-tag-insert" style="max-width:180px">
      <option value="">Insert tag...</option>
      ${knownTags.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("")}
    </select>`;
    document.getElementById("grid-tag-insert").addEventListener("change", (e) => {
      const target = lastFocusedExpressionInput;
      if (e.target.value && target) {
        target.value += (target.value && !target.value.endsWith(" ") ? " " : "") + e.target.value;
        target.dispatchEvent(new Event("input"));
        target.focus();
      }
      e.target.value = "";
    });
  } else {
    tagInsertWrap.innerHTML = "";
  }

  currentGrid = createRegisterGrid({
    container: document.getElementById("registers-table"),
    columns: config.columns, rows: config.rows, apiBase: config.apiBase,
    connectorId: c.id, isRunning, defaultRow: config.defaultRow,
  });

  document.getElementById("btn-add-row").onclick = () => currentGrid.addBlankRow();
  document.getElementById("btn-save-grid").onclick = () => currentGrid.saveAll();
  document.getElementById("btn-export-csv").onclick = () => {
    window.open(`${config.apiBase}/export`, "_blank");
  };
  document.getElementById("btn-import-csv").onclick = () => document.getElementById("csv-file-input").click();
  document.getElementById("csv-file-input").onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await fetch(`${config.apiBase}/import`, { method: "POST", body: formData });
      const body = await result.json();
      if (!result.ok) throw new Error(body.detail || "import failed");
      const parts = [`${body.created} added`, `${body.updated} updated`];
      if (body.errors.length) parts.push(`${body.errors.length} error(s)`);
      toast(`Import: ${parts.join(", ")}`, body.errors.length > 0);
      if (body.errors.length) showModal("Import Errors", `<ul>${body.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
        <div class="form-actions"><button class="btn btn-primary" id="close-import-errors">Close</button></div>`);
      if (document.getElementById("close-import-errors")) document.getElementById("close-import-errors").onclick = closeModal;
      viewConnectorDetail(c.id);
    } catch (err) { toast(err.message, true); }
  };
}

function qv(name) { return document.querySelector(`[name="${name}"]`).value.trim(); }

// --- Live Monitor -------------------------------------------------------
async function viewLiveMonitor() {
  setHeader("Live Monitor", "Real-time value of every collected tag",
    `<div class="toolbar"><input type="text" id="live-search" placeholder="Search tag..." /></div>`);
  const content = document.getElementById("content");
  content.innerHTML = `<div class="card"><div class="card-body" id="live-table"><div class="empty-state">Loading...</div></div></div>`;

  async function refresh() {
    let values;
    try { values = await Api.get("/api/values"); } catch (e) { return; }
    const filter = (document.getElementById("live-search")?.value || "").toLowerCase();
    const filtered = values.filter((v) => v.tag_name.toLowerCase().includes(filter));
    const el = document.getElementById("live-table");
    if (!el) return;
    if (filtered.length === 0) {
      el.innerHTML = `<div class="empty-state">No tags yet. Add registers/nodes to a Modbus or OPC UA Client connector.</div>`;
      return;
    }
    el.innerHTML = `<table>
      <thead><tr><th>Tag Name</th><th>Value</th><th>Quality</th><th>Source</th><th>Updated</th></tr></thead>
      <tbody>${filtered.map((v) => `
        <tr>
          <td class="mono"><b>${esc(v.tag_name)}</b></td>
          <td class="mono">${esc(fmtValue(v.value))}</td>
          <td>${v.quality === "good" ? `<span class="pill pill-good">Good</span>` : `<span class="pill pill-bad">Bad</span>`}</td>
          <td>${esc(v.source_connector || "--")}</td>
          <td class="mono">${fmtTime(v.timestamp)}</td>
        </tr>`).join("")}</tbody></table>`;
  }

  document.getElementById("live-search").addEventListener("input", refresh);
  await refresh();
  liveRefreshTimer = setInterval(refresh, 1500);
}
