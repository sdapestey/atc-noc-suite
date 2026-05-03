let _qualityToastTimer = null;
let _calidadRules = [];

function qualityToast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  if (_qualityToastTimer) clearTimeout(_qualityToastTimer);
  _qualityToastTimer = setTimeout(() => el.classList.remove("show"), 1400);
}

function _esc(v) {
  return String(v || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function _kpiRows(data) {
  return [
    ['AID con estado "IN SERVICE"', data.total_aid_in_service],
    ['AID con estado "RESERVED"', data.total_aid_reserved],
    ['AID con estado "TO BE DELETED"', data.total_aid_to_be_deleted],
    ['AID con estado "FREE"', data.total_aid_free],
    ["AID IN SERVICE sin match en SERIAL", data.aid_sin_match_serial],
    ["AID IN SERVICE sin match en OLT", data.aid_sin_match_olt],
    ["AID IN SERVICE con path_atc nulo/vacio", data.aid_path_atc_nulo_vacio],
    ["AID con serial_number nulo/vacio", data.aid_serial_nulo_vacio],
  ];
}

function renderResumen(data) {
  const body = document.getElementById("kpi-body");
  if (!body) return;
  const rows = _kpiRows(data || {});
  body.innerHTML = rows
    .map((r) => `<tr><td>${_esc(r[0])}</td><td class="mono">${_esc(r[1])}</td></tr>`)
    .join("");
}

function renderRules(rules) {
  const sel = document.getElementById("f-regla");
  if (!sel) return;
  const current = sel.value || "";
  _calidadRules = Array.isArray(rules) ? rules : [];
  const options = [{ id: "", label: "Todas" }].concat(_calidadRules);
  sel.innerHTML = options
    .map((r) => `<option value="${_esc(r.id)}">${_esc(r.label)}</option>`)
    .join("");
  sel.value = current;
  syncReglaRuleHelp();
}

function syncReglaRuleHelp() {
  const sel = document.getElementById("f-regla");
  const help = document.getElementById("f-regla-rule-help");
  if (!sel || !help) return;
  const id = (sel.value || "").trim();
  const rule = _calidadRules.find((r) => r.id === id);
  const desc = rule && rule.description ? String(rule.description).trim() : "";
  if (desc) {
    help.textContent = desc;
    help.hidden = false;
    sel.setAttribute("aria-describedby", "f-regla-rule-help");
  } else {
    help.textContent = "";
    help.hidden = true;
    sel.removeAttribute("aria-describedby");
  }
}

function renderBaseStatuses(statuses) {
  const sel = document.getElementById("f-estado");
  if (!sel) return;
  const current = sel.value || "";
  const options = [{ id: "", label: "Todos" }].concat(Array.isArray(statuses) ? statuses : []);
  sel.innerHTML = options
    .map((s) => `<option value="${_esc(s.id)}">${_esc(s.label)}</option>`)
    .join("");
  sel.value = current;
}

function renderFindings(payload) {
  const body = document.getElementById("findings-body");
  const count = document.getElementById("qualityCount");
  if (!body) return;
  const list = payload && Array.isArray(payload.findings) ? payload.findings : [];
  if (!list.length) {
    body.innerHTML = '<tr><td colspan="6">Sin hallazgos para los filtros aplicados.</td></tr>';
  } else {
    body.innerHTML = list
      .map((f) => `
      <tr>
        <td>${_esc(f.regla)}</td>
        <td class="mono">${_esc(f.access_id)}</td>
        <td class="mono">${_esc(f.base_status)}</td>
        <td class="mono">${_esc(f.path_atc)}</td>
        <td class="mono">${_esc(f.cto)}</td>
        <td class="mono">${_esc(f.operador)}</td>
      </tr>
    `)
      .join("");
  }
  if (count) count.textContent = `${list.length} hallazgos`;
}

function _filters() {
  return {
    regla: (document.getElementById("f-regla")?.value || "").trim(),
    estado_base: (document.getElementById("f-estado")?.value || "").trim(),
    operador: (document.getElementById("f-operador")?.value || "").trim(),
    q: (document.getElementById("f-q")?.value || "").trim(),
  };
}

function _queryString(filters) {
  const params = new URLSearchParams();
  if (filters.regla) params.set("regla", filters.regla);
  if (filters.estado_base) params.set("estado_base", filters.estado_base);
  if (filters.operador) params.set("operador", filters.operador);
  if (filters.q) params.set("q", filters.q);
  return params.toString();
}

function syncExportLink(filters) {
  const a = document.getElementById("btn-export");
  if (!a) return;
  const qs = _queryString(filters);
  a.href = "/dashboard/calidad-inventario/export.csv" + (qs ? `?${qs}` : "");
}

async function fetchResumen() {
  const r = await fetch("/dashboard/calidad-inventario/resumen.json");
  if (!r.ok) throw new Error("No se pudo obtener resumen");
  return r.json();
}

async function fetchFindings(filters) {
  const qs = _queryString(filters);
  const r = await fetch(`/dashboard/calidad-inventario/hallazgos.json?${qs}`);
  if (!r.ok) throw new Error("No se pudo obtener hallazgos");
  return r.json();
}

async function refreshCalidadDashboard() {
  const filters = _filters();
  syncExportLink(filters);
  try {
    const [resumen, payload] = await Promise.all([fetchResumen(), fetchFindings(filters)]);
    renderResumen(resumen);
    renderRules(payload.rules || []);
    renderBaseStatuses(payload.base_statuses || []);
    renderFindings(payload);
  } catch (_err) {
    qualityToast("No se pudo actualizar el dashboard");
  }
}

window.addEventListener("load", () => {
  const bindIds = ["f-regla", "f-estado", "f-operador", "f-q"];
  bindIds.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", () => {
      const filters = _filters();
      syncExportLink(filters);
      if (id === "f-regla") syncReglaRuleHelp();
    });
    el.addEventListener("change", () => {
      if (id === "f-regla") syncReglaRuleHelp();
      refreshCalidadDashboard();
    });
  });
  const btn = document.getElementById("btn-refresh");
  if (btn) btn.addEventListener("click", refreshCalidadDashboard);
  if (window.initNocPage) {
    initNocPage({
      page: "calidad",
      searchSelector: "#f-q",
      onSearchChange: function () {
        const filters = _filters();
        syncExportLink(filters);
      },
    });
  }
  refreshCalidadDashboard();
});
