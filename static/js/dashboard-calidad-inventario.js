let _qualityToastTimer = null;
let _calidadRules = [];
let _pageOffset = 0;
const _pageSize = 50;
let _rulesChart = null;
let _historicoChart = null;
let _historicoDays = 90;
let _lastResumen = null;
let _reglasInitialized = false;

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
  a.href = "/dashboard/calidad-inventario/export.csv" + (qs ? `?${qs}` : "");
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
  const r = await fetch("/dashboard/calidad-inventario/resumen.json");
  if (!r.ok) throw new Error("No se pudo obtener resumen");
  return r.json();
}

async function fetchFindings(filters) {
  const qs = _queryString(filters, { limit: _pageSize, offset: _pageOffset });
  const r = await fetch(`/dashboard/calidad-inventario/hallazgos.json?${qs}`);
  if (!r.ok) throw new Error("No se pudo obtener hallazgos");
  return r.json();
}

async function fetchConciliacion() {
  const r = await fetch("/dashboard/calidad-inventario/conciliacion.json");
  if (!r.ok) throw new Error("No se pudo obtener conciliación");
  return r.json();
}

async function fetchHistorico(days) {
  const r = await fetch(`/dashboard/calidad-inventario/historico.json?days=${days}`);
  if (!r.ok) throw new Error("No se pudo obtener histórico");
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

function _fmtCount(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x.toLocaleString("es-AR");
}

function _opSlug(label) {
  return String(label || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function _bigNumberCard(title, value, footLabel, operatorId, variant) {
  const opAttr = operatorId ? ` data-operator-id="${_esc(operatorId)}"` : "";
  const clickable = operatorId ? " calidad-big-card--clickable" : "";
  const variantCls = variant ? ` calidad-big-card--${variant}` : "";
  const slugCls = footLabel ? ` calidad-big-card--op-${_opSlug(footLabel)}` : "";
  const titleAttr = operatorId
    ? ` title="Filtrar hallazgos por operador ${_esc(operatorId)}"`
    : "";
  const tag =
    operatorId || variant === "hero-cm" || variant === "hero-alt"
      ? "button"
      : "div";
  const typeAttr = tag === "button" ? ' type="button"' : "";
  const kpiBody = `
      <span class="calidad-big-card__value mono">${_esc(_fmtCount(value))}</span>
      ${footLabel ? `<span class="calidad-big-card__foot">${_esc(footLabel)}</span>` : ""}`;
  return `
    <${tag} class="calidad-big-card${variantCls}${slugCls}${clickable}"${typeAttr}${opAttr}${titleAttr}>
      <span class="calidad-big-card__title">${_esc(title)}</span>
      <div class="calidad-big-card__kpi">${kpiBody}</div>
    </${tag}>`;
}

function _bindOperatorCards(root) {
  if (!root) return;
  root.querySelectorAll(".calidad-big-card[data-operator-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const opId = btn.getAttribute("data-operator-id");
      const opInput = document.getElementById("f-operador");
      if (opInput && opId) opInput.value = opId;
      switchTab("reglas");
      _pageOffset = 0;
      refreshCalidadDashboard();
    });
  });
}

function renderConciliacion(data) {
  const board = document.getElementById("conciliacion-dashboard");
  const body = document.getElementById("conciliacion-body");
  if (!board || !body || !data) return;

  const t = data.totals || {};
  const cmTotal =
    t.connect_master_in_service != null
      ? t.connect_master_in_service
      : t.bajada_inventario_in_service;
  const altTotal = t.altiplano_activos;

  const ops = Array.isArray(data.operators) ? data.operators : [];
  const altiplanoCards = ops
    .map((o) =>
      _bigNumberCard(
        `Activos ${o.label}`,
        o.altiplano != null ? o.altiplano : 0,
        o.label,
        o.id,
        "op"
      )
    )
    .join("");
  const cmCards = ops
    .map((o) => {
      const cm = o.connect_master != null ? o.connect_master : o.in_service;
      return _bigNumberCard(`Activos ${o.label}`, cm, o.label, o.id, "op");
    })
    .join("");

  board.classList.add("calidad-activos-board--loaded");
  board.innerHTML = `
    <div class="calidad-activos-shell">
      <section class="calidad-activos-hero" aria-labelledby="calidad-total-activos-title">
        <header class="calidad-zone-header calidad-zone-header--hero">
          <h2 class="calidad-board-title" id="calidad-total-activos-title">Total activos</h2>
        </header>
        <div class="calidad-big-row calidad-big-row--2 calidad-big-row--hero">
          ${_bigNumberCard("Total Activos en Connect Master", cmTotal, "", null, "hero-cm")}
          ${_bigNumberCard("Activos Totales Altiplano", altTotal, "", null, "hero-alt")}
        </div>
      </section>
      <section class="calidad-activos-zone calidad-activos-zone--altiplano" aria-labelledby="calidad-altiplano-title">
        <header class="calidad-zone-header">
          <span class="calidad-zone-badge calidad-zone-badge--alt">Altiplano</span>
          <h2 class="calidad-board-title" id="calidad-altiplano-title">Activos por operador</h2>
        </header>
        <div class="calidad-big-row calidad-big-row--5">${altiplanoCards}</div>
      </section>
      <section class="calidad-activos-zone calidad-activos-zone--cm" aria-labelledby="calidad-cm-title">
        <header class="calidad-zone-header">
          <span class="calidad-zone-badge calidad-zone-badge--cm">Connect Master</span>
          <h2 class="calidad-board-title" id="calidad-cm-title">Activos por operador</h2>
        </header>
        <div class="calidad-big-row calidad-big-row--5">${cmCards}</div>
      </section>
    </div>
  `;
  _bindOperatorCards(board);

  if (!ops.length) {
    body.innerHTML = '<tr><td colspan="4">Sin datos.</td></tr>';
    return;
  }
  body.innerHTML = ops
    .map(
      (o) => `
    <tr data-operator-id="${_esc(o.id)}" title="Filtrar hallazgos por operador ${_esc(o.id)}">
      <td>${_esc(o.label)}</td>
      <td class="mono">${_esc(o.id)}</td>
      <td class="mono">${_fmtCount(o.connect_master != null ? o.connect_master : o.in_service)}</td>
      <td class="mono">${_fmtCount(o.reserved)}</td>
    </tr>
  `
    )
    .join("");

  body.querySelectorAll("tr[data-operator-id]").forEach((row) => {
    row.addEventListener("click", () => {
      const opId = row.getAttribute("data-operator-id");
      const opInput = document.getElementById("f-operador");
      if (opInput && opId) opInput.value = opId;
      switchTab("reglas");
      _pageOffset = 0;
      refreshCalidadDashboard();
    });
  });
}

