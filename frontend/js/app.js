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

async function route() {
  stopLiveRefresh();
  const hash = location.hash || "#/connectors";
  const parts = hash.replace(/^#\//, "").split("/");
  document.querySelectorAll("#nav a").forEach((a) => a.classList.remove("active"));

  if (parts[0] === "connectors" && parts[1]) {
    document.querySelector('#nav a[data-route=connectors]').classList.add("active");
    await viewConnectorDetail(Number(parts[1]));
  } else if (parts[0] === "live") {
    document.querySelector('#nav a[data-route=live]').classList.add("active");
    await viewLiveMonitor();
  } else {
    document.querySelector('#nav a[data-route=connectors]').classList.add("active");
    await viewConnectorsList();
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
        <button class="btn btn-primary btn-sm" id="btn-add-register">+ Add</button>
      </div>
      <div class="card-body" id="registers-table"></div>
    </div>
  `;
  document.getElementById("btn-start").onclick = async () => { await Api.post(`/api/connectors/${id}/start`); viewConnectorDetail(id); };
  document.getElementById("btn-stop").onclick = async () => { await Api.post(`/api/connectors/${id}/stop`); viewConnectorDetail(id); };
  document.getElementById("btn-restart").onclick = async () => { await Api.post(`/api/connectors/${id}/restart`); toast("Restarted"); viewConnectorDetail(id); };

  renderConfigForm(c);
  renderRegistersSection(c);
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

// --- Registers / nodes sections ---------------------------------------
function renderRegistersSection(c) {
  const titleEl = document.getElementById("registers-title");
  const addBtn = document.getElementById("btn-add-register");
  if (c.type === "modbus_tcp_client") {
    titleEl.textContent = "Registers";
    addBtn.onclick = () => openModbusClientRegisterModal(c);
    renderModbusClientRegisters(c);
  } else if (c.type === "modbus_tcp_server") {
    titleEl.textContent = "Registers (exposed to Modbus masters)";
    addBtn.onclick = () => openModbusServerRegisterModal(c);
    renderModbusServerRegisters(c);
  } else if (c.type === "opcua_client") {
    titleEl.textContent = "Nodes";
    addBtn.onclick = () => openOpcUaClientNodeModal(c);
    renderOpcUaClientNodes(c);
  } else if (c.type === "opcua_server") {
    titleEl.textContent = "Nodes (exposed to OPC UA clients)";
    addBtn.onclick = () => openOpcUaServerNodeModal(c);
    renderOpcUaServerNodes(c);
  }
}

function dataTypeOptions(selected) {
  return DATA_TYPES.map((d) => `<option value="${d}" ${d === selected ? "selected" : ""}>${d}</option>`).join("");
}
function wordOrderOptions(selected) {
  return WORD_ORDERS.map((d) => `<option value="${d}" ${d === selected ? "selected" : ""}>${d}</option>`).join("");
}
function areaOptions(selected) {
  return MODBUS_AREAS.map((a) => `<option value="${a.value}" ${a.value === selected ? "selected" : ""}>${a.label}</option>`).join("");
}

// ---- Modbus client registers ----
function renderModbusClientRegisters(c) {
  const el = document.getElementById("registers-table");
  const regs = c.modbus_client_registers;
  if (!regs.length) { el.innerHTML = `<div class="empty-state">No registers yet.</div>`; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Tag Name</th><th>Area</th><th>Address</th><th>Type</th><th>Order</th><th>Factor</th><th>Offset</th><th></th></tr></thead>
    <tbody>${regs.map((r) => `
      <tr>
        <td><b>${esc(r.tag_name)}</b>${r.description ? `<div class="hint" style="color:var(--text-dim);font-size:11px">${esc(r.description)}</div>` : ""}</td>
        <td class="mono">${esc(r.area)}</td>
        <td class="mono">${r.address}</td>
        <td class="mono">${esc(r.data_type)}</td>
        <td class="mono">${esc(r.word_order)}</td>
        <td>${r.factor}</td>
        <td>${r.offset}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-edit="${r.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-del="${r.id}">Del</button>
        </td>
      </tr>`).join("")}</tbody></table>`;
  el.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => openModbusClientRegisterModal(c, regs.find((r) => r.id == b.dataset.edit)));
  el.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this register?")) return;
    try { await Api.del(`/api/connectors/${c.id}/modbus-client-registers/${b.dataset.del}`); toast("Deleted"); viewConnectorDetail(c.id); }
    catch (e) { toast(e.message, true); }
  });
}

