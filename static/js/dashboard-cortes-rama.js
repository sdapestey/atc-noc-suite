let lastPayload = null;
let allItems = [];
let currentPage = 0;
let pageSize = 10;
const PAGER_SHOW_ABOVE = 10;
const _EVENTO_COLLAPSE_MIN = 2;
const _HORA_COLLAPSE_MIN = 1;
const _SITIO_COLLAPSE_MIN = 12;
const _eventoExpandedKeys = new Set();
const _eventoCollapsedKeys = new Set();
const _sitioExpandedKeys = new Set();
const _sitioCollapsedKeys = new Set();
const _horaExpandedKeys = new Set();
const _horaCollapsedKeys = new Set();

const _CAUSA_BADGE_CLASS = {
  DYING_GASP: "cortes-badge--dying",
  LOSI_LOBI: "cortes-badge--losi",
  OTRO: "cortes-badge--otro",
};

const _CAUSA_SHORT = {
  DYING_GASP: "DG",
  LOSI_LOBI: "LOSi",
  OTRO: "?",
};

const _IMPACTO_BADGE_CLASS = {
  EMERGENCIA: "cortes-badge--emergencia",
  URGENTE: "cortes-badge--urgente",
  MODERADO: "cortes-badge--moderado",
};

const _IMPACTO_SHORT = {
  EMERGENCIA: "EMG",
  URGENTE: "URG",
  MODERADO: "MOD",
};

const _ESTADO_BADGE_CLASS = {
  Active: "cortes-badge--active",
  active: "cortes-badge--active",
  Cleared: "cortes-badge--cleared",
  cleared: "cortes-badge--cleared",
};

const _TZ_ART = "America/Argentina/Buenos_Aires";

const _SEEN_KEY = "cortesRamaSeenPonKeysV1";
const _STATE_KEY = "cortesRamaStateV1";
const _REFRESH_KEY = "cortesRamaRefreshMsV1";
const _STATE_MAX_AGE_MS = 30 * 60 * 1000;
let _refreshTimerId = null;
let _hintFreshTimerId = null;
let _fetchInFlight = false;
let _fetchPending = null;
let _cortesPageReady = false;
let _showClearedCol = false;
let _cortesFechaPicker = null;
const _stateStore = window.createNocPageStateStore
  ? window.createNocPageStateStore(_STATE_KEY, { debounceMs: 120 })
  : null;
let _restoringState = false;
let seenPonKeys = _loadSeenPonKeys();

function _esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _cortesToast(msg, opts) {
  if (!window.NocToast) return;
  const options = Object.assign({ durationMs: 2200, create: true, id: "cortes-toast" }, opts || {});
  window.NocToast.show("cortes-toast", msg, options);
}

