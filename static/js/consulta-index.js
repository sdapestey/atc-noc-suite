/** Lógica UI de consulta índice (potencias, PON, filtros, Altiplano). */
(function () {
  "use strict";
  var cfg = window.__CONSULTA_INDEX_CFG__ || {};
  var clearUrlInd = cfg.clearUrlInd || "/";
  var clearUrlMas = cfg.clearUrlMas || "/";

  function _consultaPotenciasParallelMax() {
    var n = parseInt(cfg.potenciasParallelMax, 10);
    return Number.isFinite(n) && n > 0 ? n : 32;
  }
let _activeOperador = "ALL";
let _activeFatStatus = "ALL";
function toast(msg, opts) {
  if (!window.NocToast) return;
  const options = Object.assign({ durationMs: 1800 }, opts || {});
  window.NocToast.show("toast", msg, options);
}

function _normFatStatus(s) {
  return (s || "").trim().toUpperCase();
}

const _OPERADOR_CONSULTA_CANON = {
  TASA: "TASA",
  DIRECTV: "DIRECTV",
  METROTEL: "METROTEL",
  IPLAN: "IPLAN",
  ATC: "ATC",
  SION: "SION",
};

function _canonicalOperadorConsulta(op) {
  const raw = (op || "").trim();
  if (!raw || raw === "-" || raw === "—" || raw === "0") return null;
  const k = raw.toUpperCase().replace(/\s+/g, "");
  if (k === "NONE" || k === "NULL") return null;
  return _OPERADOR_CONSULTA_CANON[k] || null;
}

function aplicarFiltrosConsulta() {
  const op = _activeOperador;
  const st = _normFatStatus(_activeFatStatus);
  document.querySelectorAll("tr[data-operador]").forEach(row => {
    const rop = row.dataset.operador || "";
    const canonOp = _canonicalOperadorConsulta(rop);
    const rst = _normFatStatus(row.dataset.fatStatus);
    const opOk =
      op === "ALL" ||
      (canonOp && canonOp === op);
    const stOk = st === "ALL" || rst === st;
    row.style.display = opOk && stOk ? "" : "none";
  });
  document.querySelectorAll("[data-chip-operador]").forEach(btn => {
    const v = btn.getAttribute("data-chip-operador");
    btn.setAttribute("aria-pressed", v === op ? "true" : "false");
  });
}

function filtrarOperador(op) {
  _activeOperador = op;
  aplicarFiltrosConsulta();
}

function consultaSetBtnConsultando(btn, loading, defaultLabel) {
  if (!btn) return;
  const label = defaultLabel || "Consultar RX";
  if (loading) {
    if (!btn.dataset.consultaBtnLabel) {
      const preset = (btn.getAttribute("data-consulta-btn-label") || "").trim();
      btn.dataset.consultaBtnLabel =
        preset || (btn.textContent || "").trim() || label;
    }
    btn.disabled = true;
    btn.classList.add("pot-btn-loading");
    btn.innerHTML = "";
    const inner = document.createElement("span");
    inner.className = "pot-btn-loading-inner";
    const sp = document.createElement("span");
    sp.className = "pot-txrx-spin";
    sp.setAttribute("aria-hidden", "true");
    const lab = document.createElement("span");
    lab.className = "pot-txrx-label";
    lab.textContent = "Consultando";
    inner.appendChild(sp);
    inner.appendChild(lab);
    btn.appendChild(inner);
    btn.setAttribute("aria-busy", "true");
    return;
  }
  btn.disabled = false;
  btn.classList.remove("pot-btn-loading");
  btn.removeAttribute("aria-busy");
  btn.textContent = btn.dataset.consultaBtnLabel || label;
}

function _consultaMarkPotenciasLoadedIfMasivo(root) {
  if (!root || !root.classList.contains("consulta-section--multi")) return;
  if (window.ConsultaMasivoUi && window.ConsultaMasivoUi.markPotenciasLoaded) {
    window.ConsultaMasivoUi.markPotenciasLoaded(root);
  }
}

function _consultaResetAlarmasFetched(pre) {
  if (pre) _consultaAlarmasFetched.delete(pre);
}

function _consultaMarkAlarmasFetched(pre) {
  if (pre) _consultaAlarmasFetched.set(pre, true);
}

function _consultaAlarmasYaFetched(pre) {
  return Boolean(pre && _consultaAlarmasFetched.get(pre));
}

function consultaRecargarPotenciasDesdeBtn(btn) {
  const sec = btn && btn.closest ? btn.closest(".consulta-section") : null;
  if (!sec) return;
  const tok = sec.getAttribute("data-query-token") || "";
  if (!tok) return;
  _consultaResetAlarmasFetched(sec.getAttribute("data-section-prefix") || "");
  if (window.ConsultaMasivoUi && window.ConsultaMasivoUi.clearPotenciasLoaded) {
    window.ConsultaMasivoUi.clearPotenciasLoaded(sec);
  }
  cargarPotenciasSeccion(tok, sec);
}

function consultaRecargarPotenciasSubcto(btn) {
  const cto = ((btn && btn.getAttribute("data-cto")) || "").trim();
  const sec = btn && btn.closest ? btn.closest(".consulta-section") : null;
  const block = btn && btn.closest ? btn.closest(".consulta-cto-block") : null;
  if (!cto || !sec || !block) return;
  _consultaResetAlarmasFetched(sec.getAttribute("data-section-prefix") || "");
  cargarPotenciasSeccion(cto, sec, block);
}

function _hasPower(v) {
  return window.NocPower.hasPowerValue(v);
}

function _formatPowerDbm(v) {
  return window.NocPower.formatPowerDbm(v);
}

function _applyPotenciaDbmCelda(el, v, hasSubscriber) {
  if (!el) return;
  el.classList.remove(
    "consulta-down-poll-counting",
    "consulta-potencia-loading",
    "olt-txrx-cell--loading",
    "loading"
  );
  el.removeAttribute("aria-busy");
  el.removeAttribute("aria-label");
  window.NocPower.applyPowerDbmCell(el, v, hasSubscriber);
}

const _CONSULTA_POT_SPINNER_HTML =
  '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';

const _CONSULTA_SN_CHANGING_HTML =
  '<span class="olt-txrx-loading-wrap consulta-sn-changing-wrap" title="Cambiando SN…">' +
  '<span class="olt-txrx-cell-spin" aria-hidden="true"></span>' +
  '<span class="consulta-sn-changing-label">Cambiando</span></span>';

const _CONSULTA_SN_RELOAD_DELAY_MS = 3500;
/** Reconsulta tras cada respuesta sin lectura (sin cuenta regresiva en UI). */
const _CONSULTA_DOWN_POLL_MS = 800;
const _CONSULTA_MASIVO_DOWN_POLL_MS = 1000;
const _CONSULTA_PON_COMMITTED_GRACE_MS = 90000;
const _CONSULTA_OPER_COMMITTED_GRACE_MS = 90000;
const _CONSULTA_NV_REFRESH_MS = 120000;
const _CONSULTA_NV_POLL_INTERVAL_MS = 12000;
const _CONSULTA_PON_POST_REFRESH_MS = 1500;
const _CONSULTA_PON_POST_REFRESH_EXTRA_MS = [4000, 12000];
const _consultaDownPollers = new Map();
/** Detalle AID: tras la primera respuesta de ``/potencias``, alarmas no vuelven a spinner en poll TX/RX. */
const _consultaAlarmasFetched = new Map();
const _consultaPonCommitted = new Map();
const _consultaOperCommitted = new Map();
const _consultaNvRefreshUntil = new Map();
const _consultaPotenciasInflight = new Map();
const _consultaSectionPotenciaBtnLocks = new Map();

function _consultaPotenciaBtnScope(root) {
  if (!root) return null;
  return root.closest ? root.closest(".consulta-section") || root : root;
}

function _consultaPotenciaActionBtns(container) {
  if (!container || !container.querySelectorAll) return [];
  return Array.from(
    container.querySelectorAll(
      'button[onclick*="consultaRecargarPotenciasDesdeBtn"], button[onclick*="consultaRecargarPotenciasSubcto"]'
    )
  );
}

function _consultaAcquireSectionPotenciaBtnsLoading(root) {
  const scope = _consultaPotenciaBtnScope(root);
  if (!scope) return;
  const key = scope.getAttribute("data-section-prefix") || scope.id || "";
  if (!key) return;
  const n = (_consultaSectionPotenciaBtnLocks.get(key) || 0) + 1;
  _consultaSectionPotenciaBtnLocks.set(key, n);
  _consultaPotenciaActionBtns(scope).forEach((btn) => consultaSetBtnConsultando(btn, true));
}

function _consultaReleaseSectionPotenciaBtnsLoading(root) {
  const scope = _consultaPotenciaBtnScope(root);
  if (!scope) return;
  const key = scope.getAttribute("data-section-prefix") || scope.id || "";
  if (!key) return;
  const n = Math.max(0, (_consultaSectionPotenciaBtnLocks.get(key) || 1) - 1);
  if (n === 0) {
    _consultaSectionPotenciaBtnLocks.delete(key);
    _consultaPotenciaActionBtns(scope).forEach((btn) => consultaSetBtnConsultando(btn, false));
  } else {
    _consultaSectionPotenciaBtnLocks.set(key, n);
  }
}

function _setConsultaSnChanging(snEl, btn, loading) {
  if (!snEl) return;
  if (loading) {
    snEl.classList.add("consulta-sn-changing");
    snEl.setAttribute("aria-busy", "true");
    snEl.setAttribute("aria-label", "Cambiando SN");
    snEl.innerHTML = _CONSULTA_SN_CHANGING_HTML;
    if (btn) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
    }
    return;
  }
  snEl.classList.remove("consulta-sn-changing");
  snEl.removeAttribute("aria-busy");
  snEl.removeAttribute("aria-label");
  if (btn) {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
  }
}

function _isConsultaDetallePotenciaPar(pre) {
  const tx = _potCell(pre, "tx");
  const rx = _potCell(pre, "rx");
  if (!tx || !rx) return false;
  const pfx = pre ? pre + "-" : "";
  return tx.id === pfx + "tx" && rx.id === pfx + "rx";
}

/** RAMA/CTO: una carga automática; reconsulta solo con «Consultar RX». AID (detalle): sin cambio. */
function _consultaPotenciasTokenEsRamaOCto(valor) {
  const v = String(valor || "").trim().toUpperCase();
  return v.includes("RATC") || v.includes("FATC");
}

/** True si la celda muestra un valor de potencia real (no DOWN ni cuenta regresiva). */
function _consultaPotenciaCeldaHasReading(el) {
  if (!el) return false;
  if (el.classList.contains("consulta-potencia-loading")) return false;
  if (el.classList.contains("consulta-down-poll-counting")) return false;
  if (el.querySelector(".consulta-down-poll-countdown")) return false;
  const t = String(el.textContent || "").trim();
  if (!t || t === "-" || t.toUpperCase() === "DOWN") return false;
  return window.NocPower.hasPowerValue(window.NocPower.parseRxDbm(t));
}

function _consultaPotenciasDetalleListas(pre) {
  const tx = _potCell(pre, "tx");
  const rx = _potCell(pre, "rx");
  return (
    _consultaPotenciaCeldaHasReading(tx) && _consultaPotenciaCeldaHasReading(rx)
  );
}

function _consultaMasivoPotenciasPendientes(scope, pfx) {
  if (!scope || !scope.querySelectorAll) return false;
  let pending = false;
  scope.querySelectorAll("tr[data-aid][data-fat-status]").forEach((tr) => {
    if (!_filaTieneAidReal(tr) || _filaSaltaPotencias(tr)) return;
    if (_normFatStatus(tr.getAttribute("data-fat-status")) !== "IN SERVICE") return;
    const aid = tr.getAttribute("data-aid");
    const rx = document.getElementById(pfx + "rx-" + aid);
    if (!_consultaPotenciaCeldaHasReading(rx)) {
      pending = true;
    }
  });
  return pending;
}

/** True si la sección masiva aún necesita cargar potencias (expuesto para consulta-masivo-ui). */
function _consultaSectionPotenciasPendientes(root) {
  if (!root) return true;
  const pre = root.getAttribute("data-section-prefix") || "";
  const pfx = pre ? pre + "-" : "";
  return _consultaMasivoPotenciasPendientes(root, pfx);
}

/** True mientras falte TX/RX con lectura válida (solo consulta por AID / detalle). */
function _consultaSectionNeedsPotenciaPoll(pre, root, scopeEl) {
  if (_isConsultaDetallePotenciaPar(pre)) {
    return !_consultaPotenciasDetalleListas(pre);
  }
  const tok = root ? root.getAttribute("data-query-token") || "" : "";
  if (_consultaPotenciasTokenEsRamaOCto(tok)) return false;
  const pfx = pre ? pre + "-" : "";
  const scope =
    scopeEl && scopeEl.querySelectorAll ? scopeEl : root;
  return _consultaMasivoPotenciasPendientes(scope, pfx);
}

function _consultaIsNvStatusSlot(el) {
  if (!el) return false;
  return (
    el.classList.contains("consulta-nv-oper-slot") ||
    el.classList.contains("consulta-nv-admin-slot") ||
    el.classList.contains("consulta-nv-pon-slot")
  );
}

function _consultaNvSlotHasContent(el) {
  if (!el) return false;
  return Boolean(
    el.querySelector(".consulta-nv-status__chip") ||
    el.querySelector(".consulta-pon-btn")
  );
}

function _consultaDownPollDelayMs(mode, root) {
  if (mode === "nv") return _CONSULTA_NV_POLL_INTERVAL_MS;
  if (root && root.classList.contains("consulta-section--multi")) {
    return _CONSULTA_MASIVO_DOWN_POLL_MS;
  }
  return _CONSULTA_DOWN_POLL_MS;
}

function _consultaRefreshPotenciaCellsLoading(cells, root) {
  const tok = root ? root.getAttribute("data-query-token") || "" : "";
  const sinReconsultaAuto = _consultaPotenciasTokenEsRamaOCto(tok);
  cells.forEach((el) => {
    if (!el || (el.id && el.id.endsWith("-alarmas"))) return;
    if (_consultaIsNvStatusSlot(el)) return;
    const tr = el.closest("tr");
    if (tr && (_filaSaltaPotencias(tr) || !_filaTieneAidReal(tr))) {
      _setConsultaPotenciaLoading(el, false);
      return;
    }
    if (_consultaPotenciaCeldaHasReading(el)) {
      _setConsultaPotenciaLoading(el, false);
    } else if (sinReconsultaAuto) {
      _setConsultaPotenciaLoading(el, false);
    } else {
      _setConsultaPotenciaLoading(el, true);
    }
  });
}

/** Poll «full»: reconsulta hasta lectura TX/RX. Poll «nv»: refresco silencioso de estado NV. */
function _consultaDetallePollShouldContinue(pre, root, scopeEl) {
  if (!_consultaIsDownPollActive(root)) return false;
  const state = _consultaDownPollers.get(
    root.id || root.getAttribute("data-section-prefix") || ""
  );
  if (state && state.mode === "nv") {
    if (!_isConsultaDetallePotenciaPar(pre)) return false;
    return Date.now() < (_consultaNvRefreshUntil.get(pre) || 0);
  }
  return _consultaSectionNeedsPotenciaPoll(pre, root, scopeEl);
}

function _consultaArmNvRefresh(pre) {
  if (!pre) return;
  _consultaNvRefreshUntil.set(pre, Date.now() + _CONSULTA_NV_REFRESH_MS);
}

function _consultaIsDownPollActive(root) {
  if (!root) return false;
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  return Boolean(key && _consultaDownPollers.has(key));
}

function _consultaDetallePollPrepUI(pre, root, scopeEl) {
  if (!_isConsultaDetallePotenciaPar(pre)) return;
  if (!_consultaSectionNeedsPotenciaPoll(pre, root, scopeEl)) return;
  if (_consultaAlarmasYaFetched(pre)) return;
  _setAlarmasDetalleRowVisible(pre, true);
}

function _consultaStopDownPoll(root) {
  if (!root) return;
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  if (!key) return;
  const state = _consultaDownPollers.get(key);
  if (state && state.timerId) clearTimeout(state.timerId);
  _consultaDownPollers.delete(key);
}

function _consultaStopAllDownPolls() {
  _consultaDownPollers.forEach((state) => {
    if (state && state.timerId) clearTimeout(state.timerId);
  });
  _consultaDownPollers.clear();
}

function _consultaRunDownPollCycle(root, valor, scopeEl) {
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  const pre = root.getAttribute("data-section-prefix") || "";
  const state = _consultaDownPollers.get(key);
  if (!state) return;
  const scope =
    scopeEl && scopeEl.querySelectorAll ? scopeEl : root;
  if (!_consultaDetallePollShouldContinue(pre, root, scope)) {
    _consultaStopDownPoll(root);
    return;
  }

  const tok = (root.getAttribute("data-query-token") || valor || "").trim();
  if (!tok) {
    _consultaStopDownPoll(root);
    return;
  }
  const silentNv = state.mode === "nv";
  const pollMode = state.mode;
  Promise.resolve(
    cargarPotenciasSeccion(tok, root, scope, { silentNvRefresh: silentNv })
  ).finally(() => {
    if (!_consultaDownPollers.has(key)) return;
    if (!_consultaDetallePollShouldContinue(pre, root, scope)) {
      _consultaStopDownPoll(root);
      return;
    }
    const delay = _consultaDownPollDelayMs(pollMode, root);
    const timerId = setTimeout(
      () => _consultaRunDownPollCycle(root, valor, scope),
      delay
    );
    _consultaDownPollers.set(key, { timerId: timerId, mode: pollMode });
  });
}

function _consultaSyncDownPoll(root, valor, scopeEl) {
  if (!root) return;
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  const pre = root.getAttribute("data-section-prefix") || "";
  const scope =
    scopeEl && scopeEl.querySelectorAll ? scopeEl : root;
  const nvUntil = _consultaNvRefreshUntil.get(pre) || 0;
  const wantNvRefresh =
    _isConsultaDetallePotenciaPar(pre) && Date.now() < nvUntil;
  const needPotencias = _consultaSectionNeedsPotenciaPoll(pre, root, scope);

  if (!needPotencias && !wantNvRefresh) {
    _consultaStopDownPoll(root);
    return;
  }
  if (_consultaDownPollers.has(key)) return;

  const mode = needPotencias ? "full" : "nv";
  _consultaDownPollers.set(key, { timerId: null, mode: mode });
  _consultaRunDownPollCycle(root, valor, scope);
}

function _consultaRecargarBusqueda() {
  const modo = (document.getElementById("consulta_modo") || {}).value || "individual";
  const value = _consultaExportValue();
  const form = document.createElement("form");
  form.method = "POST";
  form.action = window.location.pathname || "/";
  form.style.display = "none";
  const modoInp = document.createElement("input");
  modoInp.type = "hidden";
  modoInp.name = "consulta_modo";
  modoInp.value = modo;
  form.appendChild(modoInp);
  if (value) {
    const valInp = document.createElement("input");
    valInp.type = "hidden";
    valInp.name = "value";
    valInp.value = value;
    form.appendChild(valInp);
  }
  document.body.appendChild(form);
  form.submit();
}

function _setConsultaPotenciaLoading(el, loading) {
  if (!el) return;
  if (loading) {
    el.classList.remove("consulta-down-poll-counting");
    el.classList.add("consulta-potencia-loading");
    el.classList.remove("loading", "status-down", "status-up");
    el.setAttribute("aria-busy", "true");
    el.setAttribute("aria-label", "Cargando");
    el.textContent = "";
    el.innerHTML = _CONSULTA_POT_SPINNER_HTML;
    return;
  }
  el.classList.remove("consulta-potencia-loading", "consulta-down-poll-counting", "loading");
  el.removeAttribute("aria-busy");
  el.removeAttribute("aria-label");
}

function _escHtmlAlarmas(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _severityAlarmasLabel(sev) {
  const s = String(sev || "").trim().toLowerCase();
  if (!s) return "?";
  return s.charAt(0).toUpperCase();
}

function _severityAlarmasNombre(sev) {
  const s = String(sev || "").trim().toLowerCase();
  if (!s) return "—";
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function _formatAlarmasUtc(iso) {
  const s = String(iso || "").trim();
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const pad = (n) => String(n).padStart(2, "0");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return (
    pad(d.getUTCDate()) +
    " " +
    months[d.getUTCMonth()] +
    " " +
    d.getUTCFullYear() +
    " " +
    pad(d.getUTCHours()) +
    ":" +
    pad(d.getUTCMinutes()) +
    ":" +
    pad(d.getUTCSeconds())
  );
}

function _renderAlarmaDetalleHtml(a) {
  const sev = _escHtmlAlarmas(a.severity || "");
  const typ = _escHtmlAlarmas(a.type || "—");
  const res = _escHtmlAlarmas(a.resource || "—");
  const info = _escHtmlAlarmas(a.text || "—");
  const mainDev = _escHtmlAlarmas(a.main_device || "—");
  const raised = _escHtmlAlarmas(_formatAlarmasUtc(a.raised));
  const cleared = a.cleared
    ? _escHtmlAlarmas(_formatAlarmasUtc(a.cleared))
    : "—";
  return (
    '<div class="consulta-alarmas-block"><div class="consulta-alarmas-table-wrap"><table class="consulta-alarmas-table"><thead><tr>' +
    "<th>Severidad</th><th>Raised</th><th>Cleared</th><th>Recurso</th><th>Tipo</th><th>Info adicional</th><th>OLT</th>" +
    "</tr></thead><tbody><tr>" +
    '<td class="consulta-alarmas-td-sev"><span class="consulta-alarmas-sev consulta-alarmas-sev--' +
    sev.toLowerCase() +
    '" title="' +
    _escHtmlAlarmas(_severityAlarmasNombre(a.severity)) +
    '">' +
    _severityAlarmasLabel(a.severity) +
    "</span> " +
    '<span class="consulta-alarmas-sev-name">' +
    _escHtmlAlarmas(_severityAlarmasNombre(a.severity)) +
    "</span></td>" +
    '<td class="mono consulta-alarmas-td-ts">' +
    raised +
    "</td>" +
    '<td class="mono consulta-alarmas-td-ts">' +
    cleared +
    "</td>" +
    '<td class="mono consulta-alarmas-td-res">' +
    res +
    "</td>" +
    "<td><strong>" +
    typ +
    "</strong></td>" +
    '<td class="consulta-alarmas-td-info">' +
    info +
    "</td>" +
    '<td class="mono">' +
    mainDev +
    "</td>" +
    "</tr></tbody></table></div></div>"
  );
}

function _alarmasDetalleRow(pre) {
  const el = _potCell(pre, "alarmas");
  return el ? el.closest("tr") : null;
}

function _setAlarmasDetalleRowVisible(pre, visible) {
  const row = _alarmasDetalleRow(pre);
  if (row) row.hidden = !visible;
}

function _nvStatusEl(pre) {
  return document.getElementById((pre ? pre + "-" : "") + "nv-status");
}

function _nvOperEl(pre) {
  return document.getElementById((pre ? pre + "-" : "") + "nv-oper");
}

function _nvPonEl(pre) {
  return document.getElementById((pre ? pre + "-" : "") + "nv-pon");
}

function _nvAdminEl(pre) {
  return document.getElementById((pre ? pre + "-" : "") + "nv-admin");
}

function _normalizeNvHealthIso(iso) {
  let s = String(iso || "").trim();
  if (!s) return "";
  const m = s.match(/^(.+)([+-])(\d{2})(\d{2})$/);
  if (m && m[1].includes("T")) {
    s = m[1] + m[2] + m[3] + ":" + m[4];
  }
  return s;
}

function _formatNvHealthAgo(iso) {
  const s = _normalizeNvHealthIso(iso);
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return min + (min === 1 ? " minute ago" : " minutes ago");
  const hr = Math.floor(min / 60);
  if (hr < 48) return hr + (hr === 1 ? " hour ago" : " hours ago");
  const day = Math.floor(hr / 24);
  return day + (day === 1 ? " day ago" : " days ago");
}

function _nvOperLabel(oper) {
  const o = String(oper || "").trim().toUpperCase();
  if (o === "UP") return "Up";
  if (o === "DOWN") return "Down";
  return o || "—";
}

function _nvAdminLabel(admin) {
  const a = String(admin || "").trim().toUpperCase();
  if (a === "UNLOCKED") return "Unlocked";
  if (a === "LOCKED") return "Locked";
  return a || "—";
}

function _nvHealthClass(health) {
  const h = String(health || "").trim().toLowerCase();
  if (h === "healthy") return "good";
  if (h === "faulty" || h === "at risk" || h === "at-risk") return "bad";
  if (h === "suspended") return "warn";
  return "neutral";
}

function _nvOperClass(oper) {
  return String(oper || "").trim().toUpperCase() === "UP" ? "good" : "bad";
}

function _nvOperArrow(oper) {
  return String(oper || "").trim().toUpperCase() === "DOWN" ? "↓" : "↑";
}

function _nvOperFromAltiplano(nv) {
  const o = String((nv && nv.oper) || "").trim().toUpperCase();
  if (o === "UP" || o === "DOWN") return o;
  return "";
}

/**
 * Estado operacional: primero Altiplano (NV_STATUS.oper); si no viene, inferencia por potencia/PON.
 */
function _nvOperEffective(data, nvResolved) {
  const o = _nvOperFromAltiplano(nvResolved);
  if (o === "UP" || o === "DOWN") return o;

  const ponAdmin = String((nvResolved && nvResolved.pon_admin) || "")
    .trim()
    .toUpperCase();
  if (ponAdmin === "LOCKED") return "DOWN";

  const rx = data && data.RX;
  const tx = data && data.TX;
  if (typeof window !== "undefined" && window.NocPower) {
    const rxT = String(rx || "").trim().toUpperCase();
    const txT = String(tx || "").trim().toUpperCase();
    if (rxT === "DOWN" || txT === "DOWN") return "DOWN";
    if (window.NocPower.hasPowerValue(window.NocPower.parseRxDbm(rx))) {
      return "UP";
    }
  }
  return "";
}

function _consultaSetOperCommitted(pre, oper) {
  const o = String(oper || "").trim().toUpperCase();
  if (o !== "UP" && o !== "DOWN") return;
  _consultaOperCommitted.set(pre, { oper: o, ts: Date.now() });
}

/** Alinea oper con Altiplano; si el PON se acaba de bajar/subir, prioriza el estado esperado. */
function _consultaOperNvResolved(pre, nvObj) {
  const nv = Object.assign({}, nvObj || {});
  let server = String(nv.oper || "").trim().toUpperCase();

  const ponCommitted = _consultaPonCommitted.get(pre);
  if (
    ponCommitted &&
    Date.now() - ponCommitted.ts < _CONSULTA_PON_COMMITTED_GRACE_MS
  ) {
    if (ponCommitted.admin === "LOCKED") {
      nv.oper = "DOWN";
    } else if (ponCommitted.admin === "UNLOCKED") {
      if (server === "UP" || server === "DOWN") nv.oper = server;
      else nv.oper = "UP";
    }
  }

  server = String(nv.oper || "").trim().toUpperCase();
  const committed = _consultaOperCommitted.get(pre);
  if (committed && Date.now() - committed.ts < _CONSULTA_OPER_COMMITTED_GRACE_MS) {
    if (!server || server === committed.oper) {
      nv.oper = committed.oper;
    } else {
      _consultaSetOperCommitted(pre, server);
      nv.oper = server;
    }
  }
  return nv;
}

function _nvAdminClass(admin) {
  const a = String(admin || "").trim().toUpperCase();
  return a === "UNLOCKED" ? "good" : a === "LOCKED" ? "warn" : "neutral";
}

function _nvAdminIcon(admin) {
  const a = String(admin || "").trim().toUpperCase();
  return a === "LOCKED" ? "🔒" : "🔓";
}

function _ponIndexFromOntName(name) {
  const onu = String(name || "").trim();
  if (!onu) return "";
  const parts = onu.split("-");
  if (
    parts.length >= 4 &&
    parts[0].indexOf("BA_OLTA_") === 0 &&
    /^\d+$/.test(parts[2])
  ) {
    return parts[2];
  }
  const m = onu.match(/-(\d+)$/);
  return m ? m[1] : "";
}

function _consultaSectionOnt(pre) {
  const wrap = _nvStatusEl(pre);
  const section = wrap && wrap.closest ? wrap.closest(".consulta-section") : null;
  if (section) return String(section.getAttribute("data-nv-ont") || "").trim();
  const byPrefix = document.querySelector(
    '.consulta-section[data-section-prefix="' + pre + '"]'
  );
  return byPrefix ? String(byPrefix.getAttribute("data-nv-ont") || "").trim() : "";
}

/** Actualiza filas ONT (Postgres) / ONT (INP); una sola si coinciden. */
function _applyConsultaOntCompareRows(root, pfx, data) {
  if (!root || !pfx || !data) return;
  const dash = "—";
  const pgRaw = data.ONT_POSTGRES != null ? String(data.ONT_POSTGRES).trim() : "";
  const altRaw = data.ONT_ALTIPLANO != null ? String(data.ONT_ALTIPLANO).trim() : "";
  const match = data.ONT_MATCH === true;
  const pgShow = pgRaw || dash;
  const altShow = altRaw || dash;
  const ontTarget = (data.ONT != null ? String(data.ONT).trim() : "") || altRaw || pgRaw;

  const singleRow = document.getElementById(pfx + "ont-single-row");
  const pgRow = document.getElementById(pfx + "ont-postgres-row");
  const altRow = document.getElementById(pfx + "ont-altiplano-row");
  const singleVal = document.getElementById(pfx + "ont-value");
  const pgVal = document.getElementById(pfx + "ont-postgres-value");
  const altVal = document.getElementById(pfx + "ont-altiplano-value");

  const finishOntCell = (el, text) => {
    if (!el) return;
    el.innerText = text;
    el.classList.remove("consulta-potencia-loading");
    el.removeAttribute("aria-busy");
    el.removeAttribute("aria-label");
  };

  if (match && pgRaw) {
    if (singleRow) singleRow.hidden = false;
    if (pgRow) pgRow.hidden = true;
    if (altRow) altRow.hidden = true;
    if (singleVal) singleVal.innerText = pgRaw;
  } else if (pgRaw && altRaw) {
    if (singleRow) singleRow.hidden = true;
    if (pgRow) pgRow.hidden = false;
    if (altRow) altRow.hidden = false;
    finishOntCell(pgVal, pgShow);
    finishOntCell(altVal, altShow);
  } else if (pgRaw) {
    if (singleRow) singleRow.hidden = true;
    if (pgRow) pgRow.hidden = false;
    if (altRow) altRow.hidden = true;
    finishOntCell(pgVal, pgShow);
  } else if (altRaw) {
    if (singleRow) singleRow.hidden = true;
    if (pgRow) pgRow.hidden = true;
    if (altRow) altRow.hidden = false;
    finishOntCell(altVal, altShow);
  } else {
    if (singleRow) singleRow.hidden = true;
    if (pgRow) pgRow.hidden = false;
    if (altRow) altRow.hidden = true;
    finishOntCell(pgVal, dash);
  }

  if (ontTarget) {
    root.setAttribute("data-nv-ont", ontTarget);
    root.querySelectorAll("[data-ont-target]").forEach((btn) => {
      btn.setAttribute("data-ont-target", ontTarget);
    });
  }
}

function _applyConsultaVnoRows(pfx, data) {
  const dash = "—";
  const vno = data && data.ALTIPLANO_VNO != null ? String(data.ALTIPLANO_VNO).trim() : "";
  const tasa =
    data && data.ALTIPLANO_TASA_COMPOSITE != null
      ? String(data.ALTIPLANO_TASA_COMPOSITE).trim()
      : "";
  const operador =
    data && data.OPERADOR != null ? String(data.OPERADOR).trim().toUpperCase() : "";
  const aid = data && data.AID != null ? String(data.AID).trim() : "";
  const tasaMultiple = data && data.ALTIPLANO_TASA_COMPOSITE_MULTIPLE === true;
  const tasaHsi =
    data && data.ALTIPLANO_TASA_HSI && typeof data.ALTIPLANO_TASA_HSI === "object"
      ? data.ALTIPLANO_TASA_HSI
      : null;
  const vnoRow = document.getElementById(pfx + "altiplano-vno-row");
  const tasaRow = document.getElementById(pfx + "altiplano-tasa-row");
  const vnoVal = document.getElementById(pfx + "altiplano-vno-value");
  const tasaVal = document.getElementById(pfx + "altiplano-tasa-value");
  const finishCell = (el, text, show) => {
    if (!el) return;
    el.classList.remove("consulta-potencia-loading");
    el.removeAttribute("aria-busy");
    el.removeAttribute("aria-label");
    el.textContent = text || dash;
    const row = el.closest("tr");
    if (row) row.hidden = !show;
  };
  finishCell(vnoVal, vno || dash, Boolean(vno));
  if (vnoRow && !vno) vnoRow.hidden = true;

  const showTasa = Boolean(vno && tasa);
  if (tasaRow) tasaRow.hidden = !showTasa;
  if (tasaVal) {
    tasaVal.classList.remove("consulta-potencia-loading");
    tasaVal.removeAttribute("aria-busy");
    tasaVal.removeAttribute("aria-label");
    const targetSpan = tasaVal.querySelector(".consulta-tasa-composite-target");
    const actionsEl = tasaVal.querySelector(".consulta-tasa-composite-actions");
    if (targetSpan) targetSpan.textContent = tasa || dash;
    const canAct =
      showTasa &&
      operador === "TASA" &&
      !tasaMultiple &&
      tasa.indexOf(" · ") < 0 &&
      window.ConsultaTasaCompositeActions;
    if (actionsEl) {
      if (canAct) {
        actionsEl.hidden = false;
        window.ConsultaTasaCompositeActions.mount(actionsEl, {
          target: tasa,
          accessId: aid,
          operator: operador,
          tasaHsi: tasaHsi,
        });
      } else {
        actionsEl.hidden = true;
        actionsEl.innerHTML = "";
      }
    }
  }
}

/** ONT con nombre Altiplano suficiente para operar la partición PON. */
function _consultaOntOperable(ont) {
  const o = String(ont || "").trim();
  if (!o || o === "—") return false;
  return /BA_OLTA_/i.test(o);
}

function _consultaPonPortIndex(nv, ont) {
  const idx =
    String((nv && nv.pon_index) || "").trim() || _ponIndexFromOntName(ont);
  return idx || "?";
}

function _consultaSetPonCommitted(pre, status) {
  const s = String(status || "").trim().toUpperCase();
  if (s !== "LOCKED" && s !== "UNLOCKED") return;
  _consultaPonCommitted.set(pre, { admin: s, ts: Date.now() });
}

function _consultaPonNvFromDom(pre) {
  const slot = _nvPonEl(pre);
  const btn =
    slot && slot.querySelector
      ? slot.querySelector(".consulta-nv-pon-action-btn")
      : null;
  if (!btn) return {};
  const admin = String(btn.getAttribute("data-pon-admin") || "")
    .trim()
    .toUpperCase();
  if (admin !== "LOCKED" && admin !== "UNLOCKED") return {};
  return { pon_admin: admin };
}

/** Evita que recargas de /potencias pisen el estado PON recién confirmado. */
function _consultaPonNvResolved(pre, nvObj) {
  const nv = Object.assign({}, nvObj || {});
  const server = String(nv.pon_admin || "").trim().toUpperCase();
  const committed = _consultaPonCommitted.get(pre);
  const ont = _consultaSectionOnt(pre);
  if (committed && Date.now() - committed.ts < _CONSULTA_PON_COMMITTED_GRACE_MS) {
    if (!server || server === committed.admin) {
      nv.pon_admin = committed.admin;
    } else {
      _consultaSetPonCommitted(pre, server);
      nv.pon_admin = server;
    }
  } else if (!server) {
    const dom = _consultaPonNvFromDom(pre);
    if (dom.pon_admin) nv.pon_admin = dom.pon_admin;
  }
  if (!nv.pon_index && ont) {
    const idx = _ponIndexFromOntName(ont);
    if (idx) nv.pon_index = idx;
  }
  return nv;
}

function _consultaPonActionLabel(nv, ont) {
  const ponRaw = String((nv && nv.pon_admin) || "").trim().toUpperCase();
  const x = _consultaPonPortIndex(nv, ont);
  return ponRaw === "LOCKED"
    ? "PON " + x + " — Levantar puerto"
    : "PON " + x + " — Bajar puerto";
}

function _consultaOperChipHtml(operEff) {
  const o = String(operEff || "").trim().toUpperCase();
  if (o !== "UP" && o !== "DOWN") return "";
  const tip =
    "Estado operacional (Altiplano): " + _nvOperLabel(o);
  return (
    '<div class="consulta-nv-status__chip consulta-nv-status__chip--oper" title="' +
    _escHtmlAlarmas(tip) +
    '">' +
    '<span class="consulta-nv-status__icon consulta-nv-status__icon--' +
    _nvOperClass(o) +
    '" aria-hidden="true">' +
    _nvOperArrow(o) +
    "</span>" +
    '<span class="consulta-nv-status__text">' +
    _escHtmlAlarmas(_nvOperLabel(o)) +
    "</span></div>"
  );
}

function _consultaPonBtnHtml(nv, ont) {
  const ponLabel = _consultaPonActionLabel(nv || {}, ont);
  const ponRaw = String((nv && nv.pon_admin) || "").trim().toUpperCase();
  const ponLocked = ponRaw === "LOCKED";
  const ponBtnClass =
    "consulta-nv-pon-action-btn " +
    (ponLocked
      ? "consulta-nv-pon-action-btn--up"
      : "consulta-nv-pon-action-btn--down");
  const ponTitle =
    ponLocked
      ? "Levantar puerto PON " + _consultaPonPortIndex(nv, ont)
      : "Bajar puerto PON " + _consultaPonPortIndex(nv, ont);
  return (
    '<button type="button" class="' +
    ponBtnClass +
    '" title="' +
    _escHtmlAlarmas(ponTitle) +
    '" aria-label="' +
    _escHtmlAlarmas(ponLabel) +
    '" data-pon-admin="' +
    _escHtmlAlarmas(ponRaw || "UNLOCKED") +
    '" onclick="togglePonAdminDesdeUIBtn(this)">' +
    _escHtmlAlarmas(ponLabel) +
    "</button>"
  );
}

function _renderConsultaPonBtn(pre, nv) {
  const slot = _nvPonEl(pre);
  const ont = _consultaSectionOnt(pre);
  if (!slot || !_consultaOntOperable(ont)) {
    if (slot) {
      slot.innerHTML = "";
      slot.hidden = true;
    }
    return;
  }
  slot.hidden = false;
  slot.innerHTML = _consultaPonBtnHtml(_consultaPonNvResolved(pre, nv), ont);
}

function _applyNvOperDetalle(pre, data) {
  const operSlot = _nvOperEl(pre);
  if (!operSlot) return;
  _setConsultaPotenciaLoading(operSlot, false);
  const nv = data && data.NV_STATUS;
  const nvObj = nv && typeof nv === "object" ? nv : {};
  const nvResolved = _consultaOperNvResolved(pre, nvObj);
  const operEff = _nvOperEffective(data, nvResolved);
  const chip = _consultaOperChipHtml(operEff);
  operSlot.innerHTML = chip || "";
  operSlot.hidden = !chip;
}

function _applyNvAdminDetalle(pre, _nvObj) {
  const adminSlot = _nvAdminEl(pre);
  if (!adminSlot) return;
  adminSlot.innerHTML = "";
  adminSlot.hidden = true;
}

function _consultaShowNvStatusBar(pre, visible) {
  const wrap = _nvStatusEl(pre);
  if (wrap) wrap.hidden = !visible;
}

function _consultaInitNvStatusBar(pre) {
  const ont = _consultaSectionOnt(pre);
  if (!_consultaOntOperable(ont)) {
    _consultaShowNvStatusBar(pre, false);
    return;
  }
  _consultaShowNvStatusBar(pre, true);
  _renderConsultaPonBtn(pre, {});
}

function _applyNvStatusDetalle(pre, data) {
  const ont = _consultaSectionOnt(pre);
  const canTogglePon = _consultaOntOperable(ont);
  const nv = data && data.NV_STATUS;
  const nvObj = nv && typeof nv === "object" ? nv : {};
  const nvResolved = _consultaOperNvResolved(pre, nvObj);
  const operEff = _nvOperEffective(data, nvResolved);
  if (!canTogglePon && !operEff) {
    _consultaShowNvStatusBar(pre, false);
    return;
  }
  _consultaShowNvStatusBar(pre, true);
  _applyNvOperDetalle(pre, data);
  _renderConsultaPonBtn(pre, _consultaPonNvResolved(pre, nvObj));
  _applyNvAdminDetalle(pre, nvObj);
}

function togglePonAdminDesdeUI(accessId, operador, objectName, currentPonAdmin, btn) {
  let cur = String(currentPonAdmin || "").trim().toUpperCase();
  if (cur !== "LOCKED" && cur !== "UNLOCKED") {
    cur = "UNLOCKED";
  }
  const next = cur === "UNLOCKED" ? "LOCKED" : "UNLOCKED";
  const bajar = next === "LOCKED";
  const title = bajar ? "Bajar puerto PON" : "Levantar puerto PON";
  const confirmMsg = bajar
    ? "¿Confirmás bajar el puerto PON? Se caerán todas las ONT de ese PON."
    : "¿Confirmás levantar el puerto PON? Se desbloqueará la partición PON en Altiplano.";

  if (!window.runConsultaAltiplanoAction) {
    toast("Diálogo de autenticación no disponible");
    return;
  }

  const section =
    btn && btn.closest ? btn.closest(".consulta-section") : null;
  const token = section ? section.getAttribute("data-query-token") || "" : "";

  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }

  runConsultaAltiplanoAction({
    operador: "INP",
    loginDialog: {
      title: "Ingresar a Altiplano",
      message: "Credenciales de Altiplano (INP) para operar el puerto PON.",
      okLabel: "Ingresar",
    },
    dialog: {
      title: title,
      message: confirmMsg,
      danger: bajar,
      okLabel: bajar ? "Bajar PON" : "Levantar PON",
    },
    execute: (creds) =>
      fetch("/pon/admin-status", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          access_id: String(accessId || "").trim(),
          operador: String(operador || "").trim(),
          object_name: String(objectName || "").trim(),
          toggle: true,
          current_pon_admin: cur,
          altiplano_user: creds.username,
          altiplano_password: creds.password,
        }),
      }).then((r) => r.json().then((j) => ({ok: r.ok, status: r.status, json: j}))),
    onSuccess: (json) => {
      toast(json.message || "Estado PON actualizado");
      const pre = section
        ? section.getAttribute("data-section-prefix") || ""
        : "";
      const newAdmin = String(json.admin_status || next)
        .trim()
        .toUpperCase();
      if (pre) {
        _consultaSetPonCommitted(pre, newAdmin);
        _consultaSetOperCommitted(pre, bajar ? "DOWN" : "UP");
        _consultaArmNvRefresh(pre);
        _applyNvOperDetalle(pre, {
          NV_STATUS: {
            oper: bajar ? "DOWN" : "UP",
            pon_admin: newAdmin,
          },
          TX: null,
          RX: null,
        });
        _renderConsultaPonBtn(pre, {
          pon_admin: newAdmin,
          pon_index: json.pon_index || null,
        });
      }
      if (section && token) {
        const reload = () => cargarPotenciasSeccion(token, section, section);
        window.setTimeout(reload, _CONSULTA_PON_POST_REFRESH_MS);
        _CONSULTA_PON_POST_REFRESH_EXTRA_MS.forEach((ms) => {
          window.setTimeout(reload, ms);
        });
      }
    },
    onFinally: () => {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    },
  }).catch((err) => {
    if (err && err.message === "cancelled") return;
    if (err && err.authError) return;
    toast(err.message || "Error al cambiar estado PON");
  });
}

