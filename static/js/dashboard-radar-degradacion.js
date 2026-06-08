let selectedDays = 14;
let lastPayload = null;
let rawItems = [];
let allItems = [];
let currentPage = 0;
let pageSize = 10;
const PAGER_SHOW_ABOVE = 10;
const RADAR_FETCH_LIMIT = 10000;
const _RADAR_STATE_KEY = "radarDegradacionStateV1";
const _RADAR_STATE_MAX_AGE_MS = 30 * 60 * 1000;
const _RADAR_ACT_LINK_ATTRS = ' target="_blank" rel="noopener noreferrer"';
const _radarStateStore = window.createNocPageStateStore
  ? window.createNocPageStateStore(_RADAR_STATE_KEY, { debounceMs: 120 })
  : null;
let _restoringRadarState = false;

const TIMELINE_ESTADO_LABELS = {
  G: "Verde",
  A: "Amarillo",
  R: "Rojo",
  N: "Sin dato",
};

const TIMELINE_ESTADO_CLASS = {
  G: "radar-tl--verde",
  A: "radar-tl--amarillo",
  R: "radar-tl--rojo",
  N: "radar-tl--nodata",
};

const SENAL_LABELS = {
  degradacion_sostenida: "Degradación sostenida",
  delta_rx: "Caída de Rx (delta)",
  semaforo_amarillo: "Alto % amarillo/rojo",
  mas_onts_amarillas: "Más ONTs en amarillo",
  onts_down: "ONTs sin lectura",
  ultima_rx_critica: "Última Rx crítica",
  evento_transitorio: "Pico transitorio intradía",
  recuperacion: "Recuperación al cierre del día",
};

const SENAL_SHORT = {
  degradacion_sostenida: "Sostenida",
  delta_rx: "Δ Rx",
  semaforo_amarillo: "% A/R",
  mas_onts_amarillas: "+Amar",
  onts_down: "Down",
  ultima_rx_critica: "Rx crit.",
  evento_transitorio: "Trans.",
  recuperacion: "Recup.",
};

const SENAL_CLASS = {
  degradacion_sostenida: "radar-senal-tag--warn",
  delta_rx: "radar-senal-tag--warn",
  semaforo_amarillo: "radar-senal-tag--warn",
  mas_onts_amarillas: "radar-senal-tag--warn",
  onts_down: "radar-senal-tag--danger",
  ultima_rx_critica: "radar-senal-tag--danger",
  evento_transitorio: "radar-senal-tag--info",
  recuperacion: "radar-senal-tag--ok",
};

function _radarToast(msg, opts) {
  if (!window.NocToast) return;
  const options = Object.assign({ durationMs: 2200, create: true, id: "radar-toast" }, opts || {});
  window.NocToast.show("radar-toast", msg, options);
}

function _esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _rxClass(rx) {
  if (rx === null || rx === undefined || rx === "") return "";
  const v = Number(rx);
  if (!Number.isFinite(v)) return "";
  if (v < -27) return "radar-rx--rojo";
  if (v <= -25) return "radar-rx--amarillo";
  return "radar-rx--verde";
}

function _formatSlope(v, compact) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  if (compact) return sign + n.toFixed(2);
  return sign + n.toFixed(3) + " dB/d";
}

function _formatDelta(v, compact) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  if (compact) return sign + n.toFixed(1);
  return sign + n.toFixed(1) + " dB";
}

function _trendClass(value, kind) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  if (kind === "slope") {
    if (n < -0.02) return "radar-trend--bad";
    if (n > 0.02) return "radar-trend--good";
    return "radar-trend--flat";
  }
  if (n < -1.0) return "radar-trend--bad";
  if (n > 0.5) return "radar-trend--good";
  return "radar-trend--flat";
}

function _totalPages() {
  return allItems.length ? Math.ceil(allItems.length / pageSize) : 0;
}

function _pageItems() {
  const start = currentPage * pageSize;
  return allItems.slice(start, start + pageSize);
}

