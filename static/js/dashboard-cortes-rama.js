let lastPayload = null;
let allItems = [];
let allGrupos = [];
let currentPage = 0;
let pageSize = 10;
let viewMode = "grupo";
const PAGER_SHOW_ABOVE = 10;

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

function _isNuevo(row) {
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

function _buildFechaParam() {
  const day = _cortesFechaIso();
  return day || "hoy";
}

function _initCortesFechaPicker() {
  const input = document.getElementById("cortes-fecha-dia");
  const NFP = window.NocEstadisticasFlatpickr;
  if (!input || !NFP || _cortesFechaPicker) {
    return;
  }
  const initial = (input.value || "").trim() || _todayArtIso();
  _cortesFechaPicker = NFP.create(input, {
    defaultDate: initial,
    onChange() {
      if (_restoringState) return;
      currentPage = 0;
      if (!_restoringState) _saveStateSoon();
      fetchCortes({ fresh: true });
    },
  });
}

function _setCortesFechaIso(iso) {
  const val = String(iso || "").trim();
  if (_cortesFechaPicker && val) {
    _cortesFechaPicker.setDate(val, false);
    return;
  }
  const input = document.getElementById("cortes-fecha-dia");
  if (input) input.value = val;
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

function _ensureFechaHoy() {
  if (_cortesFechaPicker) {
    if (!_cortesFechaIso()) {
      _setCortesFechaIso(_todayArtIso());
    }
    return;
  }
  const fechaDia = document.getElementById("cortes-fecha-dia");
  if (fechaDia && !fechaDia.value) {
    fechaDia.value = _todayArtIso();
  }
}

function _getCortesEstado() {
  return document.getElementById("cortes-estado")?.value || "activas";
}

const _IMPACTO_RANK = { EMERGENCIA: 3, URGENTE: 2, MODERADO: 1 };

function _syncTableLayout() {
  const estado = _getCortesEstado();
  _showClearedCol = estado === "cleared" || estado === "todas";
  const table = document.getElementById("cortes-table");
  if (!table) return;
  table.classList.toggle("cortes-table--show-cleared", _showClearedCol);
  table.classList.toggle("cortes-table--show-estado", estado !== "activas");
  table.classList.toggle("cortes-table--grupo", viewMode === "grupo");
  const locTh = document.getElementById("cortes-th-loc");
  if (locTh) locTh.textContent = viewMode === "grupo" ? "PON" : "OLT / LT / PON";
}

function _emptyCortesMessage() {
  const estado = _getCortesEstado();
  if (estado === "cleared") return "Sin cortes cleared que coincidan con los filtros.";
  if (estado === "todas") return "Sin cortes que coincidan con los filtros.";
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
  const impacto = document.getElementById("cortes-impacto")?.value || "ALL";
  if (causa && causa !== "ALL") params.set("causa", causa);
  if (principal && principal !== "ALL") params.set("principal", principal);
  if (vno && vno !== "ALL") params.set("vno", vno);
  if (q) params.set("q", q);
  if (sort && sort !== "reciente") params.set("sort", sort);
  if (fecha) params.set("fecha", fecha);
  if (impacto && impacto !== "ALL") params.set("impacto", impacto);
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
  set("kpi-nuevos", _countNuevos(payload?.items || []));
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
  _updateVisibleCount(displayItems);
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

function _renderEventoMasivoCard(ev) {
  const imp = ev.impacto || "MODERADO";
  const badgeCls = _IMPACTO_BADGE_CLASS[imp] || "cortes-badge--moderado";
  const badgeTxt = _IMPACTO_SHORT[imp] || imp;
  const sitio = ev.principal || ev.olt || "";
  const tipo = _eventoTipo(ev);
  const tipoMeta = _EVENTO_TIPO_META[tipo] || _EVENTO_TIPO_META.otro;
  return (
    '<div class="cortes-evento-card cortes-evento-card--' +
    imp.toLowerCase() +
    '">' +
    '<span class="cortes-badge ' +
    tipoMeta.badgeCls +
    '" title="' +
    _esc(ev.tipo_label || tipoMeta.label) +
    '">' +
    _esc(tipoMeta.badgeTxt) +
    "</span>" +
    '<span class="cortes-badge ' +
    badgeCls +
    '">' +
    _esc(badgeTxt) +
    "</span>" +
    '<span class="cortes-evento-card__body">' +
    (sitio ? "<strong>" + _esc(sitio) + "</strong> · " : "") +
    "<strong>" +
    _esc(ev.cortes) +
    " PON</strong> · <span class=\"mono\">" +
    _esc(ev.ventana || ev.minute) +
    "</span> · <strong>" +
    _esc(ev.clientes) +
    "</strong> clientes" +
    "</span></div>"
  );
}

function _renderEventosMasivos(eventos) {
  const banner = document.getElementById("cortes-eventos-banner");
  const list = document.getElementById("cortes-eventos-list");
  if (!banner || !list) return;
  const rows = eventos || [];
  if (!rows.length) {
    banner.hidden = true;
    list.innerHTML = "";
    return;
  }
  banner.hidden = false;
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
      sectionRows.map(_renderEventoMasivoCard).join("") +
      "</div></section>";
  });
  list.innerHTML = html;
}

function _impactoBadgeHtml(imp, opts) {
  opts = opts || {};
  const badgeCls = _IMPACTO_BADGE_CLASS[imp] || "cortes-badge--moderado";
  const badgeTxt = _IMPACTO_SHORT[imp] || opts.label || imp;
  const eventoCls = opts.evento ? " cortes-badge--evento" : "";
  return (
    '<span class="cortes-badge ' +
    badgeCls +
    eventoCls +
    '" title="' +
    _esc(opts.title || imp) +
    '">' +
    _esc(badgeTxt) +
    (opts.evento
      ? '<span class="cortes-badge__evento" aria-hidden="true">Σ</span>'
      : "") +
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

function _renderGroupMetaPills(g, opts) {
  const extra = (opts && opts.extra) || "";
  return (
    extra +
    '<span class="cortes-group-pill"><strong>' +
    _esc(g.cortes) +
    "</strong> PON</span>" +
    '<span class="cortes-group-pill"><strong>' +
    _esc(g.ont_total) +
    "</strong> clientes</span>" +
    _renderGroupImpactBadge(g) +
    (g.losi
      ? '<span class="cortes-group-pill cortes-group-pill--causa" title="Corte de fibra (LOSi/LOBi)">' +
        '<span class="cortes-badge cortes-badge--losi">LOSi</span>' +
        "<strong>" +
        _esc(g.losi) +
        "</strong></span>"
      : "") +
    (g.dying
      ? '<span class="cortes-group-pill cortes-group-pill--causa" title="Corte de luz (Dying Gasp)">' +
        '<span class="cortes-badge cortes-badge--dying">DG</span>' +
        "<strong>" +
        _esc(g.dying) +
        "</strong></span>"
      : "") +
    '<span class="cortes-group-pill">' +
    _esc(g.ramas_count) +
    " RAMAs</span>"
  );
}

function _aggregateLtGrupos(ltGrupos) {
  let cortes = 0;
  let ont_total = 0;
  let losi = 0;
  let dying = 0;
  const ramas = new Set();
  const items = [];
  (ltGrupos || []).forEach((g) => {
    cortes += Number(g.cortes) || 0;
    ont_total += Number(g.ont_total) || 0;
    losi += Number(g.losi) || 0;
    dying += Number(g.dying) || 0;
    (g.ramas || []).forEach((rama) => ramas.add(String(rama)));
    (g.items || []).forEach((row) => items.push(row));
  });
  return {
    cortes,
    ont_total,
    losi,
    dying,
    ramas_count: ramas.size,
    items,
  };
}

function _buildSitioGrupos(grupos) {
  const order = [];
  const map = new Map();
  (grupos || []).forEach((g) => {
    const key = String(g.principal || "—");
    if (!map.has(key)) {
      map.set(key, { principal: key, lt_grupos: [] });
      order.push(key);
    }
    map.get(key).lt_grupos.push(g);
  });
  return order.map((key) => {
    const site = map.get(key);
    return Object.assign(site, _aggregateLtGrupos(site.lt_grupos));
  });
}

function _renderSitioGroupRow(site) {
  const ltCount = (site.lt_grupos || []).length;
  const ltPill =
    ltCount > 1
      ? '<span class="cortes-group-pill cortes-group-pill--lt-count"><strong>' +
        _esc(ltCount) +
        "</strong> LT</span>"
      : "";
  return (
    '<tr class="cortes-site-row"><td colspan="10">' +
    '<div class="cortes-group-head cortes-group-head--site">' +
    '<span class="cortes-group-head__site">' +
    _esc(site.principal || "—") +
    "</span>" +
    '<span class="cortes-group-head__meta">' +
    _renderGroupMetaPills(site, { extra: ltPill }) +
    "</span></div></td></tr>"
  );
}

function _renderLtSubGroupRow(g) {
  return (
    '<tr class="cortes-group-row cortes-group-row--lt"><td colspan="10">' +
    '<div class="cortes-group-head cortes-group-head--lt">' +
    '<span class="cortes-group-head__lt mono">' +
    _esc(g.lt_name || "") +
    "</span>" +
    '<span class="cortes-group-head__meta">' +
    _renderGroupMetaPills(g) +
    "</span></div></td></tr>"
  );
}

function _renderSitioLtGroupRow(g) {
  return (
    '<tr class="cortes-group-row"><td colspan="10">' +
    '<div class="cortes-group-head">' +
    '<span class="cortes-group-head__lead">' +
    '<span class="cortes-group-head__site">' +
    _esc(g.principal || "—") +
    "</span>" +
    '<span class="cortes-group-head__lt mono">' +
    _esc(g.lt_name || "") +
    "</span></span>" +
    '<span class="cortes-group-head__meta">' +
    _renderGroupMetaPills(g) +
    "</span></div></td></tr>"
  );
}

function _updateVisibleCount(displayItems) {
  const el = document.getElementById("cortes-visible-count");
  if (!el) return;
  const total = displayItems.length;
  if (!total) {
    el.textContent = "0";
    return;
  }
  const start = currentPage * pageSize + 1;
  const end = Math.min(total, (currentPage + 1) * pageSize);
  el.textContent = start === end ? start + "/" + total : start + "–" + end + "/" + total;
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

function _renderVnoCell(vnoList) {
  if (!vnoList || !vnoList.length) return '<span class="muted">—</span>';
  return (
    '<div class="cortes-vno-cell">' +
    vnoList
      .map(
        (v) =>
          '<span class="cortes-vno-pill" title="' +
          _esc(v.vno) +
          '"><span class="cortes-vno-pill__n">' +
          _esc(v.count) +
          "</span> " +
          _esc(v.vno) +
          "</span>"
      )
      .join("") +
    "</div>"
  );
}

function _renderRamasCell(row) {
  const ramas = row.ramas || [];
  if (!ramas.length) {
    if (row.sin_inventario) {
      return '<span class="cortes-sin-map" title="Sin ONT IN SERVICE en inventario para este PON">Sin mapeo</span>';
    }
    const clientes = row.ont_total ?? 0;
    const lt = row.lt_name || row.olt || "";
    const oltUrl = lt ? "/dashboard/olt?lt=" + encodeURIComponent(lt) : "/dashboard/olt";
    const ponLbl = row.pon_label || (row.pon ? "PON " + row.pon : "este PON");
    if (clientes > 0) {
      return (
        '<a class="cortes-sin-rama-link" href="' +
        _esc(oltUrl) +
        '" target="_blank" rel="noopener noreferrer" title="Hay ' +
        clientes +
        " clientes IN SERVICE pero el inventario no devolvió path RATC/FATC. En OLT/LT expandí " +
        ponLbl +
        ' para ver las ramas.">' +
        "Sin RAMA · ver OLT</a>"
      );
    }
    return '<span class="muted" title="Sin path_atc en inventario">Sin RAMA</span>';
  }
  const maxShow = 3;
  const visible = ramas.slice(0, maxShow);
  const extra = ramas.length - visible.length;
  let html = '<div class="cortes-ramas-list">';
  visible.forEach((rama) => {
    const isFatc = rama.toUpperCase().indexOf("-FATC-") >= 0;
    const url = "/dashboard/rama?q=" + encodeURIComponent(rama);
    html +=
      '<a class="cortes-rama-link' +
      (isFatc ? " cortes-rama-link--fatc" : "") +
      '" href="' +
      _esc(url) +
      '" target="_blank" rel="noopener noreferrer">' +
      _esc(rama) +
      "</a>";
  });
  if (extra > 0) html += '<span class="cortes-rama-more muted">+' + extra + "</span>";
  html += "</div>";
  return html;
}

function _renderActions(row, compact) {
  const lt = row.lt_name || "";
  const oltUrl = "/dashboard/olt?lt=" + encodeURIComponent(lt);
  const caminoUrl =
    row.ramas && row.ramas[0] ? "/dashboard/camino-optico?q=" + encodeURIComponent(row.ramas[0]) : null;
  const cls = compact ? " cortes-actions--compact" : "";
  let html =
    '<div class="cortes-actions' +
    cls +
    '"><a class="btn btn-ghost btn-sm" href="' +
    _esc(oltUrl) +
    '" target="_blank" rel="noopener noreferrer">OLT</a>';
  if (caminoUrl) {
    html +=
      '<a class="btn btn-ghost btn-sm" href="' +
      _esc(caminoUrl) +
      '" target="_blank" rel="noopener noreferrer">Camino</a>';
  }
  if (row.ramas && row.ramas[0]) {
    html +=
      '<a class="btn btn-ghost btn-sm" href="/?q=' +
      encodeURIComponent(row.ramas[0]) +
      '" target="_blank" rel="noopener noreferrer">Potencias</a>';
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
  const child =
    opts.child
      ? " cortes-data-row--child" + (opts.nested ? " cortes-data-row--nested" : "")
      : "";
  const nuevo = _isNuevo(row) ? " cortes-data-row--nuevo" : "";
  const imp = row.impacto || "MODERADO";
  const impPon = row.impacto_pon || imp;
  const impactoRow =
    !opts.child && row.evento_simultaneo && imp !== "MODERADO"
      ? " cortes-data-row--" + imp.toLowerCase()
      : "";
  const clientes = row.ont_total ?? 0;
  const rowImp = row.evento_simultaneo ? imp : "MODERADO";
  const clientesCls =
    rowImp === "EMERGENCIA"
      ? "cortes-clientes--emergencia"
      : rowImp === "URGENTE"
        ? "cortes-clientes--urgente"
        : clientes > 0
          ? "cortes-clientes--hit"
          : "muted";
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
  return (
    '<tr class="cortes-data-row' +
    child +
    nuevo +
    impactoRow +
    '">' +
    "<td>" +
    _renderCausaCell(row, { child: opts.child, group: opts.group }) +
    "</td>" +
    "<td>" +
    loc +
    "</td>" +
    '<td class="cortes-sitio cortes-col-sitio--optional">' +
    _esc(row.principal || "—") +
    "</td>" +
    '<td class="cortes-col-estado--optional">' +
    _renderEstadoCell(row) +
    "</td>" +
    '<td class="mono cortes-raised" title="Hora Argentina (ART)">' +
    _esc(_formatRaised(row.raised)) +
    "</td>" +
    '<td class="mono cortes-cleared cortes-col-cleared--optional" title="Hora Argentina (ART)">' +
    _esc(row.cleared ? _formatRaised(row.cleared) : "—") +
    "</td>" +
    '<td class="cortes-col-clientes ' +
    clientesCls +
    '">' +
    '<div class="cortes-clientes-cell"><span class="cortes-clientes-n">' +
    _esc(clientes) +
    "</span>" +
    _renderImpactoBadge(row, { groupChild: opts.child }) +
    "</div></td>" +
    "<td>" +
    _renderVnoCell(row.vno_list) +
    "</td>" +
    "<td>" +
    _renderRamasCell(row) +
    "</td>" +
    "<td>" +
    _renderActions(row, true) +
    "</td>" +
    "</tr>"
  );
}

function _displayRowsForMode() {
  if (viewMode === "grupo") {
    return { mode: "grupo", sitios: _buildSitioGrupos(allGrupos || []) };
  }
  return { mode: "pon", items: allItems };
}

function _totalPagesForDisplay() {
  const d = _displayRowsForMode();
  if (d.mode === "grupo") return d.sitios.length ? Math.ceil(d.sitios.length / pageSize) : 0;
  return d.items.length ? Math.ceil(d.items.length / pageSize) : 0;
}

function _updatePager() {
  const pager = document.getElementById("cortes-pager");
  const info = document.getElementById("cortes-page-info");
  const prev = document.getElementById("cortes-page-prev");
  const next = document.getElementById("cortes-page-next");
  const pages = _totalPagesForDisplay();
  const d = _displayRowsForMode();
  const total = d.mode === "grupo" ? d.sitios.length : d.items.length;
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
  const d = _displayRowsForMode();
  const total = d.mode === "grupo" ? d.sitios.length : d.items.length;

  if (!total) {
    tbody.innerHTML = "";
    table.classList.add("is-hidden");
    if (empty) empty.hidden = false;
    _updatePager();
    _updateVisibleCount([]);
    return;
  }

  if (empty) empty.hidden = true;
  table.classList.remove("is-hidden");

  const start = currentPage * pageSize;
  let html = "";

  if (d.mode === "grupo") {
    const pageSitios = d.sitios.slice(start, start + pageSize);
    pageSitios.forEach((site) => {
      const ltGrupos = site.lt_grupos || [];
      const multiLt = ltGrupos.length > 1;
      if (multiLt) {
        html += _renderSitioGroupRow(site);
        ltGrupos.forEach((g) => {
          html += _renderLtSubGroupRow(g);
          (g.items || []).forEach((row) => {
            html += _renderDataRow(row, { child: true, group: g, nested: true });
          });
        });
      } else if (ltGrupos[0]) {
        const g = ltGrupos[0];
        html += _renderSitioLtGroupRow(g);
        (g.items || []).forEach((row) => {
          html += _renderDataRow(row, { child: true, group: g });
        });
      }
    });
    _updateVisibleCount(pageSitios);
  } else {
    const pageItems = d.items.slice(start, start + pageSize);
    html = pageItems.map((row) => _renderDataRow(row)).join("");
    _updateVisibleCount(d.items);
  }

  tbody.innerHTML = html;
  _updatePager();
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
  allGrupos = [];
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

function _setViewMode(mode) {
  viewMode = mode === "grupo" ? "grupo" : "pon";
  const ponBtn = document.getElementById("cortes-view-pon");
  const grupoBtn = document.getElementById("cortes-view-grupo");
  if (ponBtn) {
    ponBtn.classList.toggle("is-active", viewMode === "pon");
    ponBtn.setAttribute("aria-selected", viewMode === "pon" ? "true" : "false");
  }
  if (grupoBtn) {
    grupoBtn.classList.toggle("is-active", viewMode === "grupo");
    grupoBtn.setAttribute("aria-selected", viewMode === "grupo" ? "true" : "false");
  }
  _syncTableLayout();
  currentPage = 0;
  _renderTablePage();
  if (!_restoringState) _saveStateSoon();
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
    impacto: document.getElementById("cortes-impacto")?.value || "ALL",
    viewMode,
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
      estado: typeof parsed.estado === "string" ? parsed.estado : "activas",
      causa: typeof parsed.causa === "string" ? parsed.causa : "ALL",
      principal: typeof parsed.principal === "string" ? parsed.principal : "ALL",
      vno: typeof parsed.vno === "string" ? parsed.vno : "ALL",
      sort: typeof parsed.sort === "string" ? parsed.sort : "reciente",
      fechaDia: typeof parsed.fechaDia === "string" ? parsed.fechaDia : "",
      impacto: typeof parsed.impacto === "string" ? parsed.impacto : "ALL",
      viewMode: parsed.viewMode === "pon" ? "pon" : "grupo",
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
  if (!st) return;
  _restoringState = true;
  const q = document.getElementById("cortes-q");
  if (q && st.q) q.value = st.q;
  const estadoSel = document.getElementById("cortes-estado");
  if (estadoSel && st.estado) estadoSel.value = st.estado;
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
    _ensureFechaHoy();
  }
  const impactoSel = document.getElementById("cortes-impacto");
  if (impactoSel && st.impacto) impactoSel.value = st.impacto;
  if (st.pageSize) pageSize = st.pageSize;
  const ps = document.getElementById("cortes-page-size");
  if (ps && st.pageSize) ps.value = String(st.pageSize);
  if (st.viewMode) viewMode = st.viewMode;
  if (typeof st.currentPage === "number") currentPage = st.currentPage;
  const refreshSel = document.getElementById("cortes-refresh");
  if (refreshSel && st.refreshMs) {
    refreshSel.value = String(st.refreshMs);
    _saveRefreshMs(st.refreshMs);
  }
  _setViewMode(viewMode);
  _restoringState = false;
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
  _setCortesFechaIso(_todayArtIso());
  const impactoSel = document.getElementById("cortes-impacto");
  if (impactoSel) impactoSel.value = "ALL";
  const refreshSel = document.getElementById("cortes-refresh");
  if (refreshSel) refreshSel.value = "0";
  _applyAutoRefresh();
  currentPage = 0;
  _setViewMode("grupo");
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

  const exportBtn = document.getElementById("btn-cortes-export");
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
  return fetch("/api/cortes-rama?" + params.toString())
    .then((r) => r.json().then((data) => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (!ok || data.error) {
        _showCortesError(data.error || "Error consultando cortes");
        if (exportBtn) exportBtn.disabled = true;
        return;
      }
      lastPayload = data;
      allItems = data.items || [];
      allGrupos = data.grupos || [];
      _syncTableLayout();
      if (!preservePage && !_restoringState) currentPage = 0;
      _populateSelect(document.getElementById("cortes-principal"), data.principals, "Todos los sitios");
      _populateSelect(document.getElementById("cortes-vno"), data.vnos, "Todos los VNO");
      _updateKpis(data, allItems);
      _renderVnoResumen(data.vno_resumen);
      _renderTablePage();
      if (exportBtn) exportBtn.disabled = !allItems.length;
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
      if (!silent && eventos.some((ev) => ev.impacto === "EMERGENCIA")) {
        const top = eventos[0];
        _cortesToast(
          "Evento masivo: " + top.cortes + " PON · " + top.clientes + " clientes (" + top.minute + ")",
          { variant: "error", durationMs: 6000, create: true, id: "cortes-evento-toast" }
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

function exportCortesCsv() {
  const params = _buildFetchParams();
  params.set("limit", "2000");
  window.location.href = "/dashboard/cortes-rama/export.csv?" + params.toString();
}

function _onCortesFilterChange() {
  currentPage = 0;
  if (!_restoringState) _saveStateSoon();
  fetchCortes({ fresh: true });
}

function initCortesRamaDashboard() {
  if (_cortesPageReady) return;
  _cortesPageReady = true;

  document.getElementById("btn-cortes-export")?.addEventListener("click", exportCortesCsv);
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
  document.getElementById("cortes-view-pon")?.addEventListener("click", () => _setViewMode("pon"));
  document.getElementById("cortes-view-grupo")?.addEventListener("click", () => _setViewMode("grupo"));
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
  document.getElementById("cortes-sort")?.addEventListener("change", _onCortesFilterChange);
  ["cortes-impacto"].forEach((id) => {
    document.getElementById(id)?.addEventListener("change", _onCortesFilterChange);
  });
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
  try {
    _restoreState();
  } catch (_err) {
    /* estado de sesión corrupto no debe impedir la consulta inicial */
  }
  _ensureFechaHoy();
  _syncTableLayout();
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