function togglePonAdminDesdeUIBtn(btn) {
  if (!btn) return;
  const section = btn.closest ? btn.closest(".consulta-section") : null;
  if (!section) {
    toast("Sección de consulta no encontrada");
    return;
  }
  const ont = (section.getAttribute("data-nv-ont") || "").trim();
  if (!ont || ont === "—") {
    toast("ONT no disponible para operar PON");
    return;
  }
  togglePonAdminDesdeUI(
    section.getAttribute("data-nv-access-id") || "",
    section.getAttribute("data-nv-operador") || "",
    ont,
    btn.getAttribute("data-pon-admin") || "",
    btn
  );
}

function toggleOntAdminDesdeUI(accessId, operador, objectName, currentAdmin, btn) {
  const cur = String(currentAdmin || "").trim().toUpperCase();
  if (cur !== "LOCKED" && cur !== "UNLOCKED") {
    toast("Estado admin no disponible");
    return;
  }
  const next = cur === "UNLOCKED" ? "LOCKED" : "UNLOCKED";
  const apagar = next === "LOCKED";
  const title = apagar ? "Apagar ONT (bloquear)" : "Encender ONT (desbloquear)";
  const confirmMsg = apagar
    ? "¿Confirmás apagar la ONT? Se bloqueará el admin en Altiplano."
    : "¿Confirmás encender la ONT? Se desbloqueará el admin en Altiplano.";

  if (!window.runConsultaAltiplanoAction) {
    toast("Diálogo de autenticación no disponible");
    return;
  }

  const section =
    btn && btn.closest ? btn.closest(".consulta-section") : null;
  const token = section ? section.getAttribute("data-query-token") || "" : "";

  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }

  runConsultaAltiplanoAction({
    operador: "INP",
    loginDialog: {
      title: "Ingresar a Altiplano",
      message: "Credenciales de Altiplano (INP) para operar la ONT.",
      okLabel: "Ingresar",
    },
    dialog: {
      title: title,
      message: confirmMsg,
      danger: apagar,
      okLabel: apagar ? "Apagar ONT" : "Encender ONT",
    },
    execute: (creds) =>
      fetch("/ont/admin-status", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          access_id: String(accessId || "").trim(),
          operador: String(operador || "").trim(),
          object_name: String(objectName || "").trim(),
          toggle: true,
          current_admin: cur,
          altiplano_user: creds.username,
          altiplano_password: creds.password,
        }),
      }).then((r) => r.json().then((j) => ({ok: r.ok, status: r.status, json: j}))),
    onSuccess: (json) => {
      toast(json.message || "Estado admin actualizado");
      if (section && token) {
        cargarPotenciasSeccion(token, section, section);
      }
    },
    onFinally: () => {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
    },
  }).catch((err) => {
    if (err && err.message === "cancelled") return;
    if (err && err.authError) return;
    toast(err.message || "Error al cambiar estado admin");
  });
}