function _syncPagerVisibility() {
  const pager = document.getElementById("radar-pager");
  if (!pager) return;
  pager.hidden = allItems.length <= PAGER_SHOW_ABOVE;
}

function _updatePagerUi() {
  _syncPagerVisibility();
  const tp = _totalPages();
  const info = document.getElementById("radar-page-info");
  if (info) {
    info.textContent =
      tp === 0 ? "0 resultados" : "Página " + (currentPage + 1) + " de " + tp;
  }
  const prev = document.getElementById("radar-page-prev");
  const next = document.getElementById("radar-page-next");
  if (prev) prev.disabled = currentPage <= 0;
  if (next) next.disabled = currentPage >= tp - 1;
}

function _updateVisibleCount() {
  const el = document.getElementById("visible-count");
  if (!el) return;
  const total = allItems.length;
  if (!total) {
    el.textContent = "0";
    return;
  }
  const start = currentPage * pageSize + 1;
  const end = Math.min(total, (currentPage + 1) * pageSize);
  el.textContent = start === end ? String(start) + "/" + total : String(start) + "–" + end + "/" + total;
}

function _setPage(page, opts) {
  opts = opts || {};
  const tp = _totalPages();
  if (!tp && !opts.force) return;
  const next = Math.max(0, Math.min(page, Math.max(0, tp - 1)));
  if (next === currentPage && !opts.force) return;
  currentPage = next;
  _renderTablePage();
  if (!opts.skipSave) _saveRadarStateSoon();
}

function _setLoading(on) {
  const loading = document.getElementById("radar-loading");
  const table = document.getElementById("radar-table");
  const empty = document.getElementById("radar-empty");
  const pager = document.getElementById("radar-pager");
  const btn = document.getElementById("btn-search");
  if (loading) loading.hidden = !on;
  if (btn) {
    btn.disabled = on;
    btn.setAttribute("aria-busy", on ? "true" : "false");
  }
  if (on) {
    if (table) table.classList.add("is-hidden");
    if (empty) empty.hidden = true;
    if (pager) pager.hidden = true;
  }
}

function _updateKpis(payload) {
  const tot = payload.totales || {};
  document.getElementById("kpi-tendencia").textContent = String(tot.RAMAS_CON_TENDENCIA ?? "—");
  document.getElementById("kpi-critico").textContent = String(tot.CRITICO ?? "—");
  document.getElementById("kpi-atencion").textContent = String(tot.ATENCION ?? "—");
  document.getElementById("kpi-sin-datos").textContent = String(tot.RAMAS_SIN_DATOS ?? "—");
  const hint = document.getElementById("kpi-generated-hint");
  if (hint) {
    hint.textContent = payload.generated_at
      ? "actualizado " + payload.generated_at
      : "sin consulta";
  }
  document.getElementById("window-days").textContent = String(payload.days || selectedDays);
  document.getElementById("kpi-tendencia-hint").textContent =
    "de " + String(tot.RAMAS_INVENTARIO ?? "—") + " en inventario";
  const daysWin = String(payload.days || selectedDays);
  const tlHint = document.querySelector(".radar-th-timeline__hint");
  if (tlHint) tlHint.textContent = "ant. → hoy · " + daysWin + "d";
  const legendDir = document.querySelector(".radar-legend__dir");
  if (legendDir) {
    legendDir.textContent = daysWin + "d · 1 barra = 1 día · gris = sin muestra";
  }
  _updateVisibleCount();
}

function _populatePrincipalOptions(items) {
  const sel = document.getElementById("radar-principal");
  if (!sel || !items) return;
  const current = sel.value || "ALL";
  const seen = new Set();
  const opts = ['<option value="ALL">Todos los sitios</option>'];
  items.forEach(function (row) {
    const p = row.PRINCIPAL;
    if (!p || seen.has(p)) return;
    seen.add(p);
    opts.push('<option value="' + _esc(p) + '">' + _esc(p) + "</option>");
  });
  sel.innerHTML = opts.join("");
  if (current && (current === "ALL" || seen.has(current))) {
    sel.value = current;
  }
}

