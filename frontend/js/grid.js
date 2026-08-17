/* Generic spreadsheet-style editable grid used by the register/node pages.
 * One row per register; "+ Add Row" appends a blank editable row; "Save
 * Changes" batches create/update calls (skipping per-call driver restarts,
 * then restarting once at the end if the connector was already running);
 * deleting an existing row happens immediately (with confirm), matching the
 * rest of the app. */

let lastFocusedExpressionInput = null;

function createRegisterGrid({ container, columns, rows, apiBase, connectorId, isRunning, defaultRow }) {
  let gridRows = rows.map((r) => ({ id: r.id, values: { ...r }, original: JSON.stringify(r) }));

  function addBlankRow() {
    gridRows.push({ id: null, values: { ...defaultRow }, original: null });
    render();
    const inputs = container.querySelectorAll(".grid-input");
    if (inputs.length) inputs[inputs.length - columns.length]?.focus();
  }

  function removeRowLocal(idx) {
    gridRows.splice(idx, 1);
    render();
  }

  async function deleteExisting(idx) {
    if (!confirm("Delete this row?")) return;
    const row = gridRows[idx];
    try {
      await Api.del(`${apiBase}/${row.id}?restart=${isRunning ? "true" : "false"}`);
      gridRows.splice(idx, 1);
      render();
      toast("Deleted");
    } catch (e) { toast(e.message, true); }
  }

  function cellInput(col, row, idx) {
    const val = row.values[col.key];
    if (col.type === "select") {
      const widestLabel = Math.max(...col.options.map((o) => o.label.length));
      return `<select class="grid-input" data-idx="${idx}" data-key="${col.key}" style="min-width:${Math.min(widestLabel * 8 + 40, 220)}px">
        ${col.options.map((o) => `<option value="${esc(String(o.value))}" ${String(val) === String(o.value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}
      </select>`;
    }
    if (col.type === "checkbox") {
      return `<input type="checkbox" class="grid-input" data-idx="${idx}" data-key="${col.key}" ${val ? "checked" : ""} />`;
    }
    if (col.type === "expression") {
      return `<input type="text" class="grid-input grid-expression mono" data-idx="${idx}" data-key="${col.key}"
        value="${esc(val ?? "")}" placeholder="${esc(col.placeholder || "")}" style="min-width:220px" />`;
    }
    return `<input type="${col.type === "number" ? "number" : "text"}" ${col.step ? `step="${col.step}"` : ""}
      class="grid-input" data-idx="${idx}" data-key="${col.key}" value="${esc(val ?? "")}" placeholder="${esc(col.placeholder || "")}" />`;
  }

  function render() {
    if (!gridRows.length) {
      container.innerHTML = `<div class="empty-state">No rows yet. Click "+ Add Row" or "Import CSV" to get started.</div>`;
      return;
    }
    container.innerHTML = `<div style="overflow-x:auto"><table class="grid-table">
      <thead><tr>${columns.map((c) => `<th>${esc(c.label)}</th>`).join("")}<th></th></tr></thead>
      <tbody>${gridRows.map((row, idx) => `
        <tr>${columns.map((c) => `<td>${cellInput(c, row, idx)}</td>`).join("")}
          <td><button class="btn btn-sm btn-danger grid-del" data-idx="${idx}" title="Delete row">&times;</button></td>
        </tr>`).join("")}</tbody>
    </table></div>`;

    container.querySelectorAll(".grid-input").forEach((input) => {
      const evt = input.type === "checkbox" ? "change" : "input";
      input.addEventListener(evt, () => {
        const idx = Number(input.dataset.idx);
        const key = input.dataset.key;
        gridRows[idx].values[key] = input.type === "checkbox" ? input.checked : input.value;
      });
      if (input.classList.contains("grid-expression")) {
        input.addEventListener("focus", () => { lastFocusedExpressionInput = input; });
      }
    });
    container.querySelectorAll(".grid-del").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.idx);
        if (gridRows[idx].id) deleteExisting(idx);
        else removeRowLocal(idx);
      });
    });
  }

  function bodyFor(row) {
    const body = {};
    for (const c of columns) {
      let v = row.values[c.key];
      if (c.type === "number") v = v === "" || v === null || v === undefined ? 0 : parseFloat(v);
      if (c.type === "checkbox") v = !!v;
      if (c.type === "text" && c.key === "description" && !v) v = null;
      body[c.key] = v;
    }
    return body;
  }

  async function saveAll() {
    let created = 0, updated = 0, changedAny = false;
    const errors = [];
    for (const row of gridRows) {
      const body = bodyFor(row);
      try {
        if (row.id) {
          if (JSON.stringify(row.values) === row.original) continue;
          await Api.put(`${apiBase}/${row.id}?restart=false`, body);
          row.original = JSON.stringify(row.values);
          updated++; changedAny = true;
        } else {
          const createdRow = await Api.post(`${apiBase}?restart=false`, body);
          row.id = createdRow.id;
          row.original = JSON.stringify(row.values);
          created++; changedAny = true;
        }
      } catch (e) {
        const label = row.values[columns[0].key] || "(row)";
        errors.push(`${label}: ${e.message}`);
      }
    }
    if (changedAny && isRunning) {
      try { await Api.post(`/api/connectors/${connectorId}/restart`); } catch (e) { /* surfaced via connector status */ }
    }
    if (errors.length) toast(`Saved with ${errors.length} error(s): ${errors[0]}`, true);
    else if (created || updated) toast(`Saved (${created} added, ${updated} updated)`);
    else toast("Nothing to save");
    render();
  }

  render();
  return { addBlankRow, saveAll };
}