function toggleOntAdminDesdeUIBtn(btn) {
  if (!btn) return;
  const section = btn.closest ? btn.closest(".consulta-section") : null;
  if (!section) {
    toast("Sección de consulta no encontrada");
    return;
  }
  const ont = (section.getAttribute("data-nv-ont") || "").trim();
  if (!ont || ont === "—") {
    toast("ONT no disponible para lock/unlock");
    return;
  }
  toggleOntAdminDesdeUI(
    section.getAttribute("data-nv-access-id") || "",
    section.getAttribute("data-nv-operador") || "",
    ont,
    btn.getAttribute("data-admin") || "",
    btn
  );
}

function _applyAlarmasDetalle(pre, data, root) {
  const _ensureAlarmasDetalleCell = () => {
    let el = _potCell(pre, "alarmas");
    if (el) return el;
    const rx = _potCell(pre, "rx");
    const tx = _potCell(pre, "tx");
    const ref = rx || tx;
    if (!ref) return null;
    const refTr = ref.closest("tr");
    if (!refTr || !refTr.parentNode) return null;

    const newTr = document.createElement("tr");
    newTr.id = pre + "-alarmas-row";

    const th = document.createElement("th");
    th.textContent = "Alarmas";

    const td = document.createElement("td");
    td.id = pre + "-alarmas";
    td.className = "consulta-alarmas-cell consulta-potencia-loading";
    td.setAttribute("aria-busy", "true");
    td.setAttribute("aria-label", "Cargando");
    td.innerHTML = _CONSULTA_POT_SPINNER_HTML;

    newTr.appendChild(th);
    newTr.appendChild(td);
    refTr.parentNode.insertBefore(newTr, refTr.nextSibling);
    return td;
  };

  const el = _ensureAlarmasDetalleCell();
  if (!el) return;
  _setConsultaPotenciaLoading(el, false);
  if (!data || typeof data !== "object") {
    _setAlarmasDetalleRowVisible(pre, false);
    return;
  }
  const list = Array.isArray(data.ALARMAS) ? data.ALARMAS : [];
  if (Array.isArray(data.ALARMAS)) {
    _consultaMarkAlarmasFetched(pre);
  }
  if (data.alarmas_label === "Sin Alarmas") {
    el.innerHTML = "";
    el.removeAttribute("title");
    _setAlarmasDetalleRowVisible(pre, false);
    return;
  }
  if (!list.length) {
    el.innerHTML = "";
    _setAlarmasDetalleRowVisible(pre, false);
    return;
  }
  _setAlarmasDetalleRowVisible(pre, true);
  el.textContent = "";
  el.title = "";
  el.innerHTML = list.map((a) => _renderAlarmaDetalleHtml(a)).join("");
}