function _timelineTip(day) {
  const estado = String(day.e || day.estado || "N");
  const dia = String(day.d || day.dia || "");
  let tip = dia + ": " + (TIMELINE_ESTADO_LABELS[estado] || estado);
  const rx = day.r != null ? day.r : day.rx;
  if (rx != null) tip += " · " + rx + " dBm";
  if (day.t || day.transitorio) {
    const pico = day.p != null ? day.p : day.pico;
    tip += pico != null ? " · pico " + pico + " dBm (recuperó)" : " · transitorio";
  }
  return tip;
}

function _rowMetricsTip(row) {
  const parts = [];
  const sitio = row.PRINCIPAL;
  if (sitio) parts.push("Sitio: " + sitio);
  if (row.PCT_AMARILLO_ROJO != null) parts.push("% amar/rojo: " + row.PCT_AMARILLO_ROJO + "%");
  if (row.DIAS_CON_MUESTRA != null) parts.push("Días con muestra: " + row.DIAS_CON_MUESTRA);
  return parts.join(" · ");
}

function _pendCellTip(row) {
  const v = row.PENDIENTE_PEOR_RX;
  if (v === null || v === undefined || v === "") return "Pendiente peor Rx";
  return "Pendiente peor Rx: " + _formatSlope(v) + " · negativo = empeora";
}

function _deltaCellTip(row) {
  const v = row.DELTA_BASELINE_DB;
  if (v === null || v === undefined || v === "") return "Delta baseline (2ª mitad − 1ª mitad del período)";
  return "Delta baseline: " + _formatDelta(v) + " · negativo = empeoró en el período";
}

function _renderTrendCell(row) {
  const pendVal = row.PENDIENTE_PEOR_RX;
  const deltaVal = row.DELTA_BASELINE_DB;
  return (
    '<td class="radar-col-trend">' +
    '<span class="radar-trend-stack">' +
    '<span class="radar-trend-item ' +
    _trendClass(pendVal, "slope") +
    '" title="' +
    _esc(_pendCellTip(row)) +
    '">' +
    _esc(_formatSlope(pendVal, true)) +
    "</span>" +
    '<span class="radar-trend-item ' +
    _trendClass(deltaVal, "delta") +
    '" title="' +
    _esc(_deltaCellTip(row)) +
    '">' +
    _esc(_formatDelta(deltaVal, true)) +
    "</span>" +
    "</span></td>"
  );
}

function _rxCellTip(row) {
  const ultimaRx = row.ULTIMA_PEOR_RX != null ? row.ULTIMA_PEOR_RX : row.PEOR_RX;
  const picoRx = row.PEOR_RX_PICO;
  let tip = "Última Rx del día";
  if (ultimaRx != null) tip += ": " + ultimaRx + " dBm";
  if (
    picoRx != null &&
    ultimaRx != null &&
    Number(picoRx) < Number(ultimaRx) - 2
  ) {
    tip += " · Pico intradía: " + picoRx + " dBm";
  }
  return tip;
}

function _renderTimeline(timeline) {
  if (!timeline || !timeline.length) {
    return '<span class="muted">—</span>';
  }
  const windowDays = Number(selectedDays) || timeline.length;
  let density = "";
  if (windowDays > 18) density = " radar-timeline--ultra";
  else if (windowDays > 10) density = " radar-timeline--dense";
  const lastIdx = timeline.length - 1;
  const cells = timeline
    .map(function (day, idx) {
      const estado = String(day.e || day.estado || "N");
      const cls = TIMELINE_ESTADO_CLASS[estado] || "radar-tl--nodata";
      const trans = Boolean(day.t || day.transitorio);
      const ultimo = idx === lastIdx;
      return (
        '<span class="radar-tl-cell ' +
        cls +
        (trans ? " radar-tl-cell--transitorio" : "") +
        (ultimo ? " radar-tl-cell--ultimo" : "") +
        '" title="' +
        _esc(_timelineTip(day)) +
        '">' +
        (trans ? '<span class="radar-tl-trans-badge" aria-hidden="true"></span>' : "") +
        "</span>"
      );
    })
    .join("");
  return (
    '<span class="radar-timeline-wrap" title="Izquierda: más antiguo · derecha: más reciente">' +
    '<span class="radar-timeline' +
    density +
    '" aria-label="Trayectoria Rx por día (' +
    timeline.length +
    " días, ventana " +
    windowDays +
    'd)">' +
    cells +
    "</span></span>"
  );
}