function openModbusClientRegisterModal(c, reg) {
  const isEdit = !!reg;
  showModal(isEdit ? "Edit Register" : "Add Register", `
    <div class="form-grid">
      ${ff("Variable Name (tag)", `<input type="text" name="tag_name" value="${esc(reg?.tag_name || "")}" placeholder="tank1_level" />`)}
      ${ff("Area", `<select name="area">${areaOptions(reg?.area || "holding_register")}</select>`)}
      ${ff("Address", `<input type="number" name="address" value="${reg?.address ?? 0}" min="0" max="65535" />`)}
      ${ff("Data Type", `<select name="data_type">${dataTypeOptions(reg?.data_type || "uint16")}</select>`)}
      ${ff("Word/Byte Order", `<select name="word_order">${wordOrderOptions(reg?.word_order || "ABCD")}</select>`, "only applies to multi-register types")}
      ${ff("Factor (multiplier)", `<input type="number" step="any" name="factor" value="${reg?.factor ?? 1}" />`)}
      ${ff("Offset", `<input type="number" step="any" name="offset" value="${reg?.offset ?? 0}" />`)}
      ${ff("Description (optional)", `<input type="text" name="description" value="${esc(reg?.description || "")}" />`, "", true)}
    </div>
    <div class="checkbox-row" style="margin-top:12px">
      <input type="checkbox" name="enabled" id="reg-enabled" ${reg?.enabled !== false ? "checked" : ""} />
      <label for="reg-enabled">Enabled</label>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">${isEdit ? "Save" : "Add"}</button>
    </div>`);
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    const body = {
      tag_name: qv("tag_name"), area: qv("area"), address: parseInt(qv("address"), 10),
      data_type: qv("data_type"), word_order: qv("word_order"),
      factor: parseFloat(qv("factor")), offset: parseFloat(qv("offset")),
      description: qv("description") || null, enabled: document.getElementById("reg-enabled").checked,
    };
    try {
      if (isEdit) await Api.put(`/api/connectors/${c.id}/modbus-client-registers/${reg.id}`, body);
      else await Api.post(`/api/connectors/${c.id}/modbus-client-registers`, body);
      closeModal(); toast("Saved"); viewConnectorDetail(c.id);
    } catch (e) { toast(e.message, true); }
  };
}