function _filaTieneAidReal(tr) {
  if (!tr || _filaSaltaPotencias(tr)) return false;
  const aid = (tr.getAttribute("data-aid") || "").trim();
  if (!aid) return false;
  return !aid.startsWith("nf-");
}

function _potCell(pre, suffix) {
  const id = pre ? pre + "-" + suffix : suffix;
  return document.getElementById(id);
}

function _filaSaltaPotencias(tr) {
  if (!tr) return false;
  const st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
  // FREE: sin PON en Altiplano → no se consulta ni potencias ni alarmas.
  // RESERVED: se permite lectura completa, igual que IN SERVICE.
  return st === "FREE";
}

function _parseRxDbmJs(rx) {
  return window.NocPower.parseRxDbm(rx);
}

function _clasificarRxDbm(rx) {
  return window.NocPower.clasificarRxDbm(rx);
}

function _consultaFilaClearSemaforoHighlight(tr) {
  if (!tr) return;
  tr.classList.remove("consulta-fila-sem-rojo", "consulta-fila-sem-amarillo");
}

/** Resalta toda la fila según RX (misma regla que semáforo): solo rojo y amarillo. */
function _consultaFilaApplySemaforoHighlight(tr, rx) {
  if (!tr) return;
  _consultaFilaClearSemaforoHighlight(tr);
  const cat = _clasificarRxDbm(rx);
  if (cat === "rojo") tr.classList.add("consulta-fila-sem-rojo");
  else if (cat === "amarillo") tr.classList.add("consulta-fila-sem-amarillo");
}