function _renderSenales(senales) {
  if (!senales || !senales.length) return '<span class="muted">—</span>';
  const tip = senales
    .map(function (s) {
      return SENAL_LABELS[s] || s;
    })
    .join(" · ");
  return (
    '<span class="radar-senales" title="' +
    _esc(tip) +
    '">' +
    senales
      .map(function (s) {
        const short = SENAL_SHORT[s] || s;
        const cls = SENAL_CLASS[s] || "";
        return (
          '<span class="radar-senal-tag' +
          (cls ? " " + cls : "") +
          '" title="' +
          _esc(SENAL_LABELS[s] || s) +
          '">' +
          _esc(short) +
          "</span>"
        );
      })
      .join("") +
    "</span>"
  );
}

function _renderRowHtml(row) {
  const nivel = String(row.NIVEL || "ESTABLE").toLowerCase();
  const rama = String(row.RAMA || "");
  const histUrl =
    "/dashboard/potencias-historico?ratc=" +
    encodeURIComponent(rama) +
    "&days=" +
    encodeURIComponent(String(Math.min(selectedDays, 30) === 1 ? 7 : selectedDays));
  const consultaUrl = "/?q=" + encodeURIComponent(rama);
  const caminoUrl = "/dashboard/camino-optico?q=" + encodeURIComponent(rama);
  const ultimaRx = row.ULTIMA_PEOR_RX != null ? row.ULTIMA_PEOR_RX : row.PEOR_RX;
  const metricsTip = _rowMetricsTip(row);
  const ramaTip = row.PRINCIPAL ? String(row.PRINCIPAL) : "";
  return (
    '<tr class="radar-row radar-row--' +
    _esc(nivel) +
    '">' +
    '<td class="radar-col-nivel"><span class="radar-nivel radar-nivel--' +
    _esc(nivel) +
    '">' +
    _esc(row.NIVEL || "") +
    "</span></td>" +
    '<td class="radar-col-score"><span class="radar-score"' +
    (metricsTip ? ' title="' + _esc(metricsTip) + '"' : "") +
    ">" +
    _esc(row.SCORE ?? "—") +
    "</span></td>" +
    '<td class="mono radar-col-rama"' +
    (ramaTip ? ' title="' + _esc(ramaTip) + '"' : "") +
    ">" +
    '<span class="radar-rama-text">' +
    _esc(rama) +
    "</span></td>" +
    '<td class="mono radar-col-rx ' +
    _rxClass(ultimaRx) +
    '" title="' +
    _esc(_rxCellTip(row)) +
    '">' +
    (ultimaRx != null ? '<span class="radar-rx-val">' + _esc(ultimaRx) + "</span>" : "—") +
    "</td>" +
    _renderTrendCell(row) +
    '<td class="radar-col-timeline">' +
    _renderTimeline(row.TIMELINE) +
    "</td>" +
    '<td class="radar-col-senales">' +
    _renderSenales(row.SENALES) +
    "</td>" +
    '<td class="radar-col-actions"><span class="radar-actions radar-actions--compact">' +
    '<a class="radar-act" href="' +
    histUrl +
    '"' +
    _RADAR_ACT_LINK_ATTRS +
    ' title="Histórico Rx Postgres (nueva pestaña)">Hist</a>' +
    '<a class="radar-act" href="' +
    consultaUrl +
    '"' +
    _RADAR_ACT_LINK_ATTRS +
    ' title="Consulta Potencias (nueva pestaña)">Rx</a>' +
    '<a class="radar-act" href="' +
    caminoUrl +
    '"' +
    _RADAR_ACT_LINK_ATTRS +
    ' title="Camino óptico y mapa GIS (nueva pestaña)">Cam</a>' +
    "</span></td>" +
    "</tr>"
  );
}