// ---- Modbus server registers ----
function renderModbusServerRegisters(c) {
  const el = document.getElementById("registers-table");
  const regs = c.modbus_server_registers;
  if (!regs.length) { el.innerHTML = `<div class="empty-state">No registers yet.</div>`; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Name</th><th>Area</th><th>Address</th><th>Type</th><th>Order</th><th>Expression</th><th></th></tr></thead>
    <tbody>${regs.map((r) => `
      <tr>
        <td><b>${esc(r.name)}</b></td>
        <td class="mono">${esc(r.area)}</td>
        <td class="mono">${r.address}</td>
        <td class="mono">${esc(r.data_type)}</td>
        <td class="mono">${esc(r.word_order)}</td>
        <td class="mono">${esc(r.expression)}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-edit="${r.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-del="${r.id}">Del</button>
        </td>
      </tr>`).join("")}</tbody></table>`;
  el.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => openModbusServerRegisterModal(c, regs.find((r) => r.id == b.dataset.edit)));
  el.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this register?")) return;
    try { await Api.del(`/api/connectors/${c.id}/modbus-server-registers/${b.dataset.del}`); toast("Deleted"); viewConnectorDetail(c.id); }
    catch (e) { toast(e.message, true); }
  });
}

async function openModbusServerRegisterModal(c, reg) {
  const isEdit = !!reg;
  let knownTags = [];
  try { knownTags = await Api.get("/api/tags/known"); } catch (e) { /* ignore */ }
  showModal(isEdit ? "Edit Register" : "Add Register", `
    <div class="form-grid">
      ${ff("Name", `<input type="text" name="name" value="${esc(reg?.name || "")}" placeholder="tank1_out" />`)}
      ${ff("Area", `<select name="area">${areaOptions(reg?.area || "holding_register")}</select>`)}
      ${ff("Address", `<input type="number" name="address" value="${reg?.address ?? 0}" min="0" max="65535" />`)}
      ${ff("Data Type", `<select name="data_type">${dataTypeOptions(reg?.data_type || "uint16")}</select>`)}
      ${ff("Word/Byte Order", `<select name="word_order">${wordOrderOptions(reg?.word_order || "ABCD")}</select>`)}
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>Value / Factor Expression</label>
      <textarea name="expression" placeholder="tank1_level * 1.0">${esc(reg?.expression || "")}</textarea>
      <div class="tag-picker">
        <select id="tag-insert">
          <option value="">Insert system tag...</option>
          ${knownTags.map((t) => `<option value="${t}">${esc(t)}</option>`).join("")}
        </select>
        <span class="hint">supports + - * / ( ) and min/max/abs/round/sqrt</span>
      </div>
    </div>
    <div class="checkbox-row" style="margin-top:12px">
      <input type="checkbox" name="enabled" id="reg-enabled" ${reg?.enabled !== false ? "checked" : ""} />
      <label for="reg-enabled">Enabled</label>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">${isEdit ? "Save" : "Add"}</button>
    </div>`);
  document.getElementById("tag-insert").addEventListener("change", (e) => {
    const ta = document.querySelector('[name="expression"]');
    if (e.target.value) { ta.value += (ta.value && !ta.value.endsWith(" ") ? " " : "") + e.target.value; e.target.value = ""; ta.focus(); }
  });
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    const body = {
      name: qv("name"), area: qv("area"), address: parseInt(qv("address"), 10),
      data_type: qv("data_type"), word_order: qv("word_order"), expression: qv("expression"),
      enabled: document.getElementById("reg-enabled").checked,
    };
    try {
      if (isEdit) await Api.put(`/api/connectors/${c.id}/modbus-server-registers/${reg.id}`, body);
      else await Api.post(`/api/connectors/${c.id}/modbus-server-registers`, body);
      closeModal(); toast("Saved"); viewConnectorDetail(c.id);
    } catch (e) { toast(e.message, true); }
  };
}

// ---- OPC UA client nodes ----
function renderOpcUaClientNodes(c) {
  const el = document.getElementById("registers-table");
  const nodes = c.opcua_client_nodes;
  if (!nodes.length) { el.innerHTML = `<div class="empty-state">No nodes yet.</div>`; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Tag Name</th><th>Node ID</th><th>Factor</th><th>Offset</th><th></th></tr></thead>
    <tbody>${nodes.map((n) => `
      <tr>
        <td><b>${esc(n.tag_name)}</b>${n.description ? `<div class="hint" style="color:var(--text-dim);font-size:11px">${esc(n.description)}</div>` : ""}</td>
        <td class="mono">${esc(n.node_id)}</td>
        <td>${n.factor}</td>
        <td>${n.offset}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-edit="${n.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-del="${n.id}">Del</button>
        </td>
      </tr>`).join("")}</tbody></table>`;
  el.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => openOpcUaClientNodeModal(c, nodes.find((n) => n.id == b.dataset.edit)));
  el.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this node?")) return;
    try { await Api.del(`/api/connectors/${c.id}/opcua-client-nodes/${b.dataset.del}`); toast("Deleted"); viewConnectorDetail(c.id); }
    catch (e) { toast(e.message, true); }
  });
}