function _consultaFilaClearSemaforoEnRaiz(root) {
  root.querySelectorAll("tr.consulta-fila-sem-rojo, tr.consulta-fila-sem-amarillo").forEach((tr) => {
    _consultaFilaClearSemaforoHighlight(tr);
  });
}

function _consultaEsPotenciasTokenPrincipal(root, valor) {
  const tok = (root.getAttribute("data-query-token") || "").trim();
  return Boolean(tok && (valor || "").trim() === tok);
}

function _consultaSemaforoSetCounts(root, rojas, amarillas, verdes) {
  const wrap = root.querySelector(".consulta-semaforo-pending");
  if (wrap) wrap.classList.remove("consulta-semaforo-pending");
  const ro = root.querySelector('.semaforo-dot[data-semaforo="rojo"]');
  const am = root.querySelector('.semaforo-dot[data-semaforo="amarillo"]');
  const ve = root.querySelector('.semaforo-dot[data-semaforo="verde"]');
  if (ro) ro.textContent = String(rojas);
  if (am) am.textContent = String(amarillas);
  if (ve) ve.textContent = String(verdes);
}

/** Actualiza badges del panel (consulta masiva) cuando llegan potencias del token principal. */
function _consultaSemaforoDesdePotenciasPayload(root, valor, data, pfx) {
  if (!_consultaEsPotenciasTokenPrincipal(root, valor)) return;
  if (!root.querySelector(".semaforo-dot[data-semaforo]")) return;
  let rojas = 0;
  let amarillas = 0;
  let verdes = 0;
  if (data && data.AID) {
    const cat = _clasificarRxDbm(data.RX);
    if (cat === "rojo") rojas = 1;
    else if (cat === "amarillo") amarillas = 1;
    else if (cat === "verde") verdes = 1;
  } else if (Array.isArray(data)) {
    const seen = new Set();
    data.forEach((r) => {
      if (!r || r.AID == null) return;
      const aidKey = String(r.AID);
      if (seen.has(aidKey)) return;
      seen.add(aidKey);
      const rxEl = document.getElementById(pfx + "rx-" + aidKey);
      const tr = rxEl
        ? rxEl.closest("tr")
        : root.querySelector('tr[data-aid="' + aidKey.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"]');
      if (tr && _filaSaltaPotencias(tr)) return;
      const cat = _clasificarRxDbm(r.RX);
      if (cat === "rojo") rojas += 1;
      else if (cat === "amarillo") amarillas += 1;
      else if (cat === "verde") verdes += 1;
    });
  }
  _consultaSemaforoSetCounts(root, rojas, amarillas, verdes);
}

function cargarPotenciasSeccion(valor, root, scopeEl, opts) {
  opts = opts && typeof opts === "object" ? opts : {};
  const silentNvRefresh = Boolean(opts.silentNvRefresh);
  const skipBtnLoading = Boolean(opts.skipBtnLoading) || silentNvRefresh;
  const pre = root.getAttribute("data-section-prefix") || "";
  const pfx = pre ? pre + "-" : "";
  const scope = scopeEl && scopeEl.querySelectorAll ? scopeEl : root;
  const inflightKey = pre || root.id || "";
  if (inflightKey && _consultaPotenciasInflight.has(inflightKey)) {
    if (!skipBtnLoading) _consultaAcquireSectionPotenciaBtnsLoading(root);
    const existing = _consultaPotenciasInflight.get(inflightKey);
    if (!skipBtnLoading) {
      existing.finally(() => _consultaReleaseSectionPotenciaBtnsLoading(root));
    }
    return existing;
  }

  if (!silentNvRefresh) {
    _consultaDetallePollPrepUI(pre, root, scope);
  }

  const detSt = (root.getAttribute("data-detalle-fat-status") || "").trim().toUpperCase();
  if (detSt === "FREE") {
    const tx = _potCell(pre, "tx");
    const rx = _potCell(pre, "rx");
    if (tx) {
      tx.innerText = "-";
      _setConsultaPotenciaLoading(tx, false);
      tx.classList.remove("status-down");
    }
    if (rx) {
      rx.innerText = "-";
      _setConsultaPotenciaLoading(rx, false);
      rx.classList.remove("status-down");
    }
    _setAlarmasDetalleRowVisible(pre, false);
    const nvFree = _nvStatusEl(pre);
    if (nvFree) nvFree.hidden = true;
    const aidDetFree = document.getElementById(pfx + "aid-value");
    if (aidDetFree) _consultaFilaClearSemaforoHighlight(aidDetFree.closest("tr"));
    if (_consultaEsPotenciasTokenPrincipal(root, valor) && root.querySelector(".consulta-semaforo-pending")) {
      _consultaSemaforoSetCounts(root, 0, 0, 0);
    }
    _consultaMarkPotenciasLoadedIfMasivo(root);
    return Promise.resolve();
  }

  const cells = [];
  const addCells = (els) => {
    els.forEach((el) => {
      if (el && !cells.includes(el)) cells.push(el);
    });
  };
  addCells([_potCell(pre, "tx"), _potCell(pre, "rx"), _potCell(pre, "alarmas")]);
  const nvOper = _nvOperEl(pre);
  if (nvOper) {
    _consultaShowNvStatusBar(pre, true);
    addCells([nvOper]);
  }
  scope.querySelectorAll("[id^='" + pfx + "tx-']").forEach((el) => addCells([el]));
  scope.querySelectorAll("[id^='" + pfx + "rx-']").forEach((el) => addCells([el]));
  const cellsCarga = cells.filter((el) => {
    const tr = el.closest("tr");
    return !tr || !_filaSaltaPotencias(tr);
  });
  if (!silentNvRefresh) {
    cellsCarga.forEach((el) => {
      if (el.id === pfx + "alarmas" && _consultaAlarmasYaFetched(pre)) return;
      const keepAlarmasRendered =
        el.id === pfx + "alarmas" && el.querySelector(".consulta-alarmas-block");
      if (keepAlarmasRendered) return;
      if (_consultaIsNvStatusSlot(el) && _consultaNvSlotHasContent(el)) return;
      if (_consultaPotenciaCeldaHasReading(el)) return;
      _setConsultaPotenciaLoading(el, true);
    });
  }

  const fetchJson = () => {
    if (Object.prototype.hasOwnProperty.call(opts, "prefetchedData")) {
      return Promise.resolve(opts.prefetchedData);
    }
    return fetch("/potencias", {
      method: "POST",
      headers: {"Content-Type": "application/x-www-form-urlencoded"},
      body: "value=" + encodeURIComponent(valor),
    }).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  };

  if (!skipBtnLoading) {
    _consultaAcquireSectionPotenciaBtnsLoading(root);
  }

  const fetchPromise = fetchJson().then((data) => {
      if (data && data.AID) {
        const tx = _potCell(pre, "tx");
        const rx = _potCell(pre, "rx");
        if (tx) _applyPotenciaDbmCelda(tx, data.TX, true);
        if (rx) _applyPotenciaDbmCelda(rx, data.RX, true);
        _updateDetalleVisualStatus(pre, data, root);
        _applyAlarmasDetalle(pre, data, root);
        _consultaArmNvRefresh(pre);
        _applyNvStatusDetalle(pre, data);
        _consultaSyncDownPoll(root, valor, scope);
        const snEl = document.getElementById(pfx + "sn-value");
        if (snEl && data.SN) {
          const snLive = String(data.SN).trim();
          if (snLive) snEl.innerText = snLive;
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "ONT_POSTGRES") ||
          Object.prototype.hasOwnProperty.call(data, "ONT_ALTIPLANO")
        ) {
          _applyConsultaOntCompareRows(root, pfx, data);
        }
        if (
          Object.prototype.hasOwnProperty.call(data, "ALTIPLANO_VNO") ||
          Object.prototype.hasOwnProperty.call(data, "ALTIPLANO_TASA_COMPOSITE")
        ) {
          _applyConsultaVnoRows(pfx, data);
        }
        const opEl = document.getElementById(pfx + "operador-value");
        if (opEl && data.OPERADOR) {
          const opLive = String(data.OPERADOR).trim();
          if (opLive && opLive !== "0" && opLive !== "—") {
            opEl.innerText = opLive;
            root.setAttribute("data-nv-operador", opLive);
          }
        }
        const aidDet = document.getElementById(pfx + "aid-value");
        if (aidDet) _consultaFilaApplySemaforoHighlight(aidDet.closest("tr"), data.RX);
        _consultaRefreshPotenciaCellsLoading(
          cellsCarga.filter((el) => el.id !== pfx + "alarmas"),
          root
        );
        _consultaSemaforoDesdePotenciasPayload(root, valor, data, pfx);
        if (window.ConsultaMasivoUi) window.ConsultaMasivoUi.evalRamaAllDown(root);
        return;
      }
      if (Array.isArray(data)) {
        const seenAids = new Set();
        data.forEach((r) => {
          const tx = document.getElementById(pfx + "tx-" + r.AID);
          const rx = document.getElementById(pfx + "rx-" + r.AID);
          const tr = (tx || rx) ? (tx || rx).closest("tr") : null;
          if (tr && _filaSaltaPotencias(tr)) {
            _consultaFilaClearSemaforoHighlight(tr);
            return;
          }
          seenAids.add(String(r.AID));
          const tieneAid = _filaTieneAidReal(tr);
          if (tx) _applyPotenciaDbmCelda(tx, r.TX, tieneAid);
          if (rx) _applyPotenciaDbmCelda(rx, r.RX, tieneAid);
          _updateRowVisualStatus(tr, r.RX);
          _consultaFilaApplySemaforoHighlight(tr, r.RX);
        });
        scope.querySelectorAll("tr[data-aid]").forEach((tr) => {
          if (!_filaTieneAidReal(tr)) return;
          const aid = tr.getAttribute("data-aid");
          if (seenAids.has(aid)) return;
          const tx = document.getElementById(pfx + "tx-" + aid);
          const rx = document.getElementById(pfx + "rx-" + aid);
          _applyPotenciaDbmCelda(tx, null, true);
          _applyPotenciaDbmCelda(rx, null, true);
          _consultaFilaClearSemaforoHighlight(tr);
        });
        _consultaRefreshPotenciaCellsLoading(
          cellsCarga.filter((el) => el.id !== pfx + "alarmas"),
          root
        );
        _consultaSyncDownPoll(root, valor, scope);
        aplicarFiltrosConsulta();
        _consultaSemaforoDesdePotenciasPayload(root, valor, data, pfx);
        if (window.ConsultaMasivoUi) window.ConsultaMasivoUi.evalRamaAllDown(root);
        return;
      }
      _consultaRefreshPotenciaCellsLoading(
        cellsCarga.filter((el) => el.id !== pfx + "alarmas"),
        root
      );
      _consultaFilaClearSemaforoEnRaiz(scope);
      if (_consultaEsPotenciasTokenPrincipal(root, valor) && root.querySelector(".consulta-semaforo-pending")) {
        _consultaSemaforoSetCounts(root, 0, 0, 0);
      }
    })
    .catch(() => {
      cellsCarga.forEach((el) => {
        _setConsultaPotenciaLoading(el, false);
        const tr = el.closest("tr");
        if (_filaTieneAidReal(tr)) {
          _applyPotenciaDbmCelda(el, null, true);
        }
      });
      _setAlarmasDetalleRowVisible(pre, false);
      const nvErr = _nvStatusEl(pre);
      if (nvErr) nvErr.hidden = true;
      _consultaFilaClearSemaforoEnRaiz(scope);
      if (_consultaEsPotenciasTokenPrincipal(root, valor) && root.querySelector(".consulta-semaforo-pending")) {
        _consultaSemaforoSetCounts(root, 0, 0, 0);
      }
      toast("Error al cargar potencias");
    });
  const finalizePotencias = () => {
    _consultaMarkPotenciasLoadedIfMasivo(root);
    if (!skipBtnLoading) _consultaReleaseSectionPotenciaBtnsLoading(root);
  };
  if (inflightKey) {
    _consultaPotenciasInflight.set(inflightKey, fetchPromise);
    fetchPromise.finally(() => {
      if (_consultaPotenciasInflight.get(inflightKey) === fetchPromise) {
        _consultaPotenciasInflight.delete(inflightKey);
      }
      finalizePotencias();
    });
  } else {
    fetchPromise.finally(finalizePotencias);
  }
  return fetchPromise;
}