function _renderTablePage() {
  const tbody = document.getElementById("radar-tbody");
  const table = document.getElementById("radar-table");
  const empty = document.getElementById("radar-empty");
  const exportBtn = document.getElementById("btn-export");
  const items = _pageItems();
  if (!tbody) return;

  if (!allItems.length) {
    tbody.innerHTML = "";
    if (table) table.classList.add("is-hidden");
    if (empty) {
      empty.hidden = false;
      const p = empty.querySelector("p");
      if (p) {
        p.textContent =
          (lastPayload && lastPayload.empty_message) ||
          "Sin ramas que coincidan con los filtros en la ventana seleccionada.";
      }
    }
    if (exportBtn) exportBtn.disabled = true;
    _updatePagerUi();
    _updateVisibleCount();
    return;
  }

  if (table) table.classList.remove("is-hidden");
  if (empty) empty.hidden = true;
  if (exportBtn) exportBtn.disabled = false;
  tbody.innerHTML = items.map(_renderRowHtml).join("");
  _updatePagerUi();
  _updateVisibleCount();
}

function _getFilterValues() {
  const q = (document.getElementById("radar-q") || {}).value || "";
  const principal = (document.getElementById("radar-principal") || {}).value || "ALL";
  const nivel = (document.getElementById("radar-nivel") || {}).value || "ALL";
  return {
    q: String(q).trim(),
    principal: String(principal).trim() || "ALL",
    nivel: String(nivel).trim().toUpperCase() || "ALL",
  };
}

function _filterItemsClient(items) {
  const filters = _getFilterValues();
  const qLower = filters.q.toLowerCase();
  return (items || []).filter(function (row) {
    if (filters.principal !== "ALL" && row.PRINCIPAL !== filters.principal) return false;
    if (filters.nivel !== "ALL" && row.NIVEL !== filters.nivel) return false;
    if (qLower) {
      const haystack = [row.RAMA, row.PRINCIPAL, row.REGION]
        .map(function (v) {
          return String(v || "");
        })
        .join(" ")
        .toLowerCase();
      if (haystack.indexOf(qLower) < 0) return false;
    }
    return true;
  });
}

function _applyClientFilters(opts) {
  opts = opts || {};
  if (opts.resetPage !== false) currentPage = 0;
  allItems = _filterItemsClient(rawItems);
  _renderTablePage();
  if (!opts.skipSave) _saveRadarStateSoon();
}

function _buildRadarDashboardStatePayload() {
  const filters = _getFilterValues();
  return {
    days: selectedDays,
    q: filters.q,
    principal: filters.principal,
    nivel: filters.nivel,
    currentPage: currentPage,
    pageSize: pageSize,
    scrollY: Math.max(0, Math.floor(window.scrollY || 0)),
    ts: Date.now(),
  };
}

function _saveRadarStateSoon() {
  if (_restoringRadarState || !_radarStateStore) return;
  _radarStateStore.saveSoon(_buildRadarDashboardStatePayload);
}

function _persistRadarDashboardState() {
  if (_restoringRadarState || !_radarStateStore) return;
  _radarStateStore.save(_buildRadarDashboardStatePayload);
}