function _loadSeenPonKeys() {
  try {
    const raw = localStorage.getItem(_SEEN_KEY);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch (_e) {
    return new Set();
  }
}

function _saveSeenPonKeys() {
  try {
    localStorage.setItem(_SEEN_KEY, JSON.stringify([...seenPonKeys]));
  } catch (_e) {
    /* ignore */
  }
}

function _isConsultaHoy() {
  const dia = _cortesFechaIso();
  return !dia || dia === _todayArtIso();
}

function _nuevosTrackingEnabled() {
  const estado = _getCortesEstado();
  if (estado === "cleared") return false;
  if (!_isConsultaHoy()) return false;
  return true;
}

function _isNuevo(row) {
  if (!_nuevosTrackingEnabled()) return false;
  const pk = String(row?.pon_key || "").trim();
  return pk && !seenPonKeys.has(pk);
}

function _markAllSeen(items) {
  (items || []).forEach((row) => {
    const pk = String(row.pon_key || "").trim();
    if (pk) seenPonKeys.add(pk);
  });
  _saveSeenPonKeys();
}

function _formatRaised(iso) {
  const s = String(iso || "").trim();
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const parts = new Intl.DateTimeFormat("es-AR", {
    timeZone: _TZ_ART,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const pick = (type) => parts.find((p) => p.type === type)?.value || "";
  return pick("day") + "/" + pick("month") + " " + pick("hour") + ":" + pick("minute");
}

function _formatVentanaArt(ventana) {
  const s = String(ventana || "").trim();
  if (!s) return "—";
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (m) {
    return (
      String(parseInt(m[3], 10)) +
      "/" +
      String(parseInt(m[2], 10)) +
      " " +
      m[4] +
      ":" +
      m[5]
    );
  }
  return s;
}

function _formatRaisedHourBucket(iso) {
  const s = String(iso || "").trim();
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const parts = new Intl.DateTimeFormat("es-AR", {
    timeZone: _TZ_ART,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const pick = (type) => parts.find((p) => p.type === type)?.value || "";
  return pick("day") + "/" + pick("month") + " " + pick("hour") + ":00";
}

function _siteKey(row) {
  return String(row?.principal || row?.olt || "—").trim() || "—";
}

function _pruneHierarchyCollapseKeys(blocks, mode) {
  if (mode === "cleared_hierarchy") {
    const validSitio = new Set((blocks || []).map((b) => b.key).filter(Boolean));
    const validHora = new Set();
    (blocks || []).forEach((site) => {
      (site.hours || []).forEach((hour) => {
        if (hour.key) validHora.add(hour.key);
      });
    });
    [..._sitioExpandedKeys, ..._sitioCollapsedKeys].forEach((key) => {
      if (!validSitio.has(key)) {
        _sitioExpandedKeys.delete(key);
        _sitioCollapsedKeys.delete(key);
      }
    });
    [..._horaExpandedKeys, ..._horaCollapsedKeys].forEach((key) => {
      if (!validHora.has(key)) {
        _horaExpandedKeys.delete(key);
        _horaCollapsedKeys.delete(key);
      }
    });
    return;
  }
  _pruneEventoCollapseKeys(blocks);
}

function _pruneEventoCollapseKeys(blocks) {
  const valid = new Set(
    (blocks || []).filter((b) => b.type === "evento" && b.key).map((b) => b.key)
  );
  [..._eventoExpandedKeys].forEach((key) => {
    if (!valid.has(key)) _eventoExpandedKeys.delete(key);
  });
  [..._eventoCollapsedKeys].forEach((key) => {
    if (!valid.has(key)) _eventoCollapsedKeys.delete(key);
  });
}

function _isEventoBlockExpanded(block) {
  const key = block && block.key;
  if (!key) return true;
  if (_eventoExpandedKeys.has(key)) return true;
  if (_eventoCollapsedKeys.has(key)) return false;
  return (block.items || []).length < _EVENTO_COLLAPSE_MIN;
}

function _toggleEventoBlock(key) {
  const blocks = _displayRowsForMode().blocks;
  const block = blocks.find((b) => b.type === "evento" && b.key === key);
  if (!block) return;
  if (_isEventoBlockExpanded(block)) {
    _eventoExpandedKeys.delete(key);
    _eventoCollapsedKeys.add(key);
  } else {
    _eventoCollapsedKeys.delete(key);
    _eventoExpandedKeys.add(key);
  }
  _renderTablePage();
}

function _isSitioBlockExpanded(block) {
  const key = block && block.key;
  if (!key) return true;
  if (_sitioExpandedKeys.has(key)) return true;
  if (_sitioCollapsedKeys.has(key)) return false;
  return (block.itemCount || 0) < _SITIO_COLLAPSE_MIN;
}

function _toggleSitioBlock(key) {
  const blocks = _displayRowsForMode().blocks;
  const block = blocks.find((b) => b.type === "sitio" && b.key === key);
  if (!block) return;
  if (_isSitioBlockExpanded(block)) {
    _sitioExpandedKeys.delete(key);
    _sitioCollapsedKeys.add(key);
  } else {
    _sitioCollapsedKeys.delete(key);
    _sitioExpandedKeys.add(key);
  }
  _renderTablePage();
}

function _isHourBlockExpanded(block) {
  const key = block && block.key;
  if (!key) return false;
  if (_horaExpandedKeys.has(key)) return true;
  if (_horaCollapsedKeys.has(key)) return false;
  return false;
}

function _toggleHourBlock(key) {
  const mode = _displayRowsForMode().mode;
  const blocks = _displayRowsForMode().blocks;
  let block = null;
  if (mode === "cleared_hierarchy") {
    blocks.forEach((site) => {
      (site.hours || []).forEach((hour) => {
        if (hour.key === key) block = hour;
      });
    });
  }
  if (!block) return;
  if (_isHourBlockExpanded(block)) {
    _horaExpandedKeys.delete(key);
    _horaCollapsedKeys.add(key);
  } else {
    _horaCollapsedKeys.delete(key);
    _horaExpandedKeys.add(key);
  }
  _renderTablePage();
}

function _todayArtIso() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: _TZ_ART,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const d = parts.find((p) => p.type === "day")?.value;
  return y && m && d ? y + "-" + m + "-" + d : "";
}

function _cortesFechaIso() {
  const NFP = window.NocEstadisticasFlatpickr;
  if (NFP && _cortesFechaPicker) {
    return (NFP.getIsoValue(_cortesFechaPicker) || "").trim();
  }
  return (document.getElementById("cortes-fecha-dia")?.value || "").trim();
}

function _syncCortesFechaDisplay() {
  const fp = _cortesFechaPicker;
  const input = document.getElementById("cortes-fecha-dia");
  const iso = (fp?.input?.value || input?.value || "").trim();
  const visible = fp?.altInput;
  if (!visible) return;
  if (!iso) {
    visible.value = "Todas las fechas";
    return;
  }
  if (iso === _todayArtIso()) {
    visible.value = "Hoy";
    return;
  }
  if (fp?.selectedDates?.length) {
    visible.value = fp.formatDate(fp.selectedDates[0], fp.config.altFormat);
  }
}

function _setCortesFechaAll() {
  if (_cortesFechaPicker) _cortesFechaPicker.clear();
  const input = document.getElementById("cortes-fecha-dia");
  if (input) input.value = "";
  _syncCortesFechaDisplay();
}

function _setCortesFechaHoy() {
  _setCortesFechaIso(_todayArtIso());
}

function _enhanceCortesFechaPicker(fp) {
  const cal = fp?.calendarContainer;
  if (!cal || cal.dataset.cortesFooter === "1") return;
  cal.dataset.cortesFooter = "1";
  const footer = document.createElement("div");
  footer.className = "noc-fp-footer";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "noc-fp-footer-btn";
  btn.textContent = "Todas las fechas";
  btn.addEventListener("click", (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
    _setCortesFechaAll();
    fp.close();
    if (_restoringState) return;
    currentPage = 0;
    _saveStateSoon();
    fetchCortes({ fresh: true });
  });
  footer.appendChild(btn);
  cal.appendChild(footer);
}

function _buildFechaParam() {
  return _cortesFechaIso();
}

function _initCortesFechaPicker() {
  const input = document.getElementById("cortes-fecha-dia");
  const NFP = window.NocEstadisticasFlatpickr;
  if (!input || !NFP || _cortesFechaPicker) {
    return;
  }
  const initial = (input.value || "").trim();
  _cortesFechaPicker = NFP.create(input, {
    defaultDate: initial || undefined,
    onChange() {
      _syncCortesFechaDisplay();
      if (_restoringState) return;
      currentPage = 0;
      if (!_restoringState) _saveStateSoon();
      fetchCortes({ fresh: true });
    },
    onClose() {
      _syncCortesFechaDisplay();
    },
  });
  if (_cortesFechaPicker) {
    _enhanceCortesFechaPicker(_cortesFechaPicker);
    _syncCortesFechaDisplay();
  }
}

function _setCortesFechaIso(iso) {
  const val = String(iso || "").trim();
  if (!val) {
    _setCortesFechaAll();
    return;
  }
  if (_cortesFechaPicker) {
    _cortesFechaPicker.setDate(val, false);
  } else {
    const input = document.getElementById("cortes-fecha-dia");
    if (input) input.value = val;
  }
  _syncCortesFechaDisplay();
}

function _loadRefreshMs() {
  try {
    const raw = localStorage.getItem(_REFRESH_KEY);
    const ms = parseInt(raw || "0", 10);
    return Number.isFinite(ms) && ms > 0 ? ms : 0;
  } catch (_e) {
    return 0;
  }
}

function _saveRefreshMs(ms) {
  try {
    localStorage.setItem(_REFRESH_KEY, String(ms || 0));
  } catch (_e) {
    /* ignore */
  }
}

function _getRefreshMs() {
  const v = parseInt(document.getElementById("cortes-refresh")?.value || "0", 10);
  return Number.isFinite(v) && v > 0 ? v : 0;
}

function _setRefreshBusy(on) {
  const sel = document.getElementById("cortes-refresh");
  if (sel) sel.classList.toggle("cortes-select--polling", !!on);
  const hint = document.getElementById("kpi-generated-hint");
  if (!hint) return;
  if (on) {
    hint.classList.add("cortes-hint--polling");
    hint.classList.remove("cortes-hint--fresh");
  } else {
    hint.classList.remove("cortes-hint--polling");
  }
}

function _flashRefreshHint() {
  const hint = document.getElementById("kpi-generated-hint");
  if (!hint) return;
  hint.classList.add("cortes-hint--fresh");
  if (_hintFreshTimerId) clearTimeout(_hintFreshTimerId);
  _hintFreshTimerId = window.setTimeout(() => {
    hint.classList.remove("cortes-hint--fresh");
    _hintFreshTimerId = null;
  }, 1500);
}

function _stopAutoRefresh() {
  if (_refreshTimerId) {
    clearTimeout(_refreshTimerId);
    _refreshTimerId = null;
  }
}

function _scheduleAutoRefreshTick() {
  _stopAutoRefresh();
  const ms = _getRefreshMs();
  _saveRefreshMs(ms);
  if (!ms) return;
  _refreshTimerId = window.setTimeout(() => {
    _refreshTimerId = null;
    if (!_getRefreshMs()) return;
    if (document.hidden) {
      _scheduleAutoRefreshTick();
      return;
    }
    fetchCortes({ silent: true, preservePage: true, fresh: true }).finally(() => {
      if (_getRefreshMs()) _scheduleAutoRefreshTick();
    });
  }, ms);
}

function _applyAutoRefresh() {
  _stopAutoRefresh();
  const ms = _getRefreshMs();
  _saveRefreshMs(ms);
  if (!ms) return;
  _scheduleAutoRefreshTick();
}

function _getCortesEstado() {
  return document.getElementById("cortes-estado")?.value || "activas";
}

function _syncToolbarContext() {
  const cleared = _getCortesEstado() === "cleared";
  const fechaWrap = document.getElementById("cortes-fecha-wrap");
  const fechaInput = document.getElementById("cortes-fecha-dia");
  if (fechaWrap) fechaWrap.classList.toggle("cortes-fecha-wrap--cleared", cleared);
  if (fechaInput) {
    fechaInput.placeholder = cleared ? "Elegí un día" : "Hoy";
    fechaInput.title = cleared
      ? "Recomendado en Cleared: filtrar por día de raised (hora Argentina). Sin fecha se listan todos los cleared devueltos por Altiplano."
      : "Por defecto hoy (hora Argentina). Abrí el calendario para otro día o «Todas las fechas».";
  }
  _syncCortesFechaDisplay();
}

const _IMPACTO_RANK = { EMERGENCIA: 3, URGENTE: 2, MODERADO: 1 };

function _syncTableLayout() {
  _showClearedCol = true;
  const table = document.getElementById("cortes-table");
  if (!table) return;
  table.classList.add("cortes-table--show-cleared");
  table.classList.remove("cortes-table--show-estado", "cortes-table--cleared-grouped");
  const locTh = document.getElementById("cortes-th-loc");
  if (locTh) locTh.textContent = "OLT / LT / PON";
}

function _emptyCortesMessage() {
  const estado = _getCortesEstado();
  if (estado === "cleared") return "Sin cortes cleared que coincidan con los filtros.";
  return "Sin cortes activos que coincidan con los filtros.";
}

function _buildFetchParams(opts) {
  opts = opts || {};
  const params = new URLSearchParams();
  const estado = _getCortesEstado();
  const causa = document.getElementById("cortes-causa")?.value || "ALL";
  const principal = document.getElementById("cortes-principal")?.value || "ALL";
  const vno = document.getElementById("cortes-vno")?.value || "ALL";
  const q = (document.getElementById("cortes-q")?.value || "").trim();
  const sort = document.getElementById("cortes-sort")?.value || "reciente";
  const fecha = _buildFechaParam();
  if (causa && causa !== "ALL") params.set("causa", causa);
  if (principal && principal !== "ALL") params.set("principal", principal);
  if (vno && vno !== "ALL") params.set("vno", vno);
  if (q) params.set("q", q);
  if (sort && sort !== "reciente") params.set("sort", sort);
  if (fecha) params.set("fecha", fecha);
  if (estado && estado !== "activas") params.set("estado", estado);
  if (opts.fresh) params.set("fresh", "1");
  params.set("limit", "500");
  return params;
}

function _populateSelect(sel, values, allLabel) {
  if (!sel) return;
  const current = sel.value || "ALL";
  sel.innerHTML = '<option value="ALL">' + _esc(allLabel) + "</option>";
  (values || []).forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
  if ([...sel.options].some((o) => o.value === current)) sel.value = current;
}

function _countNuevos(items) {
  return (items || []).filter((row) => _isNuevo(row)).length;
}

function _updateKpis(payload, displayItems) {
  const t = payload?.totales || {};
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val ?? "—";
  };
  set("kpi-total", t.TOTAL ?? 0);
  set("kpi-losi", t.LOSI_LOBI ?? 0);
  set("kpi-dying", t.DYING_GASP ?? 0);
  set("kpi-clientes", t.CLIENTES_AFECTADOS ?? 0);
  const nuevosEnabled = _nuevosTrackingEnabled();
  set("kpi-nuevos", nuevosEnabled ? _countNuevos(payload?.items || []) : "—");
  const marcarVistos = document.getElementById("btn-cortes-marcar-vistos");
  if (marcarVistos) marcarVistos.hidden = !nuevosEnabled;
  const impactoHint = document.getElementById("kpi-impacto-hint");
  if (impactoHint) {
    const emg = t.EMERGENCIA ?? 0;
    const urg = t.URGENTE ?? 0;
    const mod = t.MODERADO ?? 0;
    impactoHint.textContent =
      emg || urg ? emg + " emergencia · " + urg + " urgente" : mod + " moderado · inventario";
  }
  const hint = document.getElementById("kpi-generated-hint");
  if (hint) {
    hint.textContent = payload?.generated_at ? "actualizado " + payload.generated_at : "sin consulta";
    if (payload?.generated_at) _flashRefreshHint();
  }
  const ramasEl = document.getElementById("cortes-ramas-count");
  if (ramasEl) ramasEl.textContent = String(t.RAMAS_IMPACTADAS ?? 0);
  const sinInv = document.getElementById("kpi-sin-inv");
  if (sinInv) {
    const n = t.SIN_INVENTARIO ?? 0;
    sinInv.hidden = !n;
    if (n) sinInv.textContent = "· " + n + " sin mapeo inventario";
  }
  _renderEventosMasivos(payload?.eventos_masivos || []);
}

const _EVENTO_TIPO_ORDER = ["fibra", "luz", "otro"];

const _EVENTO_TIPO_META = {
  fibra: {
    label: "Corte de fibra",
    badgeCls: "cortes-badge--losi",
    badgeTxt: "LOSi",
    sectionCls: "cortes-eventos-section--fibra",
  },
  luz: {
    label: "Corte de luz",
    badgeCls: "cortes-badge--dying",
    badgeTxt: "DG",
    sectionCls: "cortes-eventos-section--luz",
  },
  otro: {
    label: "Otro",
    badgeCls: "cortes-badge--otro",
    badgeTxt: "?",
    sectionCls: "cortes-eventos-section--otro",
  },
};

function _eventoTipo(ev) {
  if (ev?.tipo) return ev.tipo;
  const causa = String(ev?.causa || "").toUpperCase();
  if (causa === "DYING_GASP") return "luz";
  if (causa === "LOSI_LOBI") return "fibra";
  return "otro";
}

function _buildOltUrlFromPonKeys(keys) {
  const valid = (keys || []).map((k) => String(k || "").trim()).filter(Boolean);
  if (!valid.length) return "/dashboard/olt";
  return "/dashboard/olt?select_pon=" + encodeURIComponent(valid.join(","));
}

function _renderEventoMasivoCard(ev, idx) {
  const imp = ev.impacto || "MODERADO";
  const badgeCls = _IMPACTO_BADGE_CLASS[imp] || "cortes-badge--moderado";
  const badgeTxt = _IMPACTO_SHORT[imp] || imp;
  const sitio = ev.principal || ev.olt || "";
  const olts = Array.isArray(ev.olts) ? ev.olts : ev.olt ? [ev.olt] : [];
  const oltHint =
    olts.length > 1
      ? "<span class=\"muted\">" + _esc(olts.length) + " OLT · </span>"
      : "";
  const showReporte = imp === "EMERGENCIA" || imp === "URGENTE";
  const ponKeys = (ev && (ev.pon_keys || ev.pons)) || [];
  let actionBtns = "";
  if (showReporte) {
    const oltUrl = _buildOltUrlFromPonKeys(ponKeys);
    actionBtns =
      '<span class="cortes-evento-card__actions">' +
      '<a class="btn btn-sm btn-ghost cortes-evento-olt-btn" href="' +
      _esc(oltUrl) +
      '" target="_blank" rel="noopener noreferrer" title="Abrir OLT/LT con todos los PON del evento seleccionados">OLT</a>' +
      '<button type="button" class="btn btn-sm btn-ghost cortes-evento-reporte-btn" title="Exportar clientes IN SERVICE (PON, RAMA, CTO, AID)">Reporte</button>' +
      "</span>";
  }
  return (
    '<div class="cortes-evento-card cortes-evento-card--' +
    imp.toLowerCase() +
    '" data-evento-idx="' +
    String(idx) +
    '">' +
    '<span class="cortes-badge ' +
    badgeCls +
    '">' +
    _esc(badgeTxt) +
    "</span>" +
    '<span class="cortes-evento-card__body">' +
    (sitio ? "<strong>" + _esc(sitio) + "</strong> · " : "") +
    oltHint +
    "<strong>" +
    _esc(ev.cortes) +
    " PON</strong> · <span class=\"mono\">" +
    _esc(_formatVentanaArt(ev.ventana || ev.minute)) +
    "</span> · <strong>" +
    _esc(ev.clientes) +
    "</strong> clientes" +
    "</span>" +
    actionBtns +
    "</div>"
  );
}

function _renderEventosMasivos(eventos) {
  const banner = document.getElementById("cortes-eventos-banner");
  const list = document.getElementById("cortes-eventos-list");
  if (!banner || !list) return;
  const rows = (eventos || []).filter((ev) => {
    const imp = String(ev.impacto || "").toUpperCase();
    return imp === "EMERGENCIA" || imp === "URGENTE";
  });
  if (!rows.length) {
    banner.hidden = true;
    list.innerHTML = "";
    list._eventosData = [];
    return;
  }
  banner.hidden = false;
  list._eventosData = rows.slice();
  let globalIdx = 0;
  const byTipo = {};
  rows.forEach((ev) => {
    const tipo = _eventoTipo(ev);
    if (!byTipo[tipo]) byTipo[tipo] = [];
    byTipo[tipo].push(ev);
  });
  let html = "";
  _EVENTO_TIPO_ORDER.forEach((tipo) => {
    const sectionRows = byTipo[tipo];
    if (!sectionRows?.length) return;
    const meta = _EVENTO_TIPO_META[tipo] || _EVENTO_TIPO_META.otro;
    html +=
      '<section class="cortes-eventos-section ' +
      (meta.sectionCls || "") +
      '" aria-label="' +
      _esc(meta.label) +
      '">' +
      '<div class="cortes-eventos-section__head">' +
      '<span class="cortes-badge ' +
      meta.badgeCls +
      '">' +
      _esc(meta.badgeTxt) +
      "</span>" +
      "<strong>" +
      _esc(meta.label) +
      "</strong>" +
      '<span class="muted">' +
      sectionRows.length +
      " evento" +
      (sectionRows.length === 1 ? "" : "s") +
      "</span>" +
      "</div>" +
      '<div class="cortes-eventos-section__list">' +
      sectionRows.map((ev) => _renderEventoMasivoCard(ev, globalIdx++)).join("") +
      "</div></section>";
  });
  list.innerHTML = html;
}

function _impactoBadgeHtml(imp, opts) {
  opts = opts || {};
  if (opts.evento) {
    return (
      '<span class="cortes-badge cortes-badge--evento-masivo" title="' +
      _esc(opts.title || "Evento masivo") +
      '">Σ</span>'
    );
  }
  const badgeCls = _IMPACTO_BADGE_CLASS[imp] || "cortes-badge--moderado";
  const badgeTxt = _IMPACTO_SHORT[imp] || opts.label || imp;
  return (
    '<span class="cortes-badge ' +
    badgeCls +
    '" title="' +
    _esc(opts.title || imp) +
    '">' +
    _esc(badgeTxt) +
    "</span>"
  );
}

function _renderImpactoBadge(row, opts) {
  opts = opts || {};
  if (!row.evento_simultaneo || opts.groupChild) {
    return "";
  }
  const imp = row.impacto || "MODERADO";
  const impPon = row.impacto_pon || imp;
  let title =
    "Evento masivo: " +
    (row.evento_cortes || 2) +
    " PON · " +
    (row.evento_clientes ?? 0) +
    " clientes (" +
    String(row.impacto_label || imp) +
    ")";
  if (impPon !== imp) {
    title +=
      " · este PON: " +
      (row.ont_total ?? 0) +
      " (" +
      (row.impacto_pon_label || impPon) +
      ")";
  }
  return _impactoBadgeHtml(imp, {
    label: row.impacto_label,
    title: title,
    evento: true,
  });
}

function _groupImpactMeta(g) {
  const items = g?.items || [];
  let impacto = "MODERADO";
  let eventoRow = null;
  items.forEach((row) => {
    const imp = row.impacto || "MODERADO";
    if ((_IMPACTO_RANK[imp] || 0) > (_IMPACTO_RANK[impacto] || 0)) impacto = imp;
    if (row.evento_simultaneo) eventoRow = row;
  });
  return { impacto, eventoRow };
}

function _renderGroupImpactBadge(g) {
  const meta = _groupImpactMeta(g);
  if (!meta.eventoRow) return "";
  const imp = meta.impacto || "MODERADO";
  const title =
    "Evento masivo: " +
    (meta.eventoRow.evento_cortes || g.cortes) +
    " PON · " +
    (meta.eventoRow.evento_clientes ?? g.ont_total) +
    " clientes (" +
    String(meta.eventoRow.impacto_label || imp) +
    ")";
  return _impactoBadgeHtml(imp, {
    label: meta.eventoRow.impacto_label,
    title: title,
    evento: true,
  });
}

function _groupEarliestRaised(items) {
  let best = null;
  let iso = "";
  (items || []).forEach((row) => {
    const ts = Date.parse(String(row.raised || ""));
    if (!Number.isFinite(ts)) return;
    if (best === null || ts < best) {
      best = ts;
      iso = row.raised || "";
    }
  });
  return iso;
}

function _renderGroupCausaBadges(g) {
  const parts = [];
  parts.push(_renderGroupImpactBadge(g));
  if (g.losi) {
    parts.push(
      '<span class="cortes-group-pill cortes-group-pill--causa" title="Corte de fibra (LOSi/LOBi)">' +
        '<span class="cortes-badge cortes-badge--losi">LOSi</span>' +
        "<strong>" +
        _esc(g.losi) +
        "</strong></span>"
    );
  }
  if (g.dying) {
    parts.push(
      '<span class="cortes-group-pill cortes-group-pill--causa" title="Corte de luz (Dying Gasp)">' +
        '<span class="cortes-badge cortes-badge--dying">DG</span>' +
        "<strong>" +
        _esc(g.dying) +
        "</strong></span>"
    );
  }
  return parts.filter(Boolean).join("");
}

function _renderGroupCausaSummary(g) {
  const parts = [];
  if (g.losi) parts.push("LOSi " + g.losi);
  if (g.dying) parts.push("DG " + g.dying);
  if (!parts.length) return "";
  return (
    '<span class="cortes-group-summary-meta muted" title="Conteo por causa">' +
    _esc(parts.join(" · ")) +
    "</span>"
  );
}

function _ontBreakdownTitle(vnoList, ontTotal) {
  if (vnoList && vnoList.length) {
    return vnoList.map((v) => v.count + " " + v.vno).join(", ");
  }
  const n = Number(ontTotal) || 0;
  return n > 0 ? n + " ONT" : "";
}

function _sinMapTitle(row) {
  const clientes = row.ont_total ?? 0;
  if (clientes > 0) {
    return clientes + " clientes IN SERVICE sin path RATC/FATC en inventario";
  }
  return "Sin ONT IN SERVICE mapeadas en inventario para este PON";
}

function _renderSinMapoLabel(row) {
  return (
    '<span class="cortes-sin-map" title="' +
    _esc(_sinMapTitle(row)) +
    '">Sin Mapeo</span>'
  );
}

function _ctosFromKeys(ctoKeys) {
  const seen = new Set();
  const out = [];
  (ctoKeys || []).forEach((key) => {
    const s = String(key || "").trim();
    if (!s) return;
    const pipe = s.indexOf("|");
    const cto = pipe >= 0 ? s.slice(pipe + 1).trim() : s;
    if (cto && !seen.has(cto)) {
      seen.add(cto);
      out.push(cto);
    }
  });
  return out.sort((a, b) => a.localeCompare(b, "es"));
}

function _renderIdListCell(ids, opts) {
  opts = opts || {};
  const list = (ids || []).map((x) => String(x || "").trim()).filter(Boolean);
  if (!list.length) {
    if (opts.sinInventario) return _renderSinMapoLabel(opts.row);
    return (
      opts.emptyHtml ||
      '<span class="cortes-id-cell cortes-id-cell--empty" title="Sin dato">—</span>'
    );
  }
  const title = list.join(", ");
  if (list.length === 1) {
    return (
      '<span class="mono cortes-id-cell cortes-id-cell--single" title="' +
      _esc(title) +
      '">' +
      _esc(list[0]) +
      "</span>"
    );
  }
  return (
    '<span class="mono cortes-id-cell cortes-id-cell--multi" title="' +
    _esc(title) +
    '">' +
    _esc(list[0]) +
    ' <span class="cortes-id-cell__more">+' +
    _esc(String(list.length - 1)) +
    "</span></span>"
  );
}

function _renderCtoCell(row) {
  if (row.sin_inventario) return _renderSinMapoLabel(row);
  const ctos = _ctosFromKeys(row.cto_keys);
  if (!ctos.length) {
    return '<span class="cortes-id-cell cortes-id-cell--empty" title="Sin CTO">—</span>';
  }
  if (ctos.length === 1) {
    return (
      '<span class="mono cortes-id-cell cortes-id-cell--single cortes-id-cell--cto" title="' +
      _esc(ctos[0]) +
      '">' +
      _esc(ctos[0]) +
      "</span>"
    );
  }
  const title = ctos.join(", ");
  return (
    '<span class="cortes-metric-n cortes-cto-count" title="' +
    _esc(title) +
    '">' +
    _esc(String(ctos.length)) +
    "</span>"
  );
}

function _renderMetricRowCells(entity, opts) {
  opts = opts || {};
  const raised = opts.raised != null ? opts.raised : entity.raised;
  const clearedVal = opts.cleared != null ? opts.cleared : entity.cleared;
  const ont = Number(entity.ont_total ?? 0);
  const ontCls = ont > 0 ? " cortes-col-ont--hit" : "";
  let html = "";
  html +=
    '<td class="mono cortes-raised cortes-col-raised">' + _esc(_formatRaised(raised)) + "</td>";
  html +=
    '<td class="mono cortes-cleared cortes-col-cleared">' +
    _esc(clearedVal ? _formatRaised(clearedVal) : "—") +
    "</td>";
  html +=
    '<td class="cortes-col-ramas cortes-col-id">' + _renderRamasCell(entity) + "</td>";
  html +=
    '<td class="cortes-col-cto cortes-col-id">' + _renderCtoCell(entity) + "</td>";
  html +=
    '<td class="cortes-col-ont' +
    ontCls +
    '">' +
    _renderOntCell(entity.vno_list, ont, false, entity) +
    "</td>";
  html += '<td class="cortes-col-actions">' + (opts.actionsHtml || "") + "</td>";
  return html;
}

function _eventoClusterKey(row) {
  if (!row || !row.evento_simultaneo) return "";
  const clusterKey = String(row.evento_cluster_key || "").trim();
  if (clusterKey) return clusterKey;
  const sitio = String(row.principal || row.olt || "").trim();
  const ventana = String(row.evento_ventana || "").trim();
  const causa = String(row.evento_causa || row.causa || "OTRO")
    .trim()
    .toUpperCase();
  if (!sitio || !ventana) return "";
  return sitio + "|" + ventana + "|" + causa;
}

function _aggregateEventoItems(items) {
  let ont_total = 0;
  let losi = 0;
  let dying = 0;
  const ramas = new Set();
  const ctoKeys = new Set();
  const olts = new Set();
  const vnoAcc = {};
  (items || []).forEach((row) => {
    ont_total += Number(row.ont_total) || 0;
    const causa = String(row.causa || "");
    if (causa === "LOSI_LOBI") losi += 1;
    else if (causa === "DYING_GASP") dying += 1;
    if (row.olt) olts.add(String(row.olt));
    (row.ramas || []).forEach((rama) => ramas.add(String(rama)));
    (row.cto_keys || []).forEach((key) => ctoKeys.add(String(key)));
    (row.vno_list || []).forEach((v) => {
      const label = String(v.vno || "");
      if (!label) return;
      vnoAcc[label] = (vnoAcc[label] || 0) + (Number(v.count) || 0);
    });
  });
  return {
    items: items || [],
    cortes: (items || []).length,
    ont_total,
    losi,
    dying,
    ramas: Array.from(ramas).sort((a, b) => a.localeCompare(b, "es")),
    cto_keys: Array.from(ctoKeys).sort((a, b) => a.localeCompare(b, "es")),
    ramas_count: ramas.size,
    cto_count: ctoKeys.size,
    olt_count: olts.size,
    vno_list: Object.keys(vnoAcc)
      .sort((a, b) => a.localeCompare(b, "es"))
      .map((vno) => ({ vno, count: vnoAcc[vno] })),
    principal: (items && items[0] && items[0].principal) || "",
    evento_ventana: (items && items[0] && items[0].evento_ventana) || "",
    impacto: (items && items[0] && items[0].impacto) || "MODERADO",
  };
}

function _buildDisplayBlocks(items) {
  // Tabla: una fila por PON (como la GUI de Altiplano). La agrupación masiva va en el banner.
  return (items || []).map((item) => ({ type: "single", item }));
}

function _groupLatestCleared(items) {
  let best = null;
  let iso = "";
  (items || []).forEach((row) => {
    const ts = Date.parse(String(row.cleared || ""));
    if (!Number.isFinite(ts)) return;
    if (best === null || ts > best) {
      best = ts;
      iso = row.cleared || "";
    }
  });
  return iso;
}

function _buildClearedHierarchyBlocks(items) {
  const siteOrder = [];
  const bySite = new Map();
  (items || []).forEach((item) => {
    const site = _siteKey(item);
    if (!bySite.has(site)) {
      bySite.set(site, { hourOrder: [], hours: new Map() });
      siteOrder.push(site);
    }
    const bucket = bySite.get(site);
    const hourLabel = _formatRaisedHourBucket(item.raised);
    if (!bucket.hours.has(hourLabel)) {
      bucket.hours.set(hourLabel, []);
      bucket.hourOrder.push(hourLabel);
    }
    bucket.hours.get(hourLabel).push(item);
  });
  return siteOrder.map((site) => {
    const bucket = bySite.get(site);
    const hours = bucket.hourOrder.map((hourLabel) => ({
      type: "hora",
      key: site + "|" + hourLabel,
      site,
      hourLabel,
      items: bucket.hours.get(hourLabel) || [],
    }));
    const flatItems = hours.flatMap((h) => h.items);
    return {
      type: "sitio",
      key: site,
      site,
      hours,
      items: flatItems,
      itemCount: flatItems.length,
    };
  });
}

function _renderHierarchyToggle(key, expanded, title, label, cls, dataAttr) {
  return (
    '<button type="button" class="btn btn-ghost btn-sm ' +
    cls +
    '" data-' +
    dataAttr +
    '="' +
    _esc(key) +
    '" aria-expanded="' +
    (expanded ? "true" : "false") +
    '" title="' +
    _esc(title) +
    '"><span class="cortes-evento-toggle__icon" aria-hidden="true">' +
    (expanded ? "▾" : "▸") +
    '</span><span class="mono">' +
    _esc(label) +
    "</span></button>"
  );
}

function _renderSitioGroupRow(siteBlock) {
  const g = _aggregateEventoItems(siteBlock.items);
  const summaryMeta = _renderGroupCausaSummary(g);
  const ponCount = siteBlock.itemCount || 0;
  const expanded = _isSitioBlockExpanded(siteBlock);
  const toggleTitle = expanded
    ? "Ocultar horas de " + siteBlock.site
    : "Mostrar " + ponCount + " PON de " + siteBlock.site;
  const toggleBtn = _renderHierarchyToggle(
    siteBlock.key,
    expanded,
    toggleTitle,
    ponCount + " PON",
    "cortes-sitio-toggle",
    "sitio-key"
  );
  return (
    '<tr class="cortes-site-row' +
    (expanded ? "" : " cortes-site-row--collapsed") +
    '" data-sitio-key="' +
    _esc(siteBlock.key) +
    '"><td colspan="4" class="cortes-site-summary-cell">' +
    '<div class="cortes-group-head cortes-group-head--site">' +
    '<span class="cortes-group-head__lead">' +
    toggleBtn +
    '<span class="cortes-group-head__site">' +
    _esc(siteBlock.site) +
    "</span></span>" +
    (summaryMeta ? summaryMeta : "") +
    "</div></td>" +
    _renderMetricRowCells(g, {
      groupSummary: true,
      raised: _groupEarliestRaised(siteBlock.items),
      cleared: _groupLatestCleared(siteBlock.items),
      oltCount: g.olt_count,
      actionsHtml: "",
    }) +
    "</tr>"
  );
}

function _renderHourGroupRow(hourBlock, siteBlock) {
  const g = _aggregateEventoItems(hourBlock.items);
  const summaryMeta = _renderGroupCausaSummary(g);
  const ponCount = (hourBlock.items || []).length;
  const siteExpanded = _isSitioBlockExpanded(siteBlock);
  const expanded = _isHourBlockExpanded(hourBlock);
  const toggleTitle = expanded
    ? "Ocultar detalle de PON"
    : "Mostrar " + ponCount + " PON de " + hourBlock.hourLabel;
  const toggleBtn = _renderHierarchyToggle(
    hourBlock.key,
    expanded,
    toggleTitle,
    ponCount + " PON",
    "cortes-hour-toggle",
    "hora-key"
  );
  return (
    '<tr class="cortes-hour-row cortes-group-row cortes-group-row--lt' +
    (expanded ? "" : " cortes-hour-row--collapsed") +
    '"' +
    (siteExpanded ? "" : " hidden") +
    ' data-hora-key="' +
    _esc(hourBlock.key) +
    '" data-sitio-key="' +
    _esc(siteBlock.key) +
    '"><td colspan="4" class="cortes-hour-summary-cell">' +
    '<div class="cortes-group-head cortes-group-head--hour">' +
    '<span class="cortes-group-head__lead">' +
    toggleBtn +
    '<strong class="cortes-group-head__hour mono" title="' +
    _esc(hourBlock.hourLabel) +
    '">' +
    _esc(hourBlock.hourLabel) +
    "</strong></span>" +
    (summaryMeta ? summaryMeta : "") +
    "</div></td>" +
    _renderMetricRowCells(g, {
      groupSummary: true,
      raised: _groupEarliestRaised(hourBlock.items),
      cleared: _groupLatestCleared(hourBlock.items),
      oltCount: g.olt_count,
      actionsHtml: "",
    }) +
    "</tr>"
  );
}

function _countPonsInBlocks(blocks) {
  let n = 0;
  (blocks || []).forEach((block) => {
    if (block.type === "evento") n += (block.items || []).length;
    else if (block.type === "single") n += 1;
    else if (block.type === "sitio") n += block.itemCount || 0;
    else if (block.type === "hora") n += (block.items || []).length;
  });
  return n;
}

function _renderEventoGroupActions(items) {
  const ponKeys = (items || [])
    .map((row) => String(row.pon_key || "").trim())
    .filter(Boolean);
  if (!ponKeys.length) return "";
  const oltUrl = _buildOltUrlFromPonKeys(ponKeys);
  const principal = (items[0] && (items[0].principal || items[0].olt)) || "";
  return (
    '<div class="cortes-actions cortes-actions--compact">' +
    '<a class="btn btn-ghost btn-sm cortes-evento-olt-btn" href="' +
    _esc(oltUrl) +
    '" target="_blank" rel="noopener noreferrer" title="Abrir OLT/LT con todos los PON del evento">OLT</a>' +
    '<button type="button" class="btn btn-ghost btn-sm cortes-evento-reporte-btn" data-pon-keys="' +
    _esc(ponKeys.join(",")) +
    '" data-principal="' +
    _esc(principal) +
    '" title="Exportar clientes IN SERVICE del evento">Reporte</button>' +
    "</div>"
  );
}

function _renderEventoTableGroupRow(block) {
  const g = _aggregateEventoItems(block.items);
  const meta = block.items[0] || {};
  const badges = _renderGroupCausaBadges(g);
  const ventana = _formatVentanaArt(meta.evento_ventana || g.evento_ventana || "");
  const ponCount = (block.items || []).length;
  const expanded = _isEventoBlockExpanded(block);
  const sitio = g.principal || meta.principal || meta.olt || "Evento masivo";
  const oltCount = g.olt_count || 0;
  const oltHint =
    oltCount > 1
      ? '<span class="muted">' + _esc(oltCount) + " OLT · </span>"
      : "";
  const summaryTitle =
    _esc(sitio) +
    " · " +
    oltHint +
    "<strong>" +
    _esc(ponCount) +
    " PON</strong> · <span class=\"mono\">" +
    _esc(ventana) +
    "</span> · <strong>" +
    _esc(g.ont_total) +
    "</strong> clientes";
  const toggleTitle = expanded
    ? "Ocultar detalle de PON"
    : "Mostrar " + ponCount + " PON del evento";
  const toggleBtn =
    '<button type="button" class="btn btn-ghost btn-sm cortes-evento-toggle" data-evento-key="' +
    _esc(block.key) +
    '" aria-expanded="' +
    (expanded ? "true" : "false") +
    '" title="' +
    _esc(toggleTitle) +
    '"><span class="cortes-evento-toggle__icon" aria-hidden="true">' +
    (expanded ? "▾" : "▸") +
    '</span><span class="mono">' +
    _esc(ponCount) +
    " PON</span></button>";
  return (
    '<tr class="cortes-evento-row' +
    (expanded ? "" : " cortes-evento-row--collapsed") +
    '" data-evento-key="' +
    _esc(block.key) +
    '"><td colspan="4" class="cortes-evento-summary-cell">' +
    '<div class="cortes-group-head cortes-group-head--evento">' +
    '<span class="cortes-group-head__lead">' +
    toggleBtn +
    '<strong class="cortes-group-head__title cortes-group-head__title--evento" title="' +
    _esc(sitio + " · " + ventana) +
    '">' +
    summaryTitle +
    "</strong></span>" +
    (badges ? '<span class="cortes-group-head__badges">' + badges + "</span>" : "") +
    "</div></td>" +
    _renderMetricRowCells(g, {
      groupSummary: true,
      raised: _groupEarliestRaised(g.items),
      oltCount: g.olt_count,
      actionsHtml: _renderEventoGroupActions(block.items),
    }) +
    "</tr>"
  );
}

function _updateVisibleCount(blocks, totalBlocks) {
  const el = document.getElementById("cortes-visible-count");
  if (!el) return;
  const total = totalBlocks || (blocks || []).length;
  if (!total) {
    el.textContent = "0";
    return;
  }
  const pons = _countPonsInBlocks(blocks);
  const start = currentPage * pageSize + 1;
  const end = Math.min(total, (currentPage + 1) * pageSize);
  el.textContent =
    pons +
    " PON · filas " +
    (start === end ? start + "/" + total : start + "–" + end + "/" + total);
}

function _renderVnoResumen(vnoResumen) {
  const wrap = document.getElementById("cortes-vno-resumen");
  const chips = document.getElementById("cortes-vno-chips");
  if (!wrap || !chips) return;
  const rows = vnoResumen || [];
  if (!rows.length) {
    wrap.hidden = true;
    chips.innerHTML = "";
    return;
  }
  wrap.hidden = false;
  chips.innerHTML = rows
    .map(
      (r) =>
        '<span class="cortes-vno-chip"><span class="cortes-vno-chip__n">' +
        _esc(r.count) +
        '</span><span class="cortes-vno-chip__l">' +
        _esc(r.vno) +
        "</span></span>"
    )
    .join("");
}

function _renderOntCell(vnoList, ontTotal, summaryOnly, row) {
  const n = Number(ontTotal) || 0;
  const title = _ontBreakdownTitle(vnoList, n);
  if (summaryOnly) {
    if (n <= 0) return '<span class="cortes-metric-n cortes-metric-n--empty">—</span>';
    return (
      '<span class="cortes-metric-n' +
      (n > 0 ? "" : " cortes-metric-n--empty") +
      '" title="' +
      _esc(title) +
      '">' +
      _esc(n) +
      "</span>"
    );
  }
  if (row && row.sin_inventario) {
    return _renderSinMapoLabel(row);
  }
  if (vnoList && vnoList.length) {
    return (
      '<div class="cortes-ont-cell">' +
      vnoList
        .map(
          (v) =>
            '<span class="cortes-ont-pill" title="' +
            _esc(v.vno) +
            '"><span class="cortes-ont-pill__n">' +
            _esc(v.count) +
            "</span> " +
            _esc(v.vno) +
            "</span>"
        )
        .join("") +
      "</div>"
    );
  }
  if (n > 0) {
    return (
      '<div class="cortes-ont-cell"><span class="cortes-ont-pill" title="ONT afectadas">' +
      '<span class="cortes-ont-pill__n">' +
      _esc(n) +
      "</span></span></div>"
    );
  }
  return '<span class="muted">—</span>';
}

function _renderVnoCell(vnoList) {
  return _renderOntCell(vnoList, 0);
}

function _renderRamasCell(row) {
  const ramas = row.ramas || [];
  if (!ramas.length) {
    return _renderIdListCell([], {
      row: row,
      sinInventario: !!row.sin_inventario,
      emptyHtml: '<span class="cortes-id-cell cortes-id-cell--empty" title="Sin RAMA">—</span>',
    });
  }
  return _renderIdListCell(ramas, { row: row });
}

function _renderActions(row, compact) {
  if (row.sin_inventario) {
    return '<span class="muted" title="' + _esc(_sinMapTitle(row)) + '">—</span>';
  }
  const pk = String(row.pon_key || "").trim();
  const oltUrl = pk ? _buildOltUrlFromPonKeys([pk]) : "/dashboard/olt";
  const cls = compact ? " cortes-actions--compact" : "";
  let html =
    '<div class="cortes-actions' +
    cls +
    '"><a class="btn btn-ghost btn-sm cortes-evento-olt-btn" href="' +
    _esc(oltUrl) +
    '" target="_blank" rel="noopener noreferrer" title="Abrir OLT/LT con este PON seleccionado">OLT</a>';
  if (pk) {
    html +=
      '<button type="button" class="btn btn-ghost btn-sm cortes-evento-reporte-btn" data-pon-key="' +
      _esc(pk) +
      '" data-principal="' +
      _esc(row.principal || row.olt || "") +
      '" title="Exportar clientes IN SERVICE (PON, RAMA, CTO, AID)">Reporte</button>';
  }
  if (row.ramas && row.ramas[0]) {
    html +=
      '<a class="btn btn-ghost btn-sm cortes-action-rx-btn" href="/?q=' +
      encodeURIComponent(row.ramas[0]) +
      '" target="_blank" rel="noopener noreferrer" title="Consultar potencias RX">RX</a>';
  }
  html += "</div>";
  return html;
}

function _renderEstadoCell(row) {
  const status = String(row.status || "Active").trim() || "Active";
  const badgeCls = _ESTADO_BADGE_CLASS[status] || "cortes-badge--active";
  const label = status.toLowerCase() === "cleared" ? "CLR" : "ACT";
  return (
    '<span class="cortes-badge ' +
    badgeCls +
    '" title="' +
    _esc(status) +
    '">' +
    _esc(label) +
    "</span>"
  );
}

function _groupHasMixedCausa(g) {
  if (!g) return false;
  const losi = Number(g.losi) || 0;
  const dying = Number(g.dying) || 0;
  return losi > 0 && dying > 0;
}

function _renderCausaCell(row, opts) {
  opts = opts || {};
  const parts = [];
  if (_isNuevo(row)) {
    parts.push(
      '<span class="cortes-badge cortes-badge--nuevo" title="Corte nuevo desde tu última visita">N</span>'
    );
  }
  const impactHtml = _renderImpactoBadge(row, opts);
  if (impactHtml) parts.push(impactHtml);
  const showCausaBadge = !opts.child || !opts.group || _groupHasMixedCausa(opts.group);
  if (showCausaBadge) {
    const causa = row.causa || "OTRO";
    const badgeCls = _CAUSA_BADGE_CLASS[causa] || "cortes-badge--otro";
    const badgeTxt = _CAUSA_SHORT[causa] || row.causa_label || causa;
    parts.push(
      '<span class="cortes-badge ' +
        badgeCls +
        '" title="' +
        _esc(row.causa_label || causa) +
        '">' +
        _esc(badgeTxt) +
        "</span>"
    );
  }
  if (!parts.length) {
    return '<span class="cortes-causa-cell cortes-causa-cell--empty" aria-hidden="true"></span>';
  }
  return '<span class="cortes-causa-cell">' + parts.join("") + "</span>";
}

function _renderDataRow(row, opts) {
  opts = opts || {};
  const child = opts.child
    ? " cortes-data-row--child" + (opts.nested ? " cortes-data-row--nested" : "")
    : "";
  const nuevo = _isNuevo(row) ? " cortes-data-row--nuevo" : "";
  const loc = opts.child
    ? '<span class="mono cortes-loc__pon">' + _esc(row.pon_label || "PON " + row.pon) + "</span>"
    :
        '<div class="cortes-loc"><span class="mono cortes-loc__olt">' +
        _esc(row.olt) +
        '</span><span class="cortes-loc__sub mono">LT ' +
        _esc(row.lt) +
        " · " +
        _esc(row.pon_label || row.pon) +
        "</span></div>";
  const causaHtml = _renderCausaCell(row, {
    child: opts.child,
    group: opts.group,
    groupChild: opts.child,
  });
  let trAttrs = "";
  if (opts.eventoKey) {
    trAttrs += ' data-evento-key="' + _esc(opts.eventoKey) + '"';
  }
  return (
    '<tr class="cortes-data-row' +
    child +
    nuevo +
    '"' +
    trAttrs +
    ">" +
    '<td class="cortes-col-causa">' +
    causaHtml +
    "</td>" +
    '<td class="cortes-col-loc">' +
    loc +
    "</td>" +
    _renderMetricRowCells(row, {
      actionsHtml: _renderActions(row, true),
    }) +
    "</tr>"
  );
}

function _renderDisplayBlock(block) {
  if (block.type === "evento") {
    let html = _renderEventoTableGroupRow(block);
    if (_isEventoBlockExpanded(block)) {
      const g = _aggregateEventoItems(block.items);
      (block.items || []).forEach((row) => {
        html += _renderDataRow(row, { child: true, group: g, eventoKey: block.key });
      });
    }
    return html;
  }
  if (block.type === "single") {
    return _renderDataRow(block.item);
  }
  return "";
}

function _displayRowsForMode() {
  const blocks = _buildDisplayBlocks(allItems || []);
  _pruneEventoCollapseKeys(blocks);
  return { mode: "flat", blocks };
}

function _totalPagesForDisplay() {
  const blocks = _displayRowsForMode().blocks;
  return blocks.length ? Math.ceil(blocks.length / pageSize) : 0;
}

function _updatePager() {
  const pager = document.getElementById("cortes-pager");
  const info = document.getElementById("cortes-page-info");
  const prev = document.getElementById("cortes-page-prev");
  const next = document.getElementById("cortes-page-next");
  const pages = _totalPagesForDisplay();
  const blocks = _displayRowsForMode().blocks;
  const total = blocks.length;
  if (!pager) return;
  pager.hidden = total <= PAGER_SHOW_ABOVE;
  if (info) {
    info.textContent = pages ? "Página " + (currentPage + 1) + " de " + pages : "0 resultados";
  }
  if (prev) prev.disabled = currentPage <= 0;
  if (next) next.disabled = currentPage >= pages - 1;
}

function _renderTablePage() {
  const tbody = document.getElementById("cortes-tbody");
  const table = document.getElementById("cortes-table");
  const empty = document.getElementById("cortes-empty");
  if (!tbody || !table) return;

  _syncTableLayout();
  const display = _displayRowsForMode();
  const blocks = display.blocks;
  const total = blocks.length;

  if (!total) {
    tbody.innerHTML = "";
    table.classList.add("is-hidden");
    if (empty) empty.hidden = false;
    _updatePager();
    _updateVisibleCount([], 0);
    return;
  }

  if (empty) empty.hidden = true;
  table.classList.remove("is-hidden");

  const start = currentPage * pageSize;
  const pageBlocks = blocks.slice(start, start + pageSize);
  let html = "";
  pageBlocks.forEach((block) => {
    html += _renderDisplayBlock(block);
  });

  tbody.innerHTML = html;
  _updatePager();
  _updateVisibleCount(pageBlocks, total);
}

function _setLoading(on) {
  const loading = document.getElementById("cortes-loading");
  const table = document.getElementById("cortes-table");
  const empty = document.getElementById("cortes-empty");
  const pager = document.getElementById("cortes-pager");
  const btn = document.getElementById("btn-cortes-search");
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

function _showCortesError(msg) {
  const empty = document.getElementById("cortes-empty");
  const table = document.getElementById("cortes-table");
  const tbody = document.getElementById("cortes-tbody");
  allItems = [];
  currentPage = 0;
  if (tbody) tbody.innerHTML = "";
  if (table) table.classList.add("is-hidden");
  if (empty) {
    empty.hidden = false;
    const p = empty.querySelector("p");
    if (p) {
      p.textContent = msg || "No se pudieron cargar los cortes.";
      p.classList.add("cortes-error-msg");
    }
  }
  _renderEventosMasivos([]);
  _updatePager();
  _cortesToast(msg || "Error consultando cortes", { variant: "error" });
}

function _buildCortesRamaStatePayload() {
  return {
    ts: Date.now(),
    q: document.getElementById("cortes-q")?.value || "",
    estado: _getCortesEstado(),
    causa: document.getElementById("cortes-causa")?.value || "ALL",
    principal: document.getElementById("cortes-principal")?.value || "ALL",
    vno: document.getElementById("cortes-vno")?.value || "ALL",
    sort: document.getElementById("cortes-sort")?.value || "reciente",
    fechaDia: _cortesFechaIso(),
    pageSize,
    currentPage,
    refreshMs: _getRefreshMs(),
  };
}

function _saveStateSoon() {
  if (!_stateStore) return;
  _stateStore.saveSoon(_buildCortesRamaStatePayload);
}

function _readCortesRamaState() {
  if (!_stateStore) return null;
  return _stateStore.read((parsed) => {
    if (!parsed || typeof parsed !== "object") return null;
    const ts = Number(parsed.ts || 0);
    if (!Number.isFinite(ts) || Date.now() - ts > _STATE_MAX_AGE_MS) return null;
    const page = Number(parsed.currentPage);
    const size = Number(parsed.pageSize);
    return {
      q: typeof parsed.q === "string" ? parsed.q : "",
      estado: parsed.estado === "todas" ? "activas" : typeof parsed.estado === "string" ? parsed.estado : "activas",
      causa: typeof parsed.causa === "string" ? parsed.causa : "ALL",
      principal: typeof parsed.principal === "string" ? parsed.principal : "ALL",
      vno: typeof parsed.vno === "string" ? parsed.vno : "ALL",
      sort: typeof parsed.sort === "string" ? parsed.sort : "reciente",
      fechaDia: typeof parsed.fechaDia === "string" ? parsed.fechaDia : "",
      pageSize: Number.isFinite(size) && size > 0 ? Math.floor(size) : 10,
      currentPage: Number.isFinite(page) && page >= 0 ? Math.floor(page) : 0,
      refreshMs: Number.isFinite(Number(parsed.refreshMs)) && Number(parsed.refreshMs) > 0
        ? Math.floor(Number(parsed.refreshMs))
        : 0,
    };
  });
}

function _restoreState() {
  const st = _readCortesRamaState();
  if (!st) return false;
  _restoringState = true;
  const q = document.getElementById("cortes-q");
  if (q && st.q) q.value = st.q;
  const estadoSel = document.getElementById("cortes-estado");
  if (estadoSel && st.estado) {
    estadoSel.value = st.estado === "todas" ? "activas" : st.estado;
  }
  const causa = document.getElementById("cortes-causa");
  if (causa && st.causa) causa.value = st.causa;
  const principal = document.getElementById("cortes-principal");
  if (principal && st.principal) principal.value = st.principal;
  const vno = document.getElementById("cortes-vno");
  if (vno && st.vno) vno.value = st.vno;
  const sortSel = document.getElementById("cortes-sort");
  if (sortSel && st.sort) sortSel.value = st.sort;
  if (st.fechaDia) {
    _setCortesFechaIso(st.fechaDia);
  } else {
    _setCortesFechaAll();
  }
  if (st.pageSize) pageSize = st.pageSize;
  const ps = document.getElementById("cortes-page-size");
  if (ps && st.pageSize) ps.value = String(st.pageSize);
  if (typeof st.currentPage === "number") currentPage = st.currentPage;
  const refreshSel = document.getElementById("cortes-refresh");
  if (refreshSel && st.refreshMs) {
    refreshSel.value = String(st.refreshMs);
    _saveRefreshMs(st.refreshMs);
  }
  _restoringState = false;
  return true;
}

function resetCortes() {
  document.getElementById("cortes-q").value = "";
  const estadoSel = document.getElementById("cortes-estado");
  if (estadoSel) estadoSel.value = "activas";
  document.getElementById("cortes-causa").value = "ALL";
  document.getElementById("cortes-principal").value = "ALL";
  document.getElementById("cortes-vno").value = "ALL";
  const sortSel = document.getElementById("cortes-sort");
  if (sortSel) sortSel.value = "reciente";
  _setCortesFechaHoy();
  const refreshSel = document.getElementById("cortes-refresh");
  if (refreshSel) refreshSel.value = "0";
  _applyAutoRefresh();
  currentPage = 0;
  fetchCortes({ fresh: true });
}

function fetchCortes(opts) {
  opts = opts || {};
  const silent = !!opts.silent;
  const preservePage = !!opts.preservePage;
  const fresh = !!opts.fresh;
  if (_fetchInFlight) {
    _fetchPending = opts;
    return Promise.resolve();
  }
  _fetchInFlight = true;
  _fetchPending = null;

  const empty = document.getElementById("cortes-empty");
  if (!silent) _setLoading(true);
  else _setRefreshBusy(true);
  if (empty && !silent) {
    empty.hidden = true;
    const p = empty.querySelector("p");
    if (p) {
      p.textContent = _emptyCortesMessage();
      p.classList.remove("cortes-error-msg");
    }
  }

  const params = _buildFetchParams({ fresh: fresh });
  return fetch("/api/alarm-analyzer?" + params.toString())
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || data.error) {
        _showCortesError(data.error || "Error consultando cortes");
        return;
      }
      lastPayload = data;
      allItems = data.items || [];
      _pruneEventoCollapseKeys(_buildDisplayBlocks(allItems));
      _syncTableLayout();
      if (!preservePage && !_restoringState) currentPage = 0;
      _populateSelect(document.getElementById("cortes-principal"), data.principals, "Todos los sitios");
      _populateSelect(document.getElementById("cortes-vno"), data.vnos, "Todos los VNO");
      _updateKpis(data, allItems);
      _renderVnoResumen(data.vno_resumen);
      _renderTablePage();
      if (!silent && allItems.length) {
        const nuevos = _countNuevos(allItems);
        const t = data.totales || {};
        let toastMsg =
          allItems.length + " cortes · " + (t.CLIENTES_AFECTADOS ?? 0) + " clientes" +
          (nuevos ? " · " + nuevos + " nuevos" : "");
        if (t.EMERGENCIA) toastMsg += " · " + t.EMERGENCIA + " emergencia";
        _cortesToast(toastMsg, t.EMERGENCIA ? { variant: "error", durationMs: 4500 } : undefined);
      }
      const eventos = data.eventos_masivos || [];
      if (!silent && eventos.some((ev) => ev.impacto === "EMERGENCIA" || ev.impacto === "URGENTE")) {
        const top = eventos[0];
        _cortesToast(
          "Evento masivo: " + top.cortes + " PON · " + top.clientes + " clientes (" + top.minute + ")",
          {
            variant: top.impacto === "EMERGENCIA" ? "error" : "warning",
            durationMs: 6000,
            create: true,
            id: "cortes-evento-toast",
          }
        );
      }
      if (!_restoringState) _saveStateSoon();
    })
    .catch(() => {
      if (!silent) _showCortesError("Error de red consultando cortes");
    })
    .finally(() => {
      _fetchInFlight = false;
      if (!silent) _setLoading(false);
      else _setRefreshBusy(false);
      const pending = _fetchPending;
      _fetchPending = null;
      if (pending) fetchCortes(pending);
    });
}

window.fetchCortes = fetchCortes;

function _downloadBlobCsv(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "reporte_evento.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportEventoReporte(ev, btn) {
  const keys = (ev && (ev.pon_keys || ev.pons)) || [];
  if (!keys.length) {
    _cortesToast("Sin PON asociados a este evento", { variant: "warning" });
    return;
  }
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  fetch("/dashboard/alarm-analyzer/evento-reporte.csv", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/csv" },
    credentials: "same-origin",
    body: JSON.stringify({
      pon_keys: keys,
      principal: ev.principal || ev.olt || "",
      ventana: ev.ventana || ev.minute || "",
    }),
  })
    .then(function (res) {
      if (res.status === 401) {
        window.location.reload();
        return null;
      }
      if (!res.ok) {
        return res.text().then(function (txt) {
          throw new Error(txt || "No se pudo generar el reporte");
        });
      }
      const cd = res.headers.get("Content-Disposition") || "";
      const m = /filename=\"?([^\";]+)\"?/i.exec(cd);
      const fname = m ? m[1] : "pones_seleccionados.csv";
      return res.blob().then(function (blob) {
        return { blob: blob, filename: fname };
      });
    })
    .then(function (out) {
      if (!out) return;
      _downloadBlobCsv(out.blob, out.filename);
      _cortesToast("Reporte exportado (" + keys.length + " PON)", { variant: "success" });
    })
    .catch(function (err) {
      _cortesToast(err.message || "Error al exportar reporte", { variant: "error" });
    })
    .finally(function () {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    });
}