function cambiarSNDesdeUI(accessId, operador, ontTarget, btn) {
  const section = btn && btn.closest ? btn.closest(".consulta-section") : null;
  const pre = section ? section.getAttribute("data-section-prefix") || "" : "";
  const snId = pre ? pre + "-sn-value" : "sn-value";
  const currentSnEl = document.getElementById(snId);
  const current = currentSnEl ? currentSnEl.innerText.trim() : "";

  if (!window.ensureConsultaAltiplanoSession || !window.runConsultaSnChange) {
    toast("Diálogo de autenticación no disponible");
    return;
  }

  const opLabel = String(operador || "").trim() || "Altiplano";
  let reloadScheduled = false;

  const snChangeOpts = {
    creds: null,
    dialog: {
      title: "Cambiar SN de la ONT",
      message: "Ingresá el nuevo serial.",
      currentSn: current,
      snValue: current,
      snPlaceholder: "12 caracteres (ej. SDMC5C73B3AF) o 16 hex del rótulo",
      okLabel: "Cambiar SN",
    },
    onCommitStart: () => {
      _setConsultaSnChanging(currentSnEl, btn, true);
    },
    execute: (creds) => {
      const sn = String(creds.new_sn || "").trim().toUpperCase();
      return fetch("/sn/cambiar", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          access_id: String(accessId || "").trim(),
          operador: String(operador || "").trim(),
          ont_target: String(ontTarget || "").trim(),
          new_sn: sn,
          altiplano_user: creds.username,
          altiplano_password: creds.password,
        }),
      }).then((r) => r.json().then((j) => ({ok: r.ok, status: r.status, json: j, sn})));
    },
    onSuccess: (json) => {
      reloadScheduled = true;
      toast(json.message || "SN actualizado · recargando consulta…");
      setTimeout(_consultaRecargarBusqueda, _CONSULTA_SN_RELOAD_DELAY_MS);
    },
    onFinally: () => {
      if (!reloadScheduled) {
        _setConsultaSnChanging(currentSnEl, btn, false);
        if (currentSnEl && current) currentSnEl.textContent = current;
      }
    },
  };

  ensureConsultaAltiplanoSession({
    operador: operador,
    dialog: {
      title: "Ingresar a Altiplano",
      message:
        "Credenciales de Altiplano (" +
        opLabel +
        ") para autorizar el cambio de SN.",
      okLabel: "Ingresar",
    },
  })
    .then((creds) => {
      snChangeOpts.creds = creds;
      return runConsultaSnChange(snChangeOpts);
    })
    .catch((err) => {
      if (err && err.message === "cancelled") return;
      _setConsultaSnChanging(currentSnEl, btn, false);
      if (currentSnEl && current) currentSnEl.textContent = current;
      toast(err.message || "Error al cambiar SN");
    });
}