function _readRadarDashboardState() {
  if (!_radarStateStore) return null;
  return _radarStateStore.read(function (parsed) {
    if (!parsed || typeof parsed !== "object") return null;
    const ts = Number(parsed.ts || 0);
    if (!Number.isFinite(ts) || Date.now() - ts > _RADAR_STATE_MAX_AGE_MS) return null;
    const days = Number(parsed.days);
    const allowedDays = [7, 14, 30];
    const page = Number(parsed.currentPage);
    const size = Number(parsed.pageSize);
    return {
      days: allowedDays.indexOf(days) >= 0 ? days : 14,
      q: typeof parsed.q === "string" ? parsed.q : "",
      principal: typeof parsed.principal === "string" ? parsed.principal : "ALL",
      nivel: typeof parsed.nivel === "string" ? parsed.nivel.toUpperCase() : "ALL",
      currentPage: Number.isFinite(page) && page >= 0 ? Math.floor(page) : 0,
      pageSize: Number.isFinite(size) && size > 0 ? Math.floor(size) : 10,
      scrollY: Number.isFinite(parsed.scrollY) ? Number(parsed.scrollY) : 0,
    };
  });
}

function _syncRangePickerUi(days) {
  const picker = document.getElementById("range-picker");
  if (!picker) return;
  picker.querySelectorAll("button[data-days]").forEach(function (btn) {
    btn.classList.toggle("is-active", Number(btn.getAttribute("data-days")) === days);
  });
}

function _applySavedFiltersToUi(state) {
  if (!state) return;
  const qInput = document.getElementById("radar-q");
  if (qInput) qInput.value = state.q || "";
  const nivelSel = document.getElementById("radar-nivel");
  if (nivelSel && state.nivel) nivelSel.value = state.nivel;
  const sizeSel = document.getElementById("radar-page-size");
  if (sizeSel && state.pageSize) {
    sizeSel.value = String(state.pageSize);
    pageSize = state.pageSize;
  }
  selectedDays = state.days || selectedDays;
  _syncRangePickerUi(selectedDays);
}

function _applyPrincipalFromState(principal) {
  const sel = document.getElementById("radar-principal");
  if (!sel || !principal || principal === "ALL") return;
  const has = Array.from(sel.options).some(function (opt) {
    return opt.value === principal;
  });
  if (has) sel.value = principal;
}

function _restoreRadarUiAfterData(state) {
  if (!state) return;
  _restoringRadarState = true;
  try {
    _applyPrincipalFromState(state.principal);
    _applyClientFilters({ resetPage: false, skipSave: true });
    _setPage(state.currentPage, { force: true, skipSave: true });
  } finally {
    _restoringRadarState = false;
  }
  if (_radarStateStore) _radarStateStore.restoreScroll(state.scrollY);
}

function _applyRadarData(payload, restoreState) {
  rawItems = payload.items || [];
  if (!restoreState) currentPage = 0;
  _populatePrincipalOptions(rawItems);
  _updateKpis(payload);
  if (restoreState) {
    _restoreRadarUiAfterData(restoreState);
    return;
  }
  _applyClientFilters({ resetPage: false, skipSave: true });
}

function _buildFetchParams() {
  const params = new URLSearchParams();
  params.set("days", String(selectedDays));
  params.set("limit", String(RADAR_FETCH_LIMIT));
  return params;
}

function _buildExportParams() {
  const filters = _getFilterValues();
  const params = _buildFetchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.principal !== "ALL") params.set("principal", filters.principal);
  if (filters.nivel !== "ALL") params.set("nivel", filters.nivel);
  return params;
}

async function fetchRadar(opts) {
  opts = opts || {};
  _setLoading(true);
  try {
    const params = _buildFetchParams();
    const resp = await fetch("/api/radar-degradacion?" + params.toString(), {
      headers: { Accept: "application/json" },
    });
    const payload = await resp.json();
    if (!resp.ok || !payload.ok) {
      throw new Error((payload && payload.error) || "Error consultando radar");
    }
    lastPayload = payload;
    _applyRadarData(payload, opts.restoreState || null);
    if (!opts.restoreState) _saveRadarStateSoon();
  } catch (err) {
    rawItems = [];
    allItems = [];
    currentPage = 0;
    const msg = String((err && err.message) || err || "Error consultando radar");
    _radarToast(msg, { durationMs: 4200 });
    const table = document.getElementById("radar-table");
    const empty = document.getElementById("radar-empty");
    if (table) table.classList.add("is-hidden");
    if (empty) {
      empty.hidden = false;
      const p = empty.querySelector("p");
      if (p) {
        p.textContent = "No se pudo calcular el ranking: " + msg;
      }
    }
    const tbody = document.getElementById("radar-tbody");
    if (tbody) tbody.innerHTML = "";
    const exportBtn = document.getElementById("btn-export");
    if (exportBtn) exportBtn.disabled = true;
    _updatePagerUi();
    _updateVisibleCount();
  } finally {
    _setLoading(false);
  }
}