function _onCortesFilterChange() {
  _syncToolbarContext();
  currentPage = 0;
  if (!_restoringState) _saveStateSoon();
  fetchCortes({ fresh: true });
}

function _onCortesSortChange() {
  currentPage = 0;
  if (!_restoringState) _saveStateSoon();
  fetchCortes({ fresh: true });
}

function _onCortesReporteButtonClick(ev) {
  const btn = ev.target.closest(".cortes-evento-reporte-btn");
  if (!btn || btn.disabled) return;
  ev.preventDefault();
  ev.stopPropagation();
  const pk = (btn.getAttribute("data-pon-key") || "").trim();
  const pkMany = (btn.getAttribute("data-pon-keys") || "").trim();
  if (pkMany) {
    exportEventoReporte(
      {
        pon_keys: pkMany.split(",").map((s) => s.trim()).filter(Boolean),
        principal: (btn.getAttribute("data-principal") || "").trim(),
      },
      btn
    );
    return;
  }
  if (pk) {
    exportEventoReporte(
      {
        pon_keys: [pk],
        principal: (btn.getAttribute("data-principal") || "").trim(),
      },
      btn
    );
    return;
  }
  const card = btn.closest("[data-evento-idx]");
  const list = document.getElementById("cortes-eventos-list");
  const idx = card ? parseInt(card.getAttribute("data-evento-idx") || "", 10) : NaN;
  const rows = list && list._eventosData ? list._eventosData : [];
  const row = Number.isFinite(idx) ? rows[idx] : null;
  if (!row) {
    _cortesToast("Evento no disponible", { variant: "warning" });
    return;
  }
  exportEventoReporte(row, btn);
}