function openOpcUaClientNodeModal(c, node) {
  const isEdit = !!node;
  showModal(isEdit ? "Edit Node" : "Add Node", `
    <div class="form-grid">
      ${ff("Variable Name (tag)", `<input type="text" name="tag_name" value="${esc(node?.tag_name || "")}" placeholder="tank1_level" />`)}
      ${ff("Node ID", `<input type="text" name="node_id" value="${esc(node?.node_id || "")}" placeholder="ns=2;s=Channel1.Device1.Tag1" />`, "", true)}
      ${ff("Factor (multiplier)", `<input type="number" step="any" name="factor" value="${node?.factor ?? 1}" />`)}
      ${ff("Offset", `<input type="number" step="any" name="offset" value="${node?.offset ?? 0}" />`)}
      ${ff("Description (optional)", `<input type="text" name="description" value="${esc(node?.description || "")}" />`, "", true)}
    </div>
    <div class="checkbox-row" style="margin-top:12px">
      <input type="checkbox" name="enabled" id="node-enabled" ${node?.enabled !== false ? "checked" : ""} />
      <label for="node-enabled">Enabled</label>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">${isEdit ? "Save" : "Add"}</button>
    </div>`);
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    const body = {
      tag_name: qv("tag_name"), node_id: qv("node_id"),
      factor: parseFloat(qv("factor")), offset: parseFloat(qv("offset")),
      description: qv("description") || null, enabled: document.getElementById("node-enabled").checked,
    };
    try {
      if (isEdit) await Api.put(`/api/connectors/${c.id}/opcua-client-nodes/${node.id}`, body);
      else await Api.post(`/api/connectors/${c.id}/opcua-client-nodes`, body);
      closeModal(); toast("Saved"); viewConnectorDetail(c.id);
    } catch (e) { toast(e.message, true); }
  };
}

// ---- OPC UA server nodes ----
function renderOpcUaServerNodes(c) {
  const el = document.getElementById("registers-table");
  const nodes = c.opcua_server_nodes;
  if (!nodes.length) { el.innerHTML = `<div class="empty-state">No nodes yet.</div>`; return; }
  el.innerHTML = `<table>
    <thead><tr><th>Node Name</th><th>Expression</th><th></th></tr></thead>
    <tbody>${nodes.map((n) => `
      <tr>
        <td><b>${esc(n.node_name)}</b></td>
        <td class="mono">${esc(n.expression)}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-edit="${n.id}">Edit</button>
          <button class="btn btn-sm btn-danger" data-del="${n.id}">Del</button>
        </td>
      </tr>`).join("")}</tbody></table>`;
  el.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => openOpcUaServerNodeModal(c, nodes.find((n) => n.id == b.dataset.edit)));
  el.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
    if (!confirm("Delete this node?")) return;
    try { await Api.del(`/api/connectors/${c.id}/opcua-server-nodes/${b.dataset.del}`); toast("Deleted"); viewConnectorDetail(c.id); }
    catch (e) { toast(e.message, true); }
  });
}

async function openOpcUaServerNodeModal(c, node) {
  const isEdit = !!node;
  let knownTags = [];
  try { knownTags = await Api.get("/api/tags/known"); } catch (e) { /* ignore */ }
  showModal(isEdit ? "Edit Node" : "Add Node", `
    <div class="form-field full">
      <label>Node Name</label>
      <input type="text" name="node_name" value="${esc(node?.node_name || "")}" placeholder="Tank1Level" />
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>Value / Factor Expression</label>
      <textarea name="expression" placeholder="tank1_level * 1.0">${esc(node?.expression || "")}</textarea>
      <div class="tag-picker">
        <select id="tag-insert">
          <option value="">Insert system tag...</option>
          ${knownTags.map((t) => `<option value="${t}">${esc(t)}</option>`).join("")}
        </select>
        <span class="hint">supports + - * / ( ) and min/max/abs/round/sqrt</span>
      </div>
    </div>
    <div class="checkbox-row" style="margin-top:12px">
      <input type="checkbox" name="enabled" id="node-enabled" ${node?.enabled !== false ? "checked" : ""} />
      <label for="node-enabled">Enabled</label>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">${isEdit ? "Save" : "Add"}</button>
    </div>`);
  document.getElementById("tag-insert").addEventListener("change", (e) => {
    const ta = document.querySelector('[name="expression"]');
    if (e.target.value) { ta.value += (ta.value && !ta.value.endsWith(" ") ? " " : "") + e.target.value; e.target.value = ""; ta.focus(); }
  });
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    const body = { node_name: qv("node_name"), expression: qv("expression"), enabled: document.getElementById("node-enabled").checked };
    try {
      if (isEdit) await Api.put(`/api/connectors/${c.id}/opcua-server-nodes/${node.id}`, body);
      else await Api.post(`/api/connectors/${c.id}/opcua-server-nodes`, body);
      closeModal(); toast("Saved"); viewConnectorDetail(c.id);
    } catch (e) { toast(e.message, true); }
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

route();
