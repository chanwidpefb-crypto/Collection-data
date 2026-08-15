/* Login screen, session bootstrap, and role-aware nav / sidebar footer. */

let currentUser = null;
window.onUnauthorized = () => { currentUser = null; showLoginScreen(); };

const NAV_ITEMS = [
  { route: "connectors", label: "Connectors", icon: "&#9881;", adminOnly: true },
  { route: "live", label: "Live Monitor", icon: "&#9679;", adminOnly: false },
  { route: "trend", label: "Trend", icon: "&#128200;", adminOnly: false },
  { route: "users", label: "Users", icon: "&#128100;", adminOnly: true },
  { route: "settings", label: "Settings", icon: "&#128736;", adminOnly: true },
];

function renderNav() {
  const nav = document.getElementById("nav");
  const items = NAV_ITEMS.filter((n) => !n.adminOnly || (currentUser && currentUser.role === "admin"));
  nav.innerHTML = items.map((n) => `<li><a href="#/${n.route}" data-route="${n.route}"><span class="icon">${n.icon}</span> ${esc(n.label)}</a></li>`).join("");
}

function renderSidebarFooter() {
  const el = document.getElementById("sidebar-footer");
  if (!currentUser) { el.innerHTML = "Collection Data v0.1"; return; }
  el.innerHTML = `
    <div style="margin-bottom:8px">
      <div style="color:#fff;font-weight:700">${esc(currentUser.username)}</div>
      <div style="text-transform:capitalize">${esc(currentUser.role)}</div>
    </div>
    <div style="display:flex;gap:10px">
      <a href="#" id="link-change-password" style="color:#8ea2e0">Change password</a>
      <a href="#" id="link-logout" style="color:#8ea2e0">Logout</a>
    </div>`;
  document.getElementById("link-change-password").onclick = (e) => { e.preventDefault(); openChangePasswordModal(); };
  document.getElementById("link-logout").onclick = async (e) => {
    e.preventDefault();
    try { await Api.post("/api/auth/logout"); } catch (err) { /* ignore */ }
    currentUser = null;
    showLoginScreen();
  };
}

function openChangePasswordModal() {
  showModal("Change Password", `
    <div class="form-field full">
      <label>Current Password</label>
      <input type="password" name="old_password" />
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>New Password</label>
      <input type="password" name="new_password" />
      <span class="hint">at least 8 characters</span>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">Change Password</button>
    </div>`);
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    try {
      await Api.patch("/api/auth/me", { old_password: qv("old_password"), new_password: qv("new_password") });
      closeModal();
      toast("Password changed");
    } catch (e) { toast(e.message, true); }
  };
}

function showLoginScreen() {
  document.getElementById("app-shell").style.display = "none";
  stopLiveRefresh();
  if (typeof stopTrendAutoRefresh === "function") stopTrendAutoRefresh();
  const root = document.getElementById("login-root");
  root.innerHTML = `
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--navy)">
      <div style="background:#fff;border-radius:14px;padding:34px;width:360px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,.35)">
        <div style="text-align:center;margin-bottom:22px">
          <div style="font-size:22px;font-weight:800">Collection<span style="color:var(--accent-2)">Data</span></div>
          <div style="font-size:12px;color:var(--text-dim);margin-top:4px">Modbus TCP &amp; OPC UA Collector</div>
        </div>
        <div class="form-field full">
          <label>Username</label>
          <input type="text" id="login-username" autocomplete="username" />
        </div>
        <div class="form-field full" style="margin-top:12px">
          <label>Password</label>
          <input type="password" id="login-password" autocomplete="current-password" />
        </div>
        <div id="login-error" style="color:var(--bad);font-size:12.5px;margin-top:10px;min-height:16px"></div>
        <button class="btn btn-primary" id="login-submit" style="width:100%;margin-top:6px;padding:10px">Log In</button>
      </div>
    </div>`;

  const submit = async () => {
    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const errEl = document.getElementById("login-error");
    errEl.textContent = "";
    if (!username || !password) { errEl.textContent = "Please enter username and password"; return; }
    try {
      currentUser = await Api.post("/api/auth/login", { username, password });
      root.innerHTML = "";
      document.getElementById("app-shell").style.display = "";
      renderNav();
      renderSidebarFooter();
      route();
    } catch (e) {
      errEl.textContent = "Invalid username or password";
    }
  };
  document.getElementById("login-submit").onclick = submit;
  root.querySelectorAll("input").forEach((inp) => inp.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); }));
  document.getElementById("login-username").focus();
}

async function boot() {
  try {
    currentUser = await Api.get("/api/auth/me");
    document.getElementById("app-shell").style.display = "";
    renderNav();
    renderSidebarFooter();
    route();
  } catch (e) {
    showLoginScreen();
  }
}

boot();