function resetRadar() {
  const q = document.getElementById("radar-q");
  const principal = document.getElementById("radar-principal");
  const nivel = document.getElementById("radar-nivel");
  if (q) q.value = "";
  if (principal) principal.value = "ALL";
  if (nivel) nivel.value = "ALL";
  try {
    sessionStorage.removeItem(_RADAR_STATE_KEY);
  } catch (_err) {}
  if (rawItems.length) {
    _applyClientFilters();
    return;
  }
  fetchRadar();
}

function exportRadarCsv() {
  const params = _buildExportParams();
  window.location.href = "/dashboard/radar-degradacion/export.csv?" + params.toString();
}

function _bindRangePicker() {
  const picker = document.getElementById("range-picker");
  if (!picker) return;
  picker.querySelectorAll("button[data-days]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const days = Number(btn.getAttribute("data-days"));
      if (!Number.isFinite(days)) return;
      selectedDays = days;
      picker.querySelectorAll("button[data-days]").forEach(function (b) {
        b.classList.toggle("is-active", b === btn);
      });
      fetchRadar();
      _saveRadarStateSoon();
    });
  });
}

function _bindStatePersistence() {
  let scrollTimer = null;
  window.addEventListener(
    "scroll",
    function () {
      if (_restoringRadarState) return;
      if (scrollTimer) clearTimeout(scrollTimer);
      scrollTimer = setTimeout(_saveRadarStateSoon, 150);
    },
    { passive: true }
  );
  window.addEventListener("pagehide", _persistRadarDashboardState);
}

function _bindPager() {
  const prev = document.getElementById("radar-page-prev");
  const next = document.getElementById("radar-page-next");
  const sizeSel = document.getElementById("radar-page-size");
  if (prev) {
    prev.addEventListener("click", function () {
      _setPage(currentPage - 1);
    });
  }
  if (next) {
    next.addEventListener("click", function () {
      _setPage(currentPage + 1);
    });
  }
  if (sizeSel) {
    sizeSel.addEventListener("change", function () {
      pageSize = parseInt(sizeSel.value, 10) || 10;
      currentPage = 0;
      _renderTablePage();
      _saveRadarStateSoon();
    });
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const savedState = _readRadarDashboardState();
  if (savedState) _applySavedFiltersToUi(savedState);

  _bindRangePicker();
  _bindPager();
  _bindStatePersistence();
  const exportBtn = document.getElementById("btn-export");
  if (exportBtn) exportBtn.addEventListener("click", exportRadarCsv);
  const qInput = document.getElementById("radar-q");
  if (qInput) {
    let timer = null;
    qInput.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        _applyClientFilters();
      }, 200);
    });
  }
  const principalSel = document.getElementById("radar-principal");
  const nivelSel = document.getElementById("radar-nivel");
  if (principalSel) principalSel.addEventListener("change", _applyClientFilters);
  if (nivelSel) nivelSel.addEventListener("change", _applyClientFilters);
  fetchRadar(savedState ? { restoreState: savedState } : null);
});

window.addEventListener("pageshow", function (e) {
  if (!e.persisted || !rawItems.length) return;
  const saved = _readRadarDashboardState();
  if (saved && _radarStateStore) _radarStateStore.restoreScroll(saved.scrollY);
});