function _onCortesTbodyClick(ev) {
  const sitioToggle = ev.target.closest(".cortes-sitio-toggle");
  if (sitioToggle) {
    ev.preventDefault();
    const key = (sitioToggle.getAttribute("data-sitio-key") || "").trim();
    if (key) _toggleSitioBlock(key);
    return;
  }
  const horaToggle = ev.target.closest(".cortes-hour-toggle");
  if (horaToggle) {
    ev.preventDefault();
    const key = (horaToggle.getAttribute("data-hora-key") || "").trim();
    if (key) _toggleHourBlock(key);
    return;
  }
  const toggle = ev.target.closest(".cortes-evento-toggle");
  if (toggle) {
    ev.preventDefault();
    const key = (toggle.getAttribute("data-evento-key") || "").trim();
    if (key) _toggleEventoBlock(key);
    return;
  }
  _onCortesReporteButtonClick(ev);
}

function initCortesRamaDashboard() {
  if (_cortesPageReady) return;
  _cortesPageReady = true;

  document.getElementById("cortes-eventos-list")?.addEventListener("click", _onCortesReporteButtonClick);
  document.getElementById("cortes-tbody")?.addEventListener("click", _onCortesTbodyClick);
  document.getElementById("btn-cortes-limpiar")?.addEventListener("click", resetCortes);
  document.getElementById("btn-cortes-search")?.addEventListener("click", (ev) => {
    ev.preventDefault();
    fetchCortes({ fresh: true });
  });
  document.getElementById("btn-cortes-marcar-vistos")?.addEventListener("click", () => {
    _markAllSeen(allItems);
    _updateKpis(lastPayload, allItems);
    _renderTablePage();
    _cortesToast("Cortes marcados como vistos");
  });
  document.getElementById("cortes-q")?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      fetchCortes({ fresh: true });
    }
  });
  const refreshSel = document.getElementById("cortes-refresh");
  const savedRefresh = _loadRefreshMs();
  if (refreshSel && savedRefresh) {
    refreshSel.value = String(savedRefresh);
  }
  refreshSel?.addEventListener("change", () => {
    _applyAutoRefresh();
    const ms = _getRefreshMs();
    if (!ms) return;
    fetchCortes({ silent: true, preservePage: true, fresh: true }).finally(() => {
      _scheduleAutoRefreshTick();
    });
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) return;
    if (!_getRefreshMs()) return;
    _stopAutoRefresh();
    fetchCortes({ silent: true, preservePage: true, fresh: true }).finally(() => {
      _scheduleAutoRefreshTick();
    });
  });
  window.addEventListener("beforeunload", () => {
    _stopAutoRefresh();
  });
  window.addEventListener("pageshow", (ev) => {
    if (ev.persisted) fetchCortes({ fresh: true });
  });
  ["cortes-estado", "cortes-causa", "cortes-principal", "cortes-vno"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", _onCortesFilterChange);
  });
  document.getElementById("cortes-sort")?.addEventListener("change", _onCortesSortChange);
  document.getElementById("cortes-page-prev")?.addEventListener("click", () => {
    if (currentPage > 0) {
      currentPage -= 1;
      _renderTablePage();
      _saveStateSoon();
    }
  });
  document.getElementById("cortes-page-next")?.addEventListener("click", () => {
    if (currentPage < _totalPagesForDisplay() - 1) {
      currentPage += 1;
      _renderTablePage();
      _saveStateSoon();
    }
  });
  document.getElementById("cortes-page-size")?.addEventListener("change", (ev) => {
    pageSize = parseInt(ev.target.value, 10) || 10;
    currentPage = 0;
    _renderTablePage();
    _saveStateSoon();
  });

  _initCortesFechaPicker();
  let restored = false;
  try {
    restored = !!_restoreState();
  } catch (_err) {
    /* estado de sesión corrupto no debe impedir la consulta inicial */
  }
  if (!restored) {
    _setCortesFechaHoy();
  }
  _syncTableLayout();
  _syncToolbarContext();
  _applyAutoRefresh();
  fetchCortes({ fresh: true });
}

function bootCortesRamaDashboard() {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCortesRamaDashboard, { once: true });
  } else {
    initCortesRamaDashboard();
  }
}

bootCortesRamaDashboard();
