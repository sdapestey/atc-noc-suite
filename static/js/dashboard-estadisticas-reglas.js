let _qualityToastTimer = null;
let _calidadRules = [];
let _pageOffset = 0;
const _pageSize = 50;
let _rulesChart = null;
let _lastResumen = null;
let _reglasInitialized = false;

const _CD = window.CalidadDashboard || {};
const _calidadApi = () => _CD.api || {};
const _esc =
  _CD.esc ||
  function (v) {
    return String(v || "");
  };
const _fmtCount =
  _CD.fmtCount ||
  function (n) {
    return String(n);
  };

function qualityToast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  if (_qualityToastTimer) clearTimeout(_qualityToastTimer);
  _qualityToastTimer = setTimeout(() => el.classList.remove("show"), 1400);
}

function _filters() {
  return {
    regla: (document.getElementById("f-regla")?.value || "").trim(),
    estado_base: (document.getElementById("f-estado")?.value || "").trim(),
    operador: (document.getElementById("f-operador")?.value || "").trim(),
    q: (document.getElementById("f-q")?.value || "").trim(),
  };
}

function _queryString(filters, extra) {
  const params = new URLSearchParams();
  if (filters.regla) params.set("regla", filters.regla);
  if (filters.estado_base) params.set("estado_base", filters.estado_base);
  if (filters.operador) params.set("operador", filters.operador);
  if (filters.q) params.set("q", filters.q);
  if (extra) {
    Object.keys(extra).forEach((k) => {
      if (extra[k] !== undefined && extra[k] !== null && extra[k] !== "") {
        params.set(k, String(extra[k]));
      }
    });
  }
  return params.toString();
}

function syncExportLink(filters) {
  const a = document.getElementById("btn-export");
  if (!a) return;
  const qs = _queryString(filters);
  a.href = _calidadApi().reglasExportCsv + (qs ? `?${qs}` : "");
}

function renderKpiGrid(resumen) {
  const grid = document.getElementById("calidad-kpi-grid");
  if (!grid || !resumen) return;
  _lastResumen = resumen;

  const statusCards = [
    { key: "", label: 'AID "IN SERVICE"', value: resumen.total_aid_in_service, drill: false },
    { key: "", label: 'AID "RESERVED"', value: resumen.total_aid_reserved, drill: false },
    { key: "", label: 'AID "TO BE DELETED"', value: resumen.total_aid_to_be_deleted, drill: false },
    { key: "", label: 'AID "FREE"', value: resumen.total_aid_free, drill: false },
  ];

  const rules = Array.isArray(resumen.rules) ? resumen.rules : [];
  const ruleCards = rules.map((r) => ({
    key: r.id,
    label: r.label,
    value: r.count != null ? r.count : resumen[r.kpi_key] || 0,
    drill: true,
  }));

  const all = statusCards.concat(ruleCards);
  grid.innerHTML = all
    .map((c) => {
      const cls = c.drill ? "metric-card metric-card--drill" : "metric-card";
      const dataRule = c.key ? ` data-rule-id="${_esc(c.key)}"` : "";
      return `
      <button type="button" class="${cls}"${dataRule} title="${c.drill ? "Ver hallazgos de esta regla" : ""}">
        <div class="label">${_esc(c.label)}</div>
        <div class="value mono">${_esc(c.value)}</div>
      </button>`;
    })
    .join("");

  grid.querySelectorAll(".metric-card--drill").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ruleId = btn.getAttribute("data-rule-id");
      if (!ruleId) return;
      const sel = document.getElementById("f-regla");
      if (sel) sel.value = ruleId;
      syncReglaRuleHelp();
      _pageOffset = 0;
      refreshFindingsOnly();
      document.getElementById("findings-table")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  renderRulesChart(rules.length ? rules : ruleCards);
}

function renderRulesChart(rules) {
  const canvas = document.getElementById("calidad-rules-chart");
  if (!canvas || typeof Chart === "undefined") return;
  const labels = rules.map((r) => r.label);
  const data = rules.map((r) => Number(r.count != null ? r.count : 0));
  if (_rulesChart) _rulesChart.destroy();
  _rulesChart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Hallazgos",
          data,
          backgroundColor: "rgba(88, 166, 255, 0.55)",
          borderColor: "rgba(88, 166, 255, 0.9)",
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#9aa7b2", maxRotation: 45, minRotation: 25 } },
        y: { beginAtZero: true, ticks: { color: "#9aa7b2", precision: 0 } },
      },
      onClick: (_evt, elements) => {
        if (!elements.length || !rules[elements[0].index]) return;
        const ruleId = rules[elements[0].index].id;
        const sel = document.getElementById("f-regla");
        if (sel) sel.value = ruleId;
        syncReglaRuleHelp();
        _pageOffset = 0;
        refreshFindingsOnly();
      },
    },
  });
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

function syncPagination(totalCount) {
  const wrap = document.getElementById("calidad-pagination");
  const info = document.getElementById("calidad-page-info");
  const prev = document.getElementById("btn-page-prev");
  const next = document.getElementById("btn-page-next");
  if (!wrap || !info || !prev || !next) return;

  if (totalCount <= _pageSize) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  const page = Math.floor(_pageOffset / _pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(totalCount / _pageSize));
  info.textContent = `Página ${page} de ${totalPages} · ${totalCount} hallazgos`;
  prev.disabled = _pageOffset <= 0;
  next.disabled = _pageOffset + _pageSize >= totalCount;
}

