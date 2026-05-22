/** Lógica UI de consulta índice (potencias, PON, filtros, Altiplano). */
(function () {
  "use strict";
  var cfg = window.__CONSULTA_INDEX_CFG__ || {};
  var clearUrlInd = cfg.clearUrlInd || "/";
  var clearUrlMas = cfg.clearUrlMas || "/";
let _activeOperador = "ALL";
let _activeFatStatus = "ALL";
let _toastTimer = null;

function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 1800);
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
    const rst = _normFatStatus(row.dataset.fatStatus);
    const opOk =
      op === "ALL" ||
      (_canonicalOperadorConsulta(rop) && _canonicalOperadorConsulta(rop) === op);
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
      btn.dataset.consultaBtnLabel = (btn.textContent || "").trim() || label;
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

function consultaRecargarPotenciasDesdeBtn(btn) {
  const sec = btn && btn.closest ? btn.closest(".consulta-section") : null;
  if (!sec) return;
  const tok = sec.getAttribute("data-query-token") || "";
  if (!tok) return;
  consultaSetBtnConsultando(btn, true);
  Promise.resolve(cargarPotenciasSeccion(tok, sec)).finally(() => {
    consultaSetBtnConsultando(btn, false);
  });
}

function consultaRecargarPotenciasSubcto(btn) {
  const cto = ((btn && btn.getAttribute("data-cto")) || "").trim();
  const sec = btn && btn.closest ? btn.closest(".consulta-section") : null;
  const block = btn && btn.closest ? btn.closest(".consulta-cto-block") : null;
  if (!cto || !sec || !block) return;
  consultaSetBtnConsultando(btn, true);
  Promise.resolve(cargarPotenciasSeccion(cto, sec, block)).finally(() => {
    consultaSetBtnConsultando(btn, false);
  });
}

function _hasPower(v) {
  return window.NocPower.hasPowerValue(v);
}

function _formatPowerDbm(v) {
  return window.NocPower.formatPowerDbm(v);
}

function _applyPotenciaDbmCelda(el, v, hasSubscriber) {
  if (el) el.classList.remove("consulta-down-poll-counting");
  window.NocPower.applyPowerDbmCell(el, v, hasSubscriber);
}

const _CONSULTA_POT_SPINNER_HTML =
  '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';

const _CONSULTA_SN_CHANGING_HTML =
  '<span class="olt-txrx-loading-wrap consulta-sn-changing-wrap" title="Cambiando SN…">' +
  '<span class="olt-txrx-cell-spin" aria-hidden="true"></span>' +
  '<span class="consulta-sn-changing-label">Cambiando</span></span>';

const _CONSULTA_SN_RELOAD_DELAY_MS = 3500;
const _CONSULTA_DOWN_POLL_MS = 3000;
const _CONSULTA_DOWN_POLL_COUNTDOWN_SEC = 3;
const _CONSULTA_PON_COMMITTED_GRACE_MS = 90000;
const _CONSULTA_PON_POST_REFRESH_MS = 1500;
const _consultaDownPollers = new Map();
const _consultaPonCommitted = new Map();
const _consultaPotenciasInflight = new Map();

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

function _consultaPotenciaCeldaDown(el) {
  if (!el) return false;
  const t = String(el.textContent || "").trim().toUpperCase();
  return el.classList.contains("status-down") || t === "DOWN";
}

function _isConsultaDetallePotenciaPar(pre) {
  const tx = _potCell(pre, "tx");
  const rx = _potCell(pre, "rx");
  if (!tx || !rx) return false;
  const pfx = pre ? pre + "-" : "";
  return tx.id === pfx + "tx" && rx.id === pfx + "rx";
}

function _consultaDetalleTxRxBothDown(pre) {
  if (!_isConsultaDetallePotenciaPar(pre)) return false;
  return (
    _consultaPotenciaCeldaDown(_potCell(pre, "tx")) &&
    _consultaPotenciaCeldaDown(_potCell(pre, "rx"))
  );
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

/** El poll sigue mientras esté activo y TX/RX aún no tengan lectura válida. */
function _consultaDetallePollShouldContinue(pre, root) {
  if (!_isConsultaDetallePotenciaPar(pre)) return false;
  if (!_consultaIsDownPollActive(root)) return false;
  const tx = _potCell(pre, "tx");
  const rx = _potCell(pre, "rx");
  return !(
    _consultaPotenciaCeldaHasReading(tx) && _consultaPotenciaCeldaHasReading(rx)
  );
}

function _consultaIsDownPollActive(root) {
  if (!root) return false;
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  return Boolean(key && _consultaDownPollers.has(key));
}

/** Si el poll sigue activo y aún no hay alarmas, mantiene la fila con spinner. */
function _consultaDetallePollAlarmasTail(pre, root, data) {
  if (!root || !_consultaIsDownPollActive(root)) return;
  if (!_consultaDetallePollShouldContinue(pre, root)) return;
  const list = data && Array.isArray(data.ALARMAS) ? data.ALARMAS : [];
  if (list.length > 0) return;
  if (data && data.alarmas_label === "Sin Alarmas") return;
  _setAlarmasDetalleRowVisible(pre, true);
  const al = _potCell(pre, "alarmas");
  if (al) _setConsultaPotenciaLoading(al, true);
}

function _consultaDetallePollPrepUI(pre, root) {
  if (!_isConsultaDetallePotenciaPar(pre)) return;
  if (!_consultaDetallePollShouldContinue(pre, root) && !_consultaDetalleTxRxBothDown(pre)) {
    return;
  }
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

function _consultaDownPollCountdownCells(pre, root) {
  const cells = [];
  const tx = _potCell(pre, "tx");
  const rx = _potCell(pre, "rx");
  const al = _potCell(pre, "alarmas");
  const nvOper = _nvOperEl(pre);
  if (tx) cells.push(tx);
  if (rx) cells.push(rx);
  if (al && !al.querySelector(".consulta-alarmas-block")) cells.push(al);
  if (nvOper) cells.push(nvOper);
  return cells;
}

function _setConsultaDownPollCountdown(el, sec) {
  if (!el) return;
  el.classList.remove("consulta-potencia-loading", "status-down", "status-up");
  el.classList.add("consulta-down-poll-counting");
  el.setAttribute("aria-busy", "true");
  el.setAttribute("aria-label", "Próxima consulta en " + sec + " segundos");
  el.innerHTML =
    '<span class="consulta-down-poll-countdown" title="Próxima consulta…">' +
    '<span class="consulta-down-poll-countdown__n">' +
    String(sec) +
    "</span>" +
    '<span class="consulta-down-poll-countdown__label">s</span></span>';
}

function _consultaRunDownPollCycle(root, valor) {
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  const pre = root.getAttribute("data-section-prefix") || "";
  if (!_consultaDownPollers.has(key)) return;
  if (!_consultaDetallePollShouldContinue(pre, root)) {
    _consultaStopDownPoll(root);
    return;
  }

  const cells = _consultaDownPollCountdownCells(pre, root);
  let sec = _CONSULTA_DOWN_POLL_COUNTDOWN_SEC;

  const step = () => {
    if (!_consultaDownPollers.has(key)) return;
    if (!_consultaDetallePollShouldContinue(pre, root)) {
      _consultaStopDownPoll(root);
      return;
    }
    if (sec > 0) {
      cells.forEach((el) => _setConsultaDownPollCountdown(el, sec));
      sec -= 1;
      const timerId = setTimeout(step, 1000);
      _consultaDownPollers.set(key, { timerId: timerId });
      return;
    }
    const tok = (root.getAttribute("data-query-token") || valor || "").trim();
    if (!tok) {
      _consultaStopDownPoll(root);
      return;
    }
    Promise.resolve(cargarPotenciasSeccion(tok, root, root)).finally(() => {
      if (!_consultaDownPollers.has(key)) return;
      if (!_consultaDetallePollShouldContinue(pre, root)) {
        _consultaStopDownPoll(root);
        return;
      }
      _consultaRunDownPollCycle(root, valor);
    });
  };
  step();
}

function _consultaSyncDownPoll(root, valor) {
  if (!root) return;
  const key = root.id || root.getAttribute("data-section-prefix") || "";
  const pre = root.getAttribute("data-section-prefix") || "";
  if (!_consultaDetalleTxRxBothDown(pre)) {
    _consultaStopDownPoll(root);
    return;
  }
  if (_consultaDownPollers.has(key)) return;

  _consultaDownPollers.set(key, { timerId: null });
  _consultaRunDownPollCycle(root, valor);
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

/** oper desde NV_STATUS o inferido por lectura RX (IN SERVICE con potencia). */
function _nvOperEffective(data, nv) {
  const o = String((nv && nv.oper) || "").trim().toUpperCase();
  if (o === "UP" || o === "DOWN") return o;
  const rx = data && data.RX;
  if (typeof window !== "undefined" && window.NocPower) {
    if (window.NocPower.hasPowerValue(window.NocPower.parseRxDbm(rx))) return "UP";
    const t = String(rx || "").trim().toUpperCase();
    if (t === "DOWN") return "DOWN";
  }
  return "";
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
  return (
    '<div class="consulta-nv-status__chip consulta-nv-status__chip--oper">' +
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
  const ponTitle =
    ponRaw === "LOCKED"
      ? "Levantar puerto PON " + _consultaPonPortIndex(nv, ont)
      : "Bajar puerto PON " + _consultaPonPortIndex(nv, ont);
  return (
    '<button type="button" class="consulta-nv-pon-action-btn" title="' +
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
  const operEff = _nvOperEffective(data, nvObj);
  const chip = _consultaOperChipHtml(operEff);
  operSlot.innerHTML = chip || "";
  operSlot.hidden = !chip;
}

function _applyNvAdminDetalle(pre, nvObj) {
  const adminSlot = _nvAdminEl(pre);
  if (!adminSlot) return;
  const hasAdmin = Boolean(nvObj && nvObj.admin);
  if (!hasAdmin) {
    adminSlot.innerHTML = "";
    adminSlot.hidden = true;
    return;
  }
  const adminRaw = String(nvObj.admin || "").trim().toUpperCase();
  const admin = _nvAdminLabel(nvObj.admin);
  const adminCls = _nvAdminClass(adminRaw);
  const canToggleAdmin =
    adminRaw === "LOCKED" || adminRaw === "UNLOCKED";
  const adminEditBtn = canToggleAdmin
    ? '<button type="button" class="consulta-nv-admin-edit" title="' +
      (adminRaw === "UNLOCKED"
        ? "Bloquear ONT (apagar)"
        : "Desbloquear ONT (encender)") +
      '" aria-label="' +
      (adminRaw === "UNLOCKED" ? "Bloquear ONT" : "Desbloquear ONT") +
      '" data-admin="' +
      _escHtmlAlarmas(adminRaw) +
      '" onclick="toggleOntAdminDesdeUIBtn(this)">✎</button>'
    : "";
  adminSlot.hidden = false;
  adminSlot.innerHTML =
    '<div class="consulta-nv-status__chip consulta-nv-status__chip--admin">' +
    '<span class="consulta-nv-status__icon consulta-nv-status__icon--' +
    adminCls +
    '" aria-hidden="true">' +
    _nvAdminIcon(adminRaw) +
    "</span>" +
    '<span class="consulta-nv-status__text">' +
    _escHtmlAlarmas(admin) +
    "</span>" +
    adminEditBtn +
    "</div>";
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
  const operEff = _nvOperEffective(data, nvObj);
  const hasAdmin = Boolean(nvObj.admin);
  if (!canTogglePon && !operEff && !hasAdmin) {
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
  const msg = bajar
    ? "Se bloqueará la partición PON en Altiplano (baja el puerto para todas las ONT del PON)."
    : "Se desbloqueará la partición PON en Altiplano (levanta el puerto).";

  if (!window.runConsultaAltiplanoAuth) {
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

  runConsultaAltiplanoAuth({
    dialog: {
      title: title,
      message: msg + " Credenciales de Altiplano (INP).",
      showSnField: false,
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
        _renderConsultaPonBtn(pre, {
          pon_admin: newAdmin,
          pon_index: json.pon_index || null,
        });
      }
      if (section && token) {
        window.setTimeout(() => {
          cargarPotenciasSeccion(token, section, section);
        }, _CONSULTA_PON_POST_REFRESH_MS);
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
  const msg = apagar
    ? "Se bloqueará el admin de la ONT en Altiplano (equivalente a apagar)."
    : "Se desbloqueará el admin de la ONT en Altiplano (equivalente a encender).";

  if (!window.runConsultaAltiplanoAuth) {
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

  runConsultaAltiplanoAuth({
    dialog: {
      title: title,
      message: msg + " Credenciales de Altiplano (INP).",
      showSnField: false,
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
  const el = _potCell(pre, "alarmas");
  if (!el) return;
  const pollPending = root && _consultaDetallePollShouldContinue(pre, root);
  _setConsultaPotenciaLoading(el, false);
  if (!data || typeof data !== "object") {
    if (!pollPending) _setAlarmasDetalleRowVisible(pre, false);
    return;
  }
  const list = Array.isArray(data.ALARMAS) ? data.ALARMAS : [];
  if (data.alarmas_label === "Sin Alarmas") {
    el.innerHTML = "";
    el.removeAttribute("title");
    _setAlarmasDetalleRowVisible(pre, false);
    return;
  }
  if (!list.length) {
    if (!pollPending) {
      el.innerHTML = "";
      _setAlarmasDetalleRowVisible(pre, false);
      return;
    }
    _setAlarmasDetalleRowVisible(pre, true);
    _setConsultaPotenciaLoading(el, true);
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
  return st === "FREE" || st === "RESERVED";
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
      const stEl = document.getElementById(pfx + "st-" + r.AID);
      const tr = stEl ? stEl.closest("tr") : null;
      if (tr && _filaSaltaPotencias(tr)) return;
      const cat = _clasificarRxDbm(r.RX);
      if (cat === "rojo") rojas += 1;
      else if (cat === "amarillo") amarillas += 1;
      else if (cat === "verde") verdes += 1;
    });
  }
  _consultaSemaforoSetCounts(root, rojas, amarillas, verdes);
}

function cargarPotenciasSeccion(valor, root, scopeEl) {
  const pre = root.getAttribute("data-section-prefix") || "";
  const pfx = pre ? pre + "-" : "";
  const scope = scopeEl && scopeEl.querySelectorAll ? scopeEl : root;
  const inflightKey = pre || root.id || "";
  if (inflightKey && _consultaPotenciasInflight.has(inflightKey)) {
    return _consultaPotenciasInflight.get(inflightKey);
  }

  _consultaDetallePollPrepUI(pre, root);

  const detSt = (root.getAttribute("data-detalle-fat-status") || "").trim().toUpperCase();
  if (detSt === "FREE" || detSt === "RESERVED") {
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
  cellsCarga.forEach((el) => {
    const keepAlarmasRendered =
      el.id === pfx + "alarmas" && el.querySelector(".consulta-alarmas-block");
    if (!keepAlarmasRendered) _setConsultaPotenciaLoading(el, true);
  });

  const fetchPromise = fetch("/potencias", {
    method: "POST",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: "value=" + encodeURIComponent(valor),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      if (data && data.AID) {
        const tx = _potCell(pre, "tx");
        const rx = _potCell(pre, "rx");
        if (tx) _applyPotenciaDbmCelda(tx, data.TX, true);
        if (rx) _applyPotenciaDbmCelda(rx, data.RX, true);
        _applyAlarmasDetalle(pre, data, root);
        _applyNvStatusDetalle(pre, data);
        const snEl = document.getElementById(pfx + "sn-value");
        if (snEl && data.SN) {
          const snLive = String(data.SN).trim();
          if (snLive) snEl.innerText = snLive;
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
        cellsCarga.forEach((el) => {
          if (el.id === pfx + "alarmas") return;
          _setConsultaPotenciaLoading(el, false);
        });
        _consultaSemaforoDesdePotenciasPayload(root, valor, data, pfx);
        if (window.ConsultaMasivoUi) window.ConsultaMasivoUi.evalRamaAllDown(root);
        _consultaSyncDownPoll(root, valor);
        _consultaDetallePollAlarmasTail(pre, root, data);
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
        cellsCarga.forEach((el) => _setConsultaPotenciaLoading(el, false));
        aplicarFiltrosConsulta();
        _consultaSemaforoDesdePotenciasPayload(root, valor, data, pfx);
        if (window.ConsultaMasivoUi) window.ConsultaMasivoUi.evalRamaAllDown(root);
        return;
      }
      cellsCarga.forEach((el) => _setConsultaPotenciaLoading(el, false));
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
  if (inflightKey) {
    _consultaPotenciasInflight.set(inflightKey, fetchPromise);
    fetchPromise.finally(() => {
      if (_consultaPotenciasInflight.get(inflightKey) === fetchPromise) {
        _consultaPotenciasInflight.delete(inflightKey);
      }
    });
  }
  return fetchPromise;
}

function cambiarSNDesdeUI(accessId, operador, ontTarget, btn) {
  const section = btn && btn.closest ? btn.closest(".consulta-section") : null;
  const pre = section ? section.getAttribute("data-section-prefix") || "" : "";
  const snId = pre ? pre + "-sn-value" : "sn-value";
  const currentSnEl = document.getElementById(snId);
  const current = currentSnEl ? currentSnEl.innerText.trim() : "";

  if (!window.runConsultaAltiplanoAuth) {
    toast("Diálogo de autenticación no disponible");
    return;
  }

  const opLabel = String(operador || "").trim() || "Altiplano";
  let reloadScheduled = false;

  runConsultaAltiplanoAuth({
    dialog: {
      title: "Cambiar SN de la ONT",
      message:
        "Nuevo serial y credenciales de Altiplano (" + opLabel + ").",
      showSnField: true,
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
  }).catch((err) => {
    if (err && err.message === "cancelled") return;
    if (err && err.authError) {
      _setConsultaSnChanging(currentSnEl, btn, false);
      if (currentSnEl && current) currentSnEl.textContent = current;
      return;
    }
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

  toast("Datos copiados");
}

/** Cola de potencias (consulta masiva): una RAMA/CTO a la vez para no saturar Altiplano. */
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
  if (document.querySelector("tr[data-operador][data-fat-status]")) {
    aplicarFiltrosConsulta();
  }
  const btnCopiar = document.getElementById("btn-copiar");
  const sections = document.querySelectorAll(".consulta-section");
  const consultaMasivo = document.querySelector(".consulta-section--multi") !== null;
  const potenciaJobs = [];
  const potenciaJobFns = [];
  sections.forEach((root) => {
    const pre = root.getAttribute("data-section-prefix") || "";
    _consultaInitNvStatusBar(pre);
    const token = root.getAttribute("data-query-token") || "";
    if (!token) return;
    if (consultaMasivo) {
      potenciaJobFns.push(() => cargarPotenciasSeccion(token, root));
    } else {
      potenciaJobs.push(cargarPotenciasSeccion(token, root));
    }
  });
  const afterPotencias = () => {
    if (document.querySelector("tr[data-operador][data-fat-status]")) {
      aplicarFiltrosConsulta();
    }
  };
  if (potenciaJobs.length === 0 && potenciaJobFns.length === 0) {
    /* Sin búsqueda o sin filas útiles: dejar Copiar deshabilitado como en la página inicial. */
  } else if (consultaMasivo && window.ConsultaMasivoUi) {
    if (btnCopiar) btnCopiar.disabled = false;
    window.ConsultaMasivoUi.initPager();
    const visibleFns = window.ConsultaMasivoUi.potenciaJobFnsForVisible();
    if (visibleFns.length) {
      consultaPotenciasCola(visibleFns, 1).then(afterPotencias).catch(afterPotencias);
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
})();