function cambiarSNDesdeUIBtn(btn) {
  if (!btn) return;
  cambiarSNDesdeUI(
    btn.getAttribute("data-access-id") || "",
    btn.getAttribute("data-operador") || "",
    btn.getAttribute("data-ont-target") || "",
    btn
  );
}

function _consultaExportValue() {
  const modo = (document.getElementById("consulta_modo") || {}).value || "individual";
  if (modo === "masivo") {
    return ((document.getElementById("qm") || {}).value || "").trim();
  }
  return ((document.getElementById("q") || {}).value || "").trim();
}

function exportarConsultaCsv() {
  const value = _consultaExportValue();
  if (!value) {
    toast("No hay búsqueda para exportar");
    return;
  }
  let url = "/export/csv?value=" + encodeURIComponent(value);
  const hasTables = document.querySelector("tr[data-operador][data-fat-status]");
  const op = (_activeOperador || "ALL").trim();
  if (hasTables && op && op !== "ALL") {
    url += "&operador=" + encodeURIComponent(op);
  }
  window.location.href = url;
}

function _consultaTablaEsPuertosCto(table) {
  if (!table || table.classList.contains("table-kv")) return false;
  const row = table.querySelector("tr");
  if (!row) return false;
  const hdr = Array.from(row.querySelectorAll("th")).map((th) =>
    th.innerText.trim().toUpperCase()
  );
  return hdr.includes("OUT") && hdr.includes("AID");
}

function _consultaCtoNombreDesdeSection(section) {
  if (!section) return "";
  const block = section.querySelector(".consulta-cto-block[data-cto]");
  if (block) return (block.getAttribute("data-cto") || "").trim();
  const mapEl = section.querySelector("[data-consulta-cto-map][data-cto]");
  if (mapEl) return (mapEl.getAttribute("data-cto") || "").trim();
  const hasCtoTable = Array.from(section.querySelectorAll("table")).some(
    _consultaTablaEsPuertosCto
  );
  if (!hasCtoTable) return "";
  const tok = (section.getAttribute("data-query-token") || "").trim();
  if (tok.toUpperCase().includes("FATC")) return tok;
  const label = section.querySelector(".rama-row-head .rama-row-label");
  if (label) return label.textContent.trim();
  return tok;
}

function _consultaEncabezadoCopiarCto(cto) {
  const name = String(cto || "").trim();
  if (!name) return "";
  return "Estado de clientes en CTO " + name + "\n\n";
}

function _consultaMensajeCtoSinInService(cto) {
  const name = String(cto || "").trim();
  if (!name) return "";
  return "CTO " + name + " sin clientes IN SERVICE\n\n";
}

function _consultaFilaTextoCopiar(row) {
  const fila = [];
  row.querySelectorAll("th, td").forEach((cell) => {
    const cleanCell = cell.cloneNode(true);
    cleanCell
      .querySelectorAll("button, .btn, a.btn, .consulta-sn-btn")
      .forEach((actionEl) => actionEl.remove());
    fila.push(cleanCell.innerText.trim());
  });
  return fila.join("\t");
}

function _consultaExtraerTablaCtoInService(table) {
  let headerLine = "";
  const dataLines = [];
  if (!_consultaTablaEsPuertosCto(table)) {
    return { headerLine: headerLine, dataLines: dataLines };
  }
  if (getComputedStyle(table).display === "none") {
    return { headerLine: headerLine, dataLines: dataLines };
  }

  table.querySelectorAll("tr").forEach((row) => {
    if (getComputedStyle(row).display === "none") return;
    const line = _consultaFilaTextoCopiar(row);
    if (!line) return;
    if (row.querySelector("th")) {
      headerLine = line;
      return;
    }
    const st = (row.getAttribute("data-fat-status") || "").trim().toUpperCase();
    if (st !== "IN SERVICE") return;
    dataLines.push(line);
  });

  return { headerLine: headerLine, dataLines: dataLines };
}

function _consultaCopiarCtoScope(cto, scope) {
  const name = String(cto || "").trim();
  if (!name || !scope) return "";

  let headerLine = "";
  const dataLines = [];
  scope.querySelectorAll("table").forEach((table) => {
    if (!_consultaTablaEsPuertosCto(table)) return;
    const part = _consultaExtraerTablaCtoInService(table);
    if (part.headerLine && !headerLine) headerLine = part.headerLine;
    dataLines.push(...part.dataLines);
  });

  if (!dataLines.length) {
    return _consultaMensajeCtoSinInService(name);
  }

  let out = _consultaEncabezadoCopiarCto(name);
  if (headerLine) out += headerLine + "\n";
  out += dataLines.join("\n") + "\n\n";
  return out;
}

/* Copiar todos los resultados (masivo) */
function copiarTodo() {
  let texto = "";

  function appendTabla(el) {
    const style = getComputedStyle(el);
    if (style.display === "none") return;

    el.querySelectorAll("tr").forEach((row) => {
      const rStyle = getComputedStyle(row);
      if (rStyle.display === "none") return;

      const line = _consultaFilaTextoCopiar(row);
      if (line) texto += line + "\n";
    });

    texto += "\n";
  }

  document.querySelectorAll(".consulta-section").forEach((section) => {
    const secStyle = getComputedStyle(section);
    if (secStyle.display === "none") return;

    section.querySelectorAll(".consulta-cto-block").forEach((block) => {
      const blockStyle = getComputedStyle(block);
      if (blockStyle.display === "none") return;
      const cto = (block.getAttribute("data-cto") || "").trim();
      if (cto) texto += _consultaCopiarCtoScope(cto, block);
    });

    const ctoSuelta = _consultaCtoNombreDesdeSection(section);
    if (ctoSuelta) {
      texto += _consultaCopiarCtoScope(ctoSuelta, section);
    }

    section.querySelectorAll("table").forEach((table) => {
      if (table.closest(".consulta-cto-block")) return;
      if (_consultaTablaEsPuertosCto(table)) return;
      appendTabla(table);
    });

    section.querySelectorAll(".cto-header").forEach((el) => {
      const style = getComputedStyle(el);
      if (style.display === "none") return;
      texto += el.innerText.trim() + "\n";
    });

    texto += "\n";
  });

  if (!texto.trim()) {
    toast("No hay datos para copiar");
    return;
  }

  const ta = document.createElement("textarea");
  ta.value = texto;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);

  toast("Datos copiados al portapapeles");
}

