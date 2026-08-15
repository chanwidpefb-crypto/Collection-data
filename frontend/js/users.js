/* Users management page (admin only). */

async function viewUsers() {
  setHeader("Users", "Manage who can log in and what they can do",
    `<button class="btn btn-primary" id="btn-add-user">+ Add User</button>`);
  document.getElementById("btn-add-user").onclick = openAddUserModal;

  const content = document.getElementById("content");
  content.innerHTML = `<div class="card"><div class="card-body" id="users-table"><div class="empty-state">Loading...</div></div></div>`;

  let users;
  try { users = await Api.get("/api/users"); }
  catch (e) { document.getElementById("users-table").innerHTML = `<div class="empty-state">${esc(e.message)}</div>`; return; }

  const wrap = document.getElementById("users-table");
  wrap.innerHTML = `<table>
    <thead><tr><th>Username</th><th>Role</th><th>Created</th><th></th></tr></thead>
    <tbody>${users.map((u) => `
      <tr>
        <td><b>${esc(u.username)}</b>${u.id === currentUser.id ? ` <span class="pill pill-neutral">you</span>` : ""}</td>
        <td>
          <select data-role-select="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>
            <option value="admin" ${u.role === "admin" ? "selected" : ""}>admin</option>
            <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>viewer</option>
          </select>
        </td>
        <td class="mono">${new Date(u.created_at + "Z").toLocaleString()}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-reset="${u.id}">Reset Password</button>
          <button class="btn btn-sm btn-danger" data-del="${u.id}" ${u.id === currentUser.id ? "disabled" : ""}>Delete</button>
        </td>
      </tr>`).join("")}</tbody></table>`;

  wrap.querySelectorAll("[data-role-select]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        await Api.patch(`/api/users/${sel.dataset.roleSelect}/role`, { role: sel.value });
        toast("Role updated");
        viewUsers();
      } catch (e) { toast(e.message, true); viewUsers(); }
    });
  });
  wrap.querySelectorAll("[data-reset]").forEach((btn) => btn.onclick = () => openResetPasswordModal(btn.dataset.reset));
  wrap.querySelectorAll("[data-del]").forEach((btn) => btn.onclick = async () => {
    if (!confirm("Delete this user?")) return;
    try { await Api.del(`/api/users/${btn.dataset.del}`); toast("User deleted"); viewUsers(); }
    catch (e) { toast(e.message, true); }
  });
}

function openAddUserModal() {
  showModal("Add User", `
    <div class="form-field full">
      <label>Username</label>
      <input type="text" name="username" />
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>Password</label>
      <input type="password" name="password" />
      <span class="hint">at least 8 characters</span>
    </div>
    <div class="form-field full" style="margin-top:14px">
      <label>Role</label>
      <select name="role">
        <option value="viewer">viewer -- Live Monitor &amp; Trend only</option>
        <option value="admin">admin -- full access incl. Connectors &amp; Users</option>
      </select>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">Create</button>
    </div>`);
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    try {
      await Api.post("/api/users", { username: qv("username"), password: qv("password"), role: qv("role") });
      closeModal(); toast("User created"); viewUsers();
    } catch (e) { toast(e.message, true); }
  };
}

function openResetPasswordModal(userId) {
  showModal("Reset Password", `
    <div class="form-field full">
      <label>New Password</label>
      <input type="password" name="new_password" />
      <span class="hint">at least 8 characters</span>
    </div>
    <div class="form-actions">
      <button class="btn" id="cancel">Cancel</button>
      <button class="btn btn-primary" id="save">Reset</button>
    </div>`);
  document.getElementById("cancel").onclick = closeModal;
  document.getElementById("save").onclick = async () => {
    try {
      await Api.post(`/api/users/${userId}/reset-password`, { new_password: qv("new_password") });
      closeModal(); toast("Password reset");
    } catch (e) { toast(e.message, true); }
  };
}