function renderHistorico(data) {
  const canvas = document.getElementById("calidad-historico-chart");
  const empty = document.getElementById("historico-empty");
  if (!canvas || typeof Chart === "undefined") return;

  const series = data && Array.isArray(data.series) ? data.series : [];
  if (!series.length) {
    if (_historicoChart) {
      _historicoChart.destroy();
      _historicoChart = null;
    }
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  const labels = series.map((p) => p.fecha);
  if (_historicoChart) _historicoChart.destroy();
  _historicoChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "CM no Nokia",
          data: series.map((p) => p.cm_no_nokia),
          borderColor: "rgba(88, 166, 255, 0.9)",
          backgroundColor: "rgba(88, 166, 255, 0.15)",
          fill: true,
          tension: 0.2,
        },
        {
          label: "Nokia no CM",
          data: series.map((p) => p.nokia_no_cm),
          borderColor: "rgba(248, 81, 73, 0.9)",
          backgroundColor: "rgba(248, 81, 73, 0.12)",
          fill: true,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#9aa7b2" } } },
      scales: {
        x: { ticks: { color: "#9aa7b2", maxTicksLimit: 12 } },
        y: { beginAtZero: true, ticks: { color: "#9aa7b2", precision: 0 } },
      },
    },
  });
}

async function loadConciliacionPanel() {
  try {
    const data = await fetchConciliacion();
    renderConciliacion(data);
  } catch (_err) {
    qualityToast("No se pudo cargar conciliación");
  }
}

async function loadHistoricoPanel() {
  try {
    const data = await fetchHistorico(_historicoDays);
    renderHistorico(data);
  } catch (_err) {
    qualityToast("No se pudo cargar histórico");
  }
}

function switchTab(tabId) {
  document.querySelectorAll(".calidad-tab").forEach((btn) => {
    const active = btn.getAttribute("data-tab") === tabId;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const panelResumen = document.getElementById("panel-resumen");
  const panelConciliacion = document.getElementById("panel-conciliacion");
  if (panelResumen) panelResumen.hidden = tabId !== "resumen";
  if (panelConciliacion) panelConciliacion.hidden = tabId !== "resumen" && tabId !== "conciliacion";
  document.getElementById("panel-reglas").hidden = tabId !== "reglas";
  const panelHistorico = document.getElementById("panel-historico");
  if (panelHistorico) panelHistorico.hidden = tabId !== "historico";

  if (tabId === "resumen" && typeof window.loadCalidadResumenGeneral === "function") {
    window.loadCalidadResumenGeneral();
  }
  if (tabId === "conciliacion" && typeof loadConciliacionPanel === "function") loadConciliacionPanel();
  if (tabId === "historico" && typeof loadHistoricoPanel === "function") loadHistoricoPanel();
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

  document.querySelectorAll("#historico-range [data-days]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#historico-range [data-days]").forEach((b) => {
        b.classList.toggle("is-active", b === btn);
      });
      _historicoDays = parseInt(btn.getAttribute("data-days"), 10) || 90;
      loadHistoricoPanel();
    });
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

  if (typeof window.loadCalidadResumenGeneral === "function") {
    switchTab("resumen");
  } else {
    switchTab("reglas");
    _reglasInitialized = true;
    refreshCalidadDashboard();
  }
});