function _updateDetalleVisualStatus(pre, data, root) {
  if (!root || !data || typeof data !== "object") return;
  const orig = (root.getAttribute("data-detalle-fat-status") || "").trim().toUpperCase();
  if (!orig) return;
  const cellId = (pre ? pre + "-" : "") + "status-value";
  const el = document.getElementById(cellId);
  if (!el) return;
  let next = orig;
  if (
    orig === "RESERVED" &&
    typeof window !== "undefined" &&
    window.NocPower &&
    window.NocPower.hasPowerValue(window.NocPower.parseRxDbm(data.RX))
  ) {
    next = "IN SERVICE";
  }
  el.textContent = next;
}

function _updateRowVisualStatus(tr, rx) {
  if (!tr) return;
  const orig = _normFatStatus(tr.getAttribute("data-fat-status") || "");
  if (orig !== "RESERVED") return;
  if (
    typeof window === "undefined" ||
    !window.NocPower ||
    !window.NocPower.hasPowerValue(window.NocPower.parseRxDbm(rx))
  ) {
    return;
  }
  const statusCell = tr.querySelector("td[data-status-cell]");
  if (statusCell) statusCell.textContent = "IN SERVICE";
}

function _consultaPotenciaEntriesVisible() {
  const entries = [];
  document.querySelectorAll(".consulta-section--multi").forEach((root) => {
    if (root.hidden || root.classList.contains("consulta-section--page-hidden")) {
      return;
    }
    const token = (root.getAttribute("data-query-token") || "").trim();
    if (!token) return;
    if (
      typeof window._consultaSectionPotenciasPendientes === "function" &&
      !window._consultaSectionPotenciasPendientes(root)
    ) {
      return;
    }
    entries.push({ token: token, root: root });
  });
  return entries;
}

/** Carga potencias de varias secciones; 2+ tokens usan ``POST /potencias/batch``. */
function _consultaCargarPotenciasEntries(entries) {
  if (!entries || !entries.length) return Promise.resolve();

  const afterOne = (e) => {
    if (window.ConsultaMasivoUi && window.ConsultaMasivoUi.evalRamaAllDown) {
      window.ConsultaMasivoUi.evalRamaAllDown(e.root);
    }
  };

  const potOpts = { skipBtnLoading: true };
  const releaseEntriesBtns = () => {
    entries.forEach((e) => _consultaReleaseSectionPotenciaBtnsLoading(e.root));
  };
  entries.forEach((e) => {
    _consultaAcquireSectionPotenciaBtnsLoading(e.root);
    if (window.ConsultaMasivoUi && window.ConsultaMasivoUi.markPotenciasScheduled) {
      window.ConsultaMasivoUi.markPotenciasScheduled(e.root);
    }
  });

  const applyEntries = (mapFn) =>
    Promise.all(
      entries.map((e) => mapFn(e).then(() => afterOne(e)))
    ).finally(releaseEntriesBtns);

  if (entries.length >= 2) {
    const tokens = entries.map((e) => e.token);
    return fetch("/potencias/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: tokens }),
    })
      .then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then((batch) => {
        const items = (batch && batch.items) || {};
        return applyEntries((e) =>
          cargarPotenciasSeccion(e.token, e.root, e.root, {
            ...potOpts,
            prefetchedData: Object.prototype.hasOwnProperty.call(items, e.token)
              ? items[e.token]
              : [],
          })
        );
      })
      .catch(() => {
        releaseEntriesBtns();
        toast("Error al cargar potencias (consulta masiva). Reintentá con Consultar RX.");
        return applyEntries((e) =>
          cargarPotenciasSeccion(e.token, e.root, e.root, {
            ...potOpts,
            prefetchedData: [],
          })
        );
      });
  }

  return applyEntries((e) => cargarPotenciasSeccion(e.token, e.root, e.root, potOpts));
}

/** Cola de potencias (consulta masiva): varias RAMAs/CTOs en paralelo (Altiplano aguanta la carga). */
function consultaPotenciasCola(jobFns, maxConcurrent) {
  const queue = jobFns.slice();
  const workers = Math.max(1, Math.min(maxConcurrent, queue.length || 1));
  const run = () => {
    const fn = queue.shift();
    if (!fn) return Promise.resolve();
    return Promise.resolve(fn()).then(run, run);
  };
  return Promise.all(Array.from({ length: workers }, run));
}

window.addEventListener("beforeunload", () => {
  _consultaStopAllDownPolls();
});

window.addEventListener("load", () => {
  _consultaStopAllDownPolls();
  (function consultaApplyDeepLinkFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const prefill = (params.get("q") || params.get("rama") || params.get("value") || "").trim();
    if (!prefill || document.querySelector(".consulta-section")) return;
    const qInp = document.getElementById("q");
    const modoEl0 = document.getElementById("consulta_modo");
    if (!qInp) return;
    if (modoEl0) modoEl0.value = "individual";
    qInp.value = prefill;
    if (params.get("auto") === "0") return;
    const form = qInp.closest("form");
    if (form) form.requestSubmit();
  })();
  if (document.querySelector("tr[data-operador][data-fat-status]")) {
    aplicarFiltrosConsulta();
  }
  const btnCopiar = document.getElementById("btn-copiar");
  const sections = document.querySelectorAll(".consulta-section");
  const consultaMasivo = document.querySelector(".consulta-section--multi") !== null;
  const potenciaJobs = [];
  sections.forEach((root) => {
    const pre = root.getAttribute("data-section-prefix") || "";
    _consultaInitNvStatusBar(pre);
    const token = root.getAttribute("data-query-token") || "";
    if (!token || consultaMasivo) return;
    potenciaJobs.push(cargarPotenciasSeccion(token, root));
  });
  const afterPotencias = () => {
    if (document.querySelector("tr[data-operador][data-fat-status]")) {
      aplicarFiltrosConsulta();
    }
  };
  if (potenciaJobs.length === 0 && !consultaMasivo) {
    /* Sin búsqueda o sin filas útiles: dejar Copiar deshabilitado como en la página inicial. */
  } else if (consultaMasivo && window.ConsultaMasivoUi) {
    if (btnCopiar) btnCopiar.disabled = false;
    const preload = window.ConsultaMasivoUi.initPager();
    if (preload && preload.then) {
      preload.then(afterPotencias).catch(afterPotencias);
    } else {
      afterPotencias();
    }
  } else if (btnCopiar) {
    btnCopiar.disabled = true;
    Promise.all(potenciaJobs)
      .then(() => {
        btnCopiar.disabled = false;
        afterPotencias();
      })
      .catch(() => {
        btnCopiar.disabled = false;
      });
  } else {
    Promise.all(potenciaJobs).then(afterPotencias).catch(afterPotencias);
  }

  function consultaNavigateClear(m) {
    window.location.assign(m === "masivo" ? clearUrlMas : clearUrlInd);
  }

  const input = document.getElementById("q");
  const modoEl = document.getElementById("consulta_modo");
  const panelInd = document.getElementById("consulta-panel-individual");
  const panelMas = document.getElementById("consulta-panel-masivo");
  function consultaSetModo(m) {
    if (!modoEl || !panelInd || !panelMas) return;
    modoEl.value = m;
    const indOn = m === "individual";
    panelInd.hidden = !indOn;
    panelMas.hidden = indOn;
    document.querySelectorAll(".consulta-mode-tab").forEach((btn) => {
      const on = btn.getAttribute("data-modo") === m;
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (window.initNocPage) {
      initNocPage({
        page: "index",
        searchSelector: indOn ? "#q" : "#qm",
        onClear: function () {
          const q = document.getElementById("q");
          const qm = document.getElementById("qm");
          if (q) q.value = "";
          if (qm) qm.value = "";
        },
      });
    }
  }
  document.querySelectorAll(".consulta-mode-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const m = btn.getAttribute("data-modo") || "individual";
      if (modoEl && modoEl.value === m) return;
      consultaNavigateClear(m);
    });
  });
  const btnLimpiar = document.getElementById("btn-consulta-limpiar");
  if (btnLimpiar) {
    btnLimpiar.addEventListener("click", () => {
      consultaNavigateClear((modoEl && modoEl.value) || "individual");
    });
  }
  if (modoEl && modoEl.value === "masivo") consultaSetModo("masivo");
  else consultaSetModo("individual");

  const activeInp = (modoEl && modoEl.value === "masivo") ? document.getElementById("qm") : document.getElementById("q");
  if (activeInp && !activeInp.value) activeInp.focus();

  if (window.consultaInitAllCtoMaps) {
    consultaInitAllCtoMaps();
  }
});

  /** Handlers usados por ``onclick`` en ``index.html`` y HTML generado en runtime. */
  window.filtrarOperador = filtrarOperador;
  window.consultaRecargarPotenciasDesdeBtn = consultaRecargarPotenciasDesdeBtn;
  window.consultaRecargarPotenciasSubcto = consultaRecargarPotenciasSubcto;
  window.copiarTodo = copiarTodo;
  window.exportarConsultaCsv = exportarConsultaCsv;
  window.togglePonAdminDesdeUIBtn = togglePonAdminDesdeUIBtn;
  window.toggleOntAdminDesdeUIBtn = toggleOntAdminDesdeUIBtn;
  window.cambiarSNDesdeUIBtn = cambiarSNDesdeUIBtn;
  window.cargarPotenciasSeccion = cargarPotenciasSeccion;
  window.consultaPotenciasCola = consultaPotenciasCola;
  window._consultaCargarPotenciasEntries = _consultaCargarPotenciasEntries;
  window._consultaSectionPotenciasPendientes = _consultaSectionPotenciasPendientes;
})();