function renderFindings(payload) {
  const body = document.getElementById("findings-body");
  const count = document.getElementById("qualityCount");
  if (!body) return;
  const list = payload && Array.isArray(payload.findings) ? payload.findings : [];
  const total = payload && payload.total_count != null ? payload.total_count : list.length;

  if (!list.length) {
    body.innerHTML = '<tr><td colspan="6">Sin hallazgos para los filtros aplicados.</td></tr>';
  } else {
    body.innerHTML = list
      .map(
        (f) => `
      <tr>
        <td>${_esc(f.regla)}</td>
        <td class="mono">${_esc(f.access_id)}</td>
        <td class="mono">${_esc(f.base_status)}</td>
        <td class="mono">${_esc(f.path_atc)}</td>
        <td class="mono">${_esc(f.cto)}</td>
        <td class="mono">${_esc(f.operador)}</td>
      </tr>
    `
      )
      .join("");
  }
  if (count) {
    count.textContent =
      total > list.length ? `${list.length} de ${total} hallazgos` : `${total} hallazgos`;
  }
  syncPagination(total);
}

async function fetchResumen() {
  const r = await fetch(_calidadApi().reglasResumen);
  if (!r.ok) throw new Error("No se pudo obtener resumen");
  return r.json();
}

async function fetchFindings(filters) {
  const qs = _queryString(filters, { limit: _pageSize, offset: _pageOffset });
  const r = await fetch(`${_calidadApi().reglasHallazgos}?${qs}`);
  if (!r.ok) throw new Error("No se pudo obtener hallazgos");
  return r.json();
}

async function refreshFindingsOnly() {
  const filters = _filters();
  syncExportLink(filters);
  try {
    const payload = await fetchFindings(filters);
    renderRules(payload.rules || []);
    renderBaseStatuses(payload.base_statuses || []);
    renderFindings(payload);
  } catch (_err) {
    qualityToast("No se pudo actualizar hallazgos");
  }
}

async function refreshCalidadDashboard() {
  const filters = _filters();
  syncExportLink(filters);
  try {
    const [resumen, payload] = await Promise.all([fetchResumen(), fetchFindings(filters)]);
    renderKpiGrid(resumen);
    renderRules(payload.rules || []);
    renderBaseStatuses(payload.base_statuses || []);
    renderFindings(payload);
  } catch (_err) {
    qualityToast("No se pudo actualizar el dashboard");
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".calidad-tab").forEach((btn) => {
    const active = btn.getAttribute("data-tab") === tabId;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const panelInventario = document.getElementById("panel-inventario");
  if (panelInventario) panelInventario.hidden = tabId !== "inventario";
  document.getElementById("panel-reglas").hidden = tabId !== "reglas";
  const panelAltasBajas = document.getElementById("panel-altas-bajas");
  if (panelAltasBajas) panelAltasBajas.hidden = tabId !== "altas-bajas";

  if (tabId === "altas-bajas" && typeof window.loadCalidadEstadisticas === "function") {
    window.loadCalidadEstadisticas();
  }
  if (tabId === "inventario" && typeof window.loadCalidadResumenGeneral === "function") {
    window.loadCalidadResumenGeneral();
  }
  if (tabId === "reglas" && !_reglasInitialized) {
    _reglasInitialized = true;
    refreshCalidadDashboard();
  }
}
window.switchTab = switchTab;
window.refreshCalidadDashboard = refreshCalidadDashboard;
window.resetCalidadHallazgosPage = function () {
  _pageOffset = 0;
};

window.addEventListener("load", () => {
  document.querySelectorAll(".calidad-tab").forEach((btn) => {
    if (btn.dataset.calidadTabBound === "1") return;
    btn.dataset.calidadTabBound = "1";
    btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
  });

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
      _pageOffset = 0;
      refreshFindingsOnly();
    });
  });

  const btn = document.getElementById("btn-refresh");
  if (btn) {
    btn.addEventListener("click", () => {
      _pageOffset = 0;
      refreshCalidadDashboard();
    });
  }

  document.getElementById("btn-page-prev")?.addEventListener("click", () => {
    _pageOffset = Math.max(0, _pageOffset - _pageSize);
    refreshFindingsOnly();
  });
  document.getElementById("btn-page-next")?.addEventListener("click", () => {
    _pageOffset += _pageSize;
    refreshFindingsOnly();
  });


  if (window.initNocPage) {
    initNocPage({
      page: "calidad",
      searchSelector: "#f-q",
      onSearchChange: function () {
        const filters = _filters();
        syncExportLink(filters);
        _pageOffset = 0;
        refreshFindingsOnly();
      },
    });
  }

  if (typeof window.loadCalidadEstadisticas === "function") {
    switchTab("altas-bajas");
  } else if (typeof window.loadCalidadResumenGeneral === "function") {
    switchTab("inventario");
  } else {
    switchTab("reglas");
    _reglasInitialized = true;
    refreshCalidadDashboard();
  }
});
