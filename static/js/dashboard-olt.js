const state = {};
const ltInventarioCargado = {};
const ltCargando = {};
const ltInventarioData = {};
const _oltRamaPotenciasCache = {};
const _oltRamaPotenciasCacheMs = 45000;
const _OLT_STATE_KEY = "oltDashboardStateV1";
let _toastTimerOlt = null;
let _restoringOltState = false;
const _oltStateStore = window.createNocPageStateStore
  ? window.createNocPageStateStore(_OLT_STATE_KEY, { debounceMs: 120 })
  : null;

/** Sin columna SN ni columna Estado (alineado con consulta índice / RAMA). */
const OLT_COL_TX = 7;
const OLT_COL_RX = 8;

function _oltFatSkipPotencias(tr) {
  const st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
  return st === "FREE" || st === "RESERVED";
}

const _npOlt = () => window.NocPower;

function _hasPowerOlt(v) {
  return _npOlt() ? _npOlt().hasPowerValue(v) : false;
}

function _oltRowCellsHtml(o, rama, cto, outNum) {
  const st = String(o.STATUS || "").trim().toUpperCase();
  const aidDisp = st === "FREE" ? "-" : _esc(o.AID);
  const opDisp = st === "FREE" ? "-" : _esc(o.OPERADOR);
  const principal = _esc(o.PRINCIPAL || "—");
  const ramaDisp = _esc(o.RAMA || rama || "—");
  const ontRaw = (o.ONT || "").trim();
  const ontDisp = st === "FREE" ? "" : _esc(ontRaw || "—");
  const statusDisp = _esc(o.STATUS || "");
  const spin =
    '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';
  let txCell;
  let rxCell;
  if (st === "FREE" || st === "RESERVED") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
  } else {
    txCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    rxCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
  }
  return `
                      <td class="mono">${outNum}</td>
                      <td class="mono">${aidDisp}</td>
                      <td>${opDisp}</td>
                      <td>${principal}</td>
                      <td class="mono">${ramaDisp}</td>
                      <td class="mono">${ontDisp}</td>
                      <td>${statusDisp}</td>
                      ${txCell}
                      ${rxCell}`;
}

function toastOlt(msg) {
  const el = document.getElementById("toast-olt");
  if (!el) return;
  el.textContent = msg;
  el.classList.add("show");
  if (_toastTimerOlt) clearTimeout(_toastTimerOlt);
  _toastTimerOlt = setTimeout(() => el.classList.remove("show"), 2000);
}

function copyTextToClipboardOlt(text) {
  const done = () => toastOlt("Copiado (pegá en Excel con Ctrl+V)");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text).then(done).catch(fallback);
  }
  fallback();
  function fallback() {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (e) {
      toastOlt("No se pudo copiar");
    }
    document.body.removeChild(ta);
  }
}

function _normExportOp(raw) {
  return String(raw || "").trim().toUpperCase();
}

/** Mismo orden que ``OPERADORES_CONSULTA_ORDEN`` en ``services/domain.py``. */
const _OLT_OPERADORES_ORDEN = ["TASA", "DIRECTV", "METROTEL", "SION", "IPLAN", "ATC"];

const _OLT_OPERADOR_ALIASES = {
  TASA: "TASA",
  DIRECTV: "DIRECTV",
  DTV: "DIRECTV",
  METROTEL: "METROTEL",
  IPLAN: "IPLAN",
  ATC: "ATC",
  SION: "SION",
};

function _canonicalOperadorOlt(raw) {
  const key = String(raw || "")
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "");
  if (!key || key === "-" || key === "—" || key === "0" || key === "NONE" || key === "NULL") {
    return null;
  }
  if (_OLT_OPERADOR_ALIASES[key]) return _OLT_OPERADOR_ALIASES[key];
  if (_OLT_OPERADORES_ORDEN.includes(key)) return key;
  return null;
}

function _emptyOperadorCounts() {
  const out = {};
  _OLT_OPERADORES_ORDEN.forEach((op) => {
    out[op] = 0;
  });
  return out;
}

/** Valores basura (BD / serialización) que no deben aparecer en el selector de operador */
function _shouldListExportOperator(norm) {
  return !!norm && norm !== "NONE" && norm !== "NULL";
}

function _oltExportFilterFromUi() {
  const sel = document.getElementById("olt-export-operador");
  return sel ? String(sel.value || "").trim() : "";
}

function _collectOperatorsFromPonSelection() {
  /** Map: operador normalizado (UPPERCASE) → etiqueta visible (primera vista) */
  const byNorm = new Map();
  const selected = Array.from(document.querySelectorAll(".pon-select:checked"));
  selected.forEach((cb) => {
    const uid = cb.getAttribute("data-uid") || "";
    const pon = cb.getAttribute("data-pon-label") || "";
    const data = ltInventarioData[uid] || {};
    const ponBlock = (data.PONES || {})[pon];
    if (!ponBlock) return;
    const ramas = ponBlock.RAMAS || {};
    Object.keys(ramas).forEach((rama) => {
      const ctos = (ramas[rama] || {}).CTOS || {};
      Object.keys(ctos).forEach((cto) => {
        (ctos[cto] || []).forEach((o) => {
          const st = String(o.STATUS || "").trim().toUpperCase();
          if (st !== "IN SERVICE") return;
          const disp = String(o.OPERADOR || "").trim();
          const norm = _normExportOp(disp);
          if (!_shouldListExportOperator(norm)) return;
          if (!byNorm.has(norm)) byNorm.set(norm, disp);
        });
      });
    });
  });
  return byNorm;
}

function _syncOltExportOperatorSelect() {
  const sel = document.getElementById("olt-export-operador");
  if (!sel) return;
  const prev = String(sel.value || "").trim();
  const map = _collectOperatorsFromPonSelection();
  const keys = Array.from(map.keys()).sort((a, b) => a.localeCompare(b));
  sel.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "";
  optAll.textContent = "Todos los operadores";
  sel.appendChild(optAll);
  keys.forEach((k) => {
    const o = document.createElement("option");
    o.value = k;
    o.textContent = map.get(k) || k;
    sel.appendChild(o);
  });
  if (prev && keys.includes(prev)) sel.value = prev;
  else sel.value = "";
}

function _sanitizeExportBasename(s) {
  const t = String(s || "").replace(/[^A-Za-z0-9_-]/g, "");
  return t || "export";
}

function _buildPonExportLines(opts) {
  const raw = opts && opts.filterOperator != null ? opts.filterOperator : "";
  const filterNorm = _normExportOp(raw);
  const applyFilter = filterNorm.length > 0;

  const selected = Array.from(document.querySelectorAll(".pon-select:checked"));
  if (selected.length === 0) {
    return { error: "Seleccioná al menos un PON", lines: [], count: 0 };
  }

  const lines = [];
  lines.push(["PON", "RAMA", "CTO", "ACCESS ID", "OPERADOR", "ONT"].join("\t"));
  let n = 0;
  const selectedRamas = new Set();
  const selectedCtos = new Set();
  let selectedOnts = 0;
  const operadorCounts = _emptyOperadorCounts();

  selected.forEach((cb) => {
    const uid = cb.getAttribute("data-uid") || "";
    const pon = cb.getAttribute("data-pon-label") || "";
    const data = ltInventarioData[uid] || {};
    const ponBlock = (data.PONES || {})[pon];
    if (!ponBlock) return;
    const ramas = ponBlock.RAMAS || {};
    Object.keys(ramas).forEach((rama) => {
      const ctos = (ramas[rama] || {}).CTOS || {};
      Object.keys(ctos).forEach((cto) => {
        (ctos[cto] || []).forEach((o) => {
          const st = String(o.STATUS || "").trim().toUpperCase();
          if (st !== "IN SERVICE") return;
          const opNorm = _normExportOp(o.OPERADOR);
          if (applyFilter && opNorm !== filterNorm) return;
          selectedRamas.add(rama);
          selectedCtos.add(rama + "||" + cto);
          selectedOnts += 1;
          const opCanon = _canonicalOperadorOlt(o.OPERADOR);
          if (opCanon) operadorCounts[opCanon] = (operadorCounts[opCanon] || 0) + 1;
          lines.push([
            pon,
            rama,
            cto,
            o.AID || "",
            o.OPERADOR || "",
            o.ONT || "",
          ].join("\t"));
          n++;
        });
      });
    });
  });

  if (n === 0) {
    if (applyFilter) {
      return {
        error:
          "No hay Access ID IN SERVICE para ese operador con la selección actual",
        lines: [],
        count: 0,
      };
    }
    return {
      error:
        "No hay Access ID en estado IN SERVICE para exportar con esa selección",
      lines: [],
      count: 0,
    };
  }
  lines.push("");
  lines.push("RESUMEN:");
  lines.push("PON: " + String(selected.length));
  lines.push("RAMAS: " + String(selectedRamas.size));
  lines.push("CTO: " + String(selectedCtos.size));
  lines.push("ONT: " + String(selectedOnts));
  _OLT_OPERADORES_ORDEN.forEach((op) => {
    const nOp = operadorCounts[op] || 0;
    if (nOp > 0) lines.push(op + ": " + String(nOp));
  });
  return {
    error: null,
    lines: lines,
    count: n,
    resumen: {
      ramas: selectedRamas.size,
      ctos: selectedCtos.size,
      onts: selectedOnts,
      operadores: operadorCounts,
    },
  };
}

function _rowsPonesSeleccionados() {
  return _buildPonExportLines({ filterOperator: _oltExportFilterFromUi() });
}

function copiarPonesSeleccionados() {
  const res = _rowsPonesSeleccionados();
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  copyTextToClipboardOlt(res.lines.join("\n"));
}

function descargarCsv(filename, lines, delimiter) {
  const sep = delimiter || ",";
  const csv = lines
    .map((line) =>
      String(line)
        .split("\t")
        .map((v) => `"${String(v).replace(/"/g, '""')}"`)
        .join(sep)
    )
    .join("\r\n");
  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "pones_seleccionados.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportarPonesSeleccionadosCsv() {
  const filt = _oltExportFilterFromUi();
  const res = _buildPonExportLines({ filterOperator: filt });
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  const fname = filt
    ? "pones_seleccionados_" + _sanitizeExportBasename(filt) + ".csv"
    : "pones_seleccionados.csv";
  descargarCsv(fname, res.lines, ",");
  toastOlt("CSV exportado");
}

function _oltMetricPillHtml(n, label, kind, title) {
  const v = String(Math.max(0, Number(n) || 0));
  const empty = v === "0";
  return (
    '<span class="dashboard-metric-pill olt-metric-pill olt-metric-pill--' +
    kind +
    (empty ? " olt-metric-pill--empty" : "") +
    '" title="' +
    title +
    '">' +
    '<span class="dashboard-metric-pill__n olt-metric-pill__n">' +
    v +
    "</span> " +
    '<span class="dashboard-metric-pill__l olt-metric-pill__l">' +
    label +
    "</span></span>"
  );
}

function _oltOperadorPillHtml(n, operador) {
  const op = String(operador || "").trim().toUpperCase();
  const slug = op.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const v = String(Math.max(0, Number(n) || 0));
  return (
    '<span class="dashboard-metric-pill olt-metric-pill olt-metric-pill--operador olt-metric-pill--op-' +
    slug +
    '" title="ONT IN SERVICE · operador ' +
    op +
    '">' +
    '<span class="dashboard-metric-pill__n olt-metric-pill__n">' +
    v +
    "</span> " +
    '<span class="dashboard-metric-pill__l olt-metric-pill__l">' +
    op +
    "</span></span>"
  );
}

function _oltOperadorSummaryHtml(operadores) {
  const counts = operadores || _emptyOperadorCounts();
  const active = _OLT_OPERADORES_ORDEN.filter((op) => (counts[op] || 0) > 0);
  if (!active.length) return "";
  const pills = active
    .map((op) => _oltOperadorPillHtml(counts[op], op))
    .join(' <span class="olt-summary-sep" aria-hidden="true">·</span> ');
  return (
    '<span class="olt-selection-summary-operadores" aria-label="ONT IN SERVICE por operador">' +
    '<span class="olt-selection-operadores-label">Operador:</span> ' +
    pills +
    "</span>"
  );
}

function _oltPonSummaryHtml(pon, ramas, cto, ont, operadores) {
  const p = String(Math.max(0, Number(pon) || 0));
  const r = String(Math.max(0, Number(ramas) || 0));
  const c = String(Math.max(0, Number(cto) || 0));
  const o = String(Math.max(0, Number(ont) || 0));
  const emptyPon = p === "0";
  const main =
    '<span class="olt-selection-summary-main">' +
    '<span class="olt-selection-summary-label">Seleccionados:</span> ' +
    '<span class="olt-pon-selected-kicker' +
    (emptyPon ? " olt-pon-selected-kicker--empty" : "") +
    '" title="PON marcados; copiar/exportar incluye solo AID IN SERVICE">' +
    '<span class="olt-pon-selected-count">' +
    p +
    "</span> " +
    '<span class="olt-pon-selected-label">PON</span></span>' +
    ' <span class="olt-summary-sep" aria-hidden="true">·</span> ' +
    _oltMetricPillHtml(
      r,
      "RAMAs",
      "ramas",
      "RAMAs únicas con al menos un AID IN SERVICE en la selección"
    ) +
    ' <span class="olt-summary-sep" aria-hidden="true">·</span> ' +
    _oltMetricPillHtml(
      c,
      "CTO",
      "cto",
      "CTO únicas con al menos un AID IN SERVICE en la selección"
    ) +
    ' <span class="olt-summary-sep" aria-hidden="true">·</span> ' +
    _oltMetricPillHtml(
      o,
      "ONT",
      "ont",
      "Filas de inventario con estado IN SERVICE (copiar / exportar)"
    ) +
    "</span>";
  return main + _oltOperadorSummaryHtml(operadores);
}

function updatePonesSelectionSummary() {
  const el = document.getElementById("pon-selection-summary");
  if (!el) return;
  _syncOltExportOperatorSelect();
  const selectedPones = document.querySelectorAll(".pon-select:checked").length;
  if (!selectedPones) {
    el.innerHTML = _oltPonSummaryHtml(0, 0, 0, 0);
    return;
  }
  const res = _buildPonExportLines({ filterOperator: "" });
  if (res.error || !res.resumen) {
    el.innerHTML = _oltPonSummaryHtml(selectedPones, 0, 0, 0);
    return;
  }
  el.innerHTML = _oltPonSummaryHtml(
    selectedPones,
    res.resumen.ramas,
    res.resumen.ctos,
    res.resumen.onts,
    res.resumen.operadores
  );
}

function limpiarBusquedaOlt() {
  const input = document.getElementById("bus-olt");
  if (input) {
    input.value = "";
    if (typeof aplicarBusquedaOlt === "function") aplicarBusquedaOlt();
    input.focus();
  }
  const opSel = document.getElementById("olt-export-operador");
  if (opSel) opSel.value = "";
}

function colapsarTodoOlt() {
  _restoringOltState = true;
  Object.keys(state).forEach((id) => {
    if (state[id]) closeNode(id, true);
  });
  _restoringOltState = false;
  document.querySelectorAll("input.pon-select, input.pon-select-all").forEach((cb) => {
    cb.checked = false;
  });
  updatePonesSelectionSummary();
  limpiarBusquedaOlt();
  _saveOltStateSoon();
}

function childrenByParent(parentId) {
  return Array.from(document.querySelectorAll("[data-parent]")).filter(
    (el) => el.getAttribute("data-parent") === parentId
  );
}

function _saveOltStateSoon() {
  if (_restoringOltState) return;
  if (!_oltStateStore) return;
  _oltStateStore.saveSoon(buildOltDashboardStatePayload);
}

function _expandedNodeIdsOlt() {
  return Object.keys(state).filter((id) => !!state[id]);
}

function buildOltDashboardStatePayload() {
  const input = document.getElementById("bus-olt");
  return {
    q: String(input?.value || "").trim(),
    expandedNodeIds: _expandedNodeIdsOlt(),
    scrollY: Math.max(0, Math.floor(window.scrollY || 0)),
    ts: Date.now(),
  };
}

function persistOltDashboardState() {
  if (_restoringOltState || !_oltStateStore) return;
  _oltStateStore.save(buildOltDashboardStatePayload);
}

function readOltDashboardState() {
  if (!_oltStateStore) return null;
  return _oltStateStore.read((parsed) => {
    if (!parsed || typeof parsed !== "object") return null;
    return {
      q: typeof parsed.q === "string" ? parsed.q : "",
      expandedNodeIds: Array.isArray(parsed.expandedNodeIds)
        ? parsed.expandedNodeIds.filter((x) => typeof x === "string")
        : [],
      scrollY: Number.isFinite(parsed.scrollY) ? Number(parsed.scrollY) : 0,
    };
  });
}

function _getLtMetaFromUid(uid) {
  const td = document.querySelector("td.lt-row-toggle[data-uid='" + uid + "']");
  if (!td) return null;
  const row = td.closest("tr");
  if (!row) return null;
  const raw = (td.dataset.lt || "").trim();
  let lt = raw || null;
  if (!lt) {
    const j = td.dataset.ltJson;
    if (j != null && j !== "") {
      try {
        lt = JSON.parse(j);
      } catch (_err) {
        lt = null;
      }
    }
  }
  if (!lt) return null;
  return { lt, row };
}

async function _openNodeForRestore(nodeId) {
  if (!nodeId || state[nodeId]) return;

  const ltMeta = _getLtMetaFromUid(nodeId);
  if (ltMeta) {
    const { lt, row } = ltMeta;
    if (!ltInventarioCargado[nodeId] && !ltCargando[nodeId]) {
      ltCargando[nodeId] = true;
      try {
        await cargarInventarioLT(lt, nodeId, row);
        ltInventarioCargado[nodeId] = true;
      } catch (_err) {
      } finally {
        ltCargando[nodeId] = false;
        hideLtLoading(nodeId);
      }
    }
  }
  ensureNodeOpen(nodeId);
}

async function restoreOltDashboardState() {
  const input = document.getElementById("bus-olt");
  const forceCollapsedByTabSwitch =
    !!(window.consumeDashboardTabForceCollapse && window.consumeDashboardTabForceCollapse("/dashboard/olt"));
  if (forceCollapsedByTabSwitch) {
    try {
      sessionStorage.removeItem(_OLT_STATE_KEY);
    } catch (_err) {}
  }
  const stateSaved = readOltDashboardState();
  if (forceCollapsedByTabSwitch) {
    if (input) input.value = "";
    _restoringOltState = true;
    try {
      aplicarBusquedaOlt();
      colapsarTodoOlt();
    } finally {
      _restoringOltState = false;
    }
    return;
  }
  if (!stateSaved) return;

  if (input && stateSaved.q) {
    input.value = stateSaved.q;
  }

  _restoringOltState = true;
  try {
    aplicarBusquedaOlt();
    for (const nodeId of stateSaved.expandedNodeIds) {
      await _openNodeForRestore(nodeId);
    }
  } finally {
    _restoringOltState = false;
  }

  if (_oltStateStore) _oltStateStore.restoreScroll(stateSaved.scrollY);
}

const _OLT_TREE_ACCENT_CLASSES = ["olt-pon-row-accent", "olt-rama-row-accent", "olt-cto-row-accent"];

function _setTreeRowExpanded(el, accentClass, isOpen) {
  if (!el) return;
  if (accentClass) el.classList.toggle(accentClass, !!isOpen);
  el.setAttribute("aria-expanded", isOpen ? "true" : "false");
}

function _syncSiteHeadAccent(nodeId, isOpen) {
  const arrow = document.getElementById("arrow-" + nodeId);
  const head = arrow ? arrow.closest(".site-head.card") : null;
  _setTreeRowExpanded(head, "site-head-accent", isOpen);
}

function _syncLtRowAccent(uid, isOpen) {
  const row = document.getElementById("lt-row-" + uid);
  if (!row || !row.classList.contains("ltrow")) return;
  _setTreeRowExpanded(row, "olt-lt-row-accent", isOpen);
}

function _syncOltSectionAccent(nodeId, isOpen) {
  const section = document.querySelector('.olt-section[data-node-id="' + nodeId + '"]');
  if (!section) return;
  section.classList.toggle("olt-section-accent", !!isOpen);
  _setTreeRowExpanded(section.querySelector(":scope > .node.olt"), null, isOpen);
}

function _oltTreeAccentClassForKind(kindAttr) {
  const k = (kindAttr || "").trim();
  const u = k.toUpperCase();
  if (u === "PON") return "olt-pon-row-accent";
  if (u === "CTO") return "olt-cto-row-accent";
  if (u === "RAMA" || u === "FATC") return "olt-rama-row-accent";
  if (k === "Rama") return "olt-rama-row-accent";
  return null;
}

function _syncOltTreeRowAccent(nodeId, isOpen) {
  const row = document.querySelector('.olt-tree-row[data-node-id="' + nodeId + '"]');
  if (!row) return;
  row.classList.remove(..._OLT_TREE_ACCENT_CLASSES);
  const accent = isOpen ? _oltTreeAccentClassForKind(row.getAttribute("data-olt-tree-kind")) : null;
  _setTreeRowExpanded(row, accent, isOpen);
}

function _syncTreeNodeAccentVisual(nodeId, isOpen) {
  _syncSiteHeadAccent(nodeId, isOpen);
  _syncOltSectionAccent(nodeId, isOpen);
  _syncLtRowAccent(nodeId, isOpen);
  _syncOltTreeRowAccent(nodeId, isOpen);
}

function closeNode(id, skipSave) {
  state[id] = false;
  _syncTreeNodeAccentVisual(id, false);
  const arrow = document.getElementById("arrow-" + id);
  if (arrow) {
    arrow.textContent = "▶";
  }
  childrenByParent(id).forEach((el) => {
    el.classList.add("hidden");
    const child = el.getAttribute("data-node-id");
    if (child) {
      closeNode(child, true);
    }
  });
  if (!skipSave) {
    _saveOltStateSoon();
  }
}

function toggleNode(id, autoPotencias) {
  if (state[id]) {
    closeNode(id);
    return;
  }
  state[id] = true;
  _syncTreeNodeAccentVisual(id, true);
  const arrow = document.getElementById("arrow-" + id);
  if (arrow) {
    arrow.textContent = "▼";
  }
  childrenByParent(id).forEach((el) => {
    el.classList.remove("hidden");
  });
  if (autoPotencias !== false) {
    _autoPotenciaCtoOltAlExpandir(id);
  }
  _saveOltStateSoon();
}

function _oltTableTieneFilasPendientesPotencias(table) {
  if (!table) return false;
  for (const tr of table.querySelectorAll("tr[data-aid]")) {
    if (_oltFatSkipPotencias(tr)) continue;
    const tx = tr.children[OLT_COL_TX];
    if (tx && tx.classList.contains("olt-txrx-cell--loading")) return true;
  }
  return false;
}

function _autoPotenciaCtoOltAlExpandir(nodeId) {
  const ctoNode = document.querySelector("[data-node-id=\"" + String(nodeId).replace(/\\/g, "\\\\").replace(/"/g, '\\"') + "\"]");
  if (!ctoNode) return;
  if ((ctoNode.getAttribute("data-olt-tree-kind") || "").trim().toUpperCase() !== "CTO") return;
  const children = childrenByParent(nodeId);
  const shell = children.find((el) => el.classList.contains("olt-tree-table-shell"));
  const table = shell
    ? shell.querySelector("table.olt-tree-table")
    : children.find((el) => el.tagName === "TABLE" && el.classList.contains("olt-tree-table"));
  if (!table || !_oltTableTieneFilasPendientesPotencias(table)) return;
  const firstTr = table.querySelector("tr[data-aid]");
  const cto = decodeURIComponent((firstTr && firstTr.getAttribute("data-cto")) || "").trim();
  if (!cto) return;
  const wrap = ctoNode.closest("td");
  if (wrap && wrap._skipAutoPotenciasCto) return;
  const detailTr = ctoNode.closest("tr");
  const uid =
    detailTr && detailTr.id && detailTr.id.indexOf("detail-") === 0 ? detailTr.id.slice("detail-".length) : "";
  const ltRow = uid ? document.getElementById("lt-row-" + uid) : null;
  if (wrap && ltRow) {
    potenciaCto(cto, wrap, ltRow, null);
  }
}

function ensureNodeOpen(id, autoPotencias) {
  if (!id) {
    return;
  }
  if (!state[id]) {
    state[id] = true;
    _syncTreeNodeAccentVisual(id, true);
    const arrow = document.getElementById("arrow-" + id);
    if (arrow) {
      arrow.textContent = "▼";
    }
    childrenByParent(id).forEach((el) => {
      el.classList.remove("hidden");
    });
  }
  if (autoPotencias !== false) {
    _autoPotenciaCtoOltAlExpandir(id);
  }
  _saveOltStateSoon();
}

function _openAncestorsForNode(nodeId) {
  let currentId = String(nodeId || "").trim();
  while (currentId) {
    const nodeEl = document.querySelector('[data-node-id="' + currentId + '"]');
    if (!nodeEl) return;
    const parentId = (nodeEl.getAttribute("data-parent") || "").trim();
    if (!parentId) return;
    ensureNodeOpen(parentId);
    currentId = parentId;
  }
}

function _expandAllDescendantNodes(rootNodeId, autoPotencias) {
  const rootId = String(rootNodeId || "").trim();
  if (!rootId) return;
  ensureNodeOpen(rootId, autoPotencias);
  const stack = [rootId];
  while (stack.length) {
    const parentId = stack.pop();
    childrenByParent(parentId).forEach((child) => {
      const childId = (child.getAttribute("data-node-id") || "").trim();
      if (!childId) return;
      ensureNodeOpen(childId, autoPotencias);
      stack.push(childId);
    });
  }
}

function _expandOnlyTargetCto(ctoNodeId) {
  const targetId = String(ctoNodeId || "").trim();
  if (!targetId) return;
  const ctoNode = document.querySelector('[data-node-id="' + targetId + '"]');
  if (!ctoNode) return;
  const ramaNodeId = (ctoNode.getAttribute("data-parent") || "").trim();
  _openAncestorsForNode(targetId);
  if (ramaNodeId) {
    ensureNodeOpen(ramaNodeId);
    childrenByParent(ramaNodeId).forEach((child) => {
      const siblingId = (child.getAttribute("data-node-id") || "").trim();
      if (!siblingId || siblingId === targetId) return;
      if ((child.getAttribute("data-olt-tree-kind") || "").trim().toUpperCase() === "CTO") {
        closeNode(siblingId, true);
      }
    });
  }
  ensureNodeOpen(targetId);
}

function _esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function _formatPowerDbm(v) {
  return _npOlt() ? _npOlt().formatPowerDbm(v) : "-";
}

function _applyPotenciaEnFilaOlt(tr, txVal, rxVal, row) {
  if (!tr || _oltFatSkipPotencias(tr) || !_npOlt()) return;
  const tdTx = tr.children[OLT_COL_TX];
  const tdRx = tr.children[OLT_COL_RX];
  _npOlt().finalizeTxRxLoadingCell(tdTx, txVal, tr);
  _npOlt().finalizeTxRxLoadingCell(tdRx, rxVal, tr);
  if (row && tdRx) _addSemFromRx(row, tdRx.textContent);
}

function _addSem(row, res) {
  if (!res) return;
  const r = row.querySelector(".rojas");
  const a = row.querySelector(".amarillas");
  const v = row.querySelector(".verdes");
  if (r) r.textContent = (parseInt(r.textContent, 10) || 0) + (res.ROJAS || 0);
  if (a) a.textContent = (parseInt(a.textContent, 10) || 0) + (res.AMARILLAS || 0);
  if (v) v.textContent = (parseInt(v.textContent, 10) || 0) + (res.VERDES || 0);
}

function _clasif(rx) {
  return _npOlt() ? _npOlt().clasificarRxDbm(rx) : null;
}

function _addSemFromRx(row, rx) {
  const c = _clasif(rx);
  if (c === "rojo") _addSem(row, { ROJAS: 1, AMARILLAS: 0, VERDES: 0 });
  else if (c === "amarillo") _addSem(row, { ROJAS: 0, AMARILLAS: 1, VERDES: 0 });
  else if (c === "verde") _addSem(row, { ROJAS: 0, AMARILLAS: 0, VERDES: 1 });
}

function _recomputePeor(wrap, row) {
  let min = null;
  wrap.querySelectorAll("tr[data-aid]").forEach(tr => {
    const rxCell = tr.children[OLT_COL_RX];
    if (!rxCell) return;
    const t = rxCell.textContent.trim();
    if (t === "-" || t === "") return;
    const v = _npOlt() ? _npOlt().parseRxDbm(t) : null;
    if (v !== null && (min === null || v < min)) min = v;
  });
  const pe = row.querySelector(".peor");
  if (pe) pe.textContent = min != null ? String(min) : "-";
}

function sortNaturalKeys(keys) {
  return [...keys].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }));
}

function buildRamaBlockHtml(uid, rama, block, parentRamaId, depth) {
  block = block || {};
  const d = typeof depth === "number" && depth > 0 ? depth : 1;
  const enc = encodeURIComponent(rama).replace(/%/g, "_");
  const ramaId = parentRamaId ? parentRamaId + "_S_" + enc : uid + "_R_" + enc;
  const nestedHidden = parentRamaId ? " hidden" : "";
  const parentAttr = parentRamaId ? ` data-parent="${parentRamaId}"` : "";
  const u = String(rama).toUpperCase();
  const kindLabel =
    u.indexOf("-RATC-") !== -1 ? "RAMA" : u.indexOf("-FATC-") !== -1 ? "FATC" : "Rama";

  let html = `
            <div class="node olt-tree-row olt-tree-depth-${d}${nestedHidden}"
                 data-node-id="${ramaId}"${parentAttr}
                 data-olt-tree-kind="${kindLabel}"
                 onclick="toggleNode('${ramaId}')">
                <span class="rama-row-head">
                  <span class="rama-row-kind rama-row-kind--rama">${kindLabel}</span>
                  <span class="arrow" id="arrow-${ramaId}">▶</span>
                  <span class="mono rama-row-label">${_esc(rama)}</span>
                </span>
                <span class="rama-row-actions" onclick="event.stopPropagation()">
                  <button type="button" class="btn pot-rama" data-pot-rama="${encodeURIComponent(rama)}">Consultar RX</button>
                </span>
            </div>`;

  const ctos = block.CTOS || {};
  const ctoDepth = d + 1;
  const tblDepth = d + 2;

  for (const cto of sortNaturalKeys(Object.keys(ctos))) {
    const ctoId = ramaId + "_C_" + encodeURIComponent(cto).replace(/%/g, "_");

    html += `
                <div class="node olt-tree-row cto-head-row olt-tree-depth-${ctoDepth} olt-tree-cto hidden"
                     data-parent="${ramaId}"
                     data-node-id="${ctoId}"
                     data-olt-tree-kind="CTO"
                     onclick="toggleNode('${ctoId}')">
                    <span class="rama-row-kind rama-row-kind--cto">CTO</span>
                    <span class="arrow" id="arrow-${ctoId}">▶</span>
                    <span class="mono rama-row-label">${_esc(cto)}</span>
                    <span class="rama-row-actions" onclick="event.stopPropagation()">
                      <button type="button" class="btn-mini pot-cto" data-pot-cto="${encodeURIComponent(cto)}">Consultar RX</button>
                    </span>
                </div>

                <div class="table-wrap olt-tree-table-shell olt-tree-depth-${tblDepth} hidden" data-parent="${ctoId}">
                <table class="olt-tree-table">
                <tr><th>OUT</th><th>AID</th><th>Operador</th><th>Sitio</th><th>RAMA</th><th>ONT</th><th>Status</th><th>TX (dBm)</th><th>RX (dBm)</th></tr>`;

    (ctos[cto] || []).forEach((o, oix) => {
      html += `
                    <tr data-aid="${_esc(o.AID)}" data-rama="${encodeURIComponent(rama)}" data-cto="${encodeURIComponent(cto)}" data-fat-status="${_esc(o.STATUS || "")}">
                      ${_oltRowCellsHtml(o, rama, cto, oix + 1)}
                    </tr>`;
    });

    html += `</table></div>`;
  }

  const subs = block.SUBRAMAS || {};
  for (const sub of sortNaturalKeys(Object.keys(subs))) {
    html += buildRamaBlockHtml(uid, sub, subs[sub], ramaId, d + 1);
  }

  return html;
}

function buildPonBlockHtml(uid, pon, block) {
  const enc = encodeURIComponent(pon).replace(/%/g, "_");
  const ponId = uid + "_P_" + enc;
  const r = (block && block.RESUMEN) || {};
  const ramasN = Number(r.RAMAS || 0);
  const ctoN = Number(r.CTO_COUNT || 0);
  const ontN = Number(r.ONT_COUNT || 0);
  let html = `
            <div class="node olt-tree-row olt-tree-depth-1"
                 data-node-id="${ponId}"
                 data-olt-tree-kind="PON"
                 onclick="toggleNode('${ponId}')">
                <input type="checkbox"
                       class="pon-select"
                       data-uid="${uid}"
                       data-pon-id="${ponId}"
                       data-pon-label="${_esc(pon)}"
                       title="Seleccionar PON para exportación"
                       onclick="event.stopPropagation()">
                <span class="rama-row-head">
                  <span class="rama-row-kind rama-row-kind--pon">PON</span>
                  <span class="arrow" id="arrow-${ponId}">▶</span>
                  <span class="mono rama-row-label">${_esc(pon)}</span>
                </span>
                <span class="badge hide-sm">RAMA ${ramasN}</span>
                <span class="badge hide-sm">CTO ${ctoN}</span>
                <span class="badge hide-sm">ONT ${ontN}</span>
            </div>`;

  const ramas = block && block.RAMAS ? block.RAMAS : {};
  for (const rama of sortNaturalKeys(Object.keys(ramas))) {
    html += buildRamaBlockHtml(uid, rama, ramas[rama], ponId, 2);
  }
  return html;
}

function showLtLoading(uid) {
  const row = document.getElementById("lt-row-" + uid);
  const detailRow = document.getElementById("detail-" + uid);
  const arrow = document.getElementById("arrow-" + uid);
  if (!row || !detailRow) return;
  row.classList.add("lt-row-loading");
  row.setAttribute("aria-busy", "true");
  if (arrow) arrow.textContent = "▼";
  detailRow.classList.remove("hidden");
  detailRow.innerHTML =
    '<td colspan="10"><div class="lt-detail-loading" role="status" aria-live="polite">' +
    '<span class="lt-detail-spinner" aria-hidden="true"></span>' +
    "<span>Cargando inventario de red…</span></div></td>";
}

function hideLtLoading(uid) {
  const row = document.getElementById("lt-row-" + uid);
  if (row) {
    row.classList.remove("lt-row-loading");
    row.removeAttribute("aria-busy");
  }
}

function toggleLTCargar(lt, uid) {
  const detailRow = document.getElementById("detail-" + uid);
  const row = document.getElementById("lt-row-" + uid);
  if (!detailRow || !row) return;

  if (state[uid]) {
    closeNode(uid);
    return;
  }

  if (ltInventarioCargado[uid]) {
    toggleNode(uid);
    return;
  }

  if (ltCargando[uid]) return;
  ltCargando[uid] = true;

  const peCell = row.querySelector(".peor");
  const prevPe = peCell ? peCell.textContent : "-";
  if (peCell) peCell.textContent = "…";

  row.querySelector(".rojas").innerText = "0";
  row.querySelector(".amarillas").innerText = "0";
  row.querySelector(".verdes").innerText = "0";

  showLtLoading(uid);

  cargarInventarioLT(lt, uid, row)
    .then((wrap) => {
      ltInventarioCargado[uid] = true;
      if (peCell) peCell.textContent = prevPe;
      toggleNode(uid);
      _saveOltStateSoon();
    })
    .catch(() => {
      if (peCell) peCell.textContent = prevPe;
      const dr = document.getElementById("detail-" + uid);
      if (dr) {
        dr.classList.remove("hidden");
        dr.innerHTML =
          '<td colspan="10"><p class="lt-detail-error">No se pudo cargar el inventario. Reintentá o revisá la consola de red.</p></td>';
      }
      toastOlt("Error al cargar inventario LT");
    })
    .finally(() => {
      ltCargando[uid] = false;
      hideLtLoading(uid);
    });
}

function cargarInventarioLT(lt, uid, row) {
  const detailRow = document.getElementById("detail-" + uid);
  return fetch("/dashboard/olt/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "lt=" + encodeURIComponent(lt),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      ltInventarioData[uid] = data || {};
      const resumenLt = data.RESUMEN_LT || {};
      const ponCount = Number(resumenLt.PON_COUNT || 0);
      const ramasCount = Number(resumenLt.RAMAS || 0);
      const ctoCount = Number(resumenLt.CTO_COUNT || 0);
      const ontCount = Number(resumenLt.ONT_COUNT || 0);
      const ponCell = row.querySelector(".poncount");
      if (ponCell) ponCell.textContent = String(ponCount);

      let html =
        '<p class="hint">Inventario cargado. Expandí cada <strong>PON</strong> para ver RAMA (RATC) → FATC → CTO → ONT. <span class="muted">Las mismas ramas FATC se listan bajo cada RATC (sin vínculo padre/hijo en BD).</span> Al expandir una <strong>CTO</strong> o con <strong>Consultar RX</strong> se cargan las potencias (Altiplano).</p>';
      html += `<p class="hint"><strong>Impacto LT:</strong> PON ${ponCount} · RAMAs ${ramasCount} · CTO ${ctoCount} · ONT ${ontCount}</p>`;
      html += `<p class="hint rama-hint-no-margin"><label class="rama-cto-select-all-label"><input type="checkbox" class="pon-select-all" data-uid="${uid}"> Seleccionar todos los PON de este LT</label></p>`;

      const pones = sortNaturalKeys(Object.keys(data.PONES || {}));
      for (const pon of pones) {
        html += buildPonBlockHtml(uid, pon, data.PONES[pon]);
      }

      detailRow.innerHTML = `<td colspan="10">${html}</td>`;
      detailRow.classList.remove("hidden");

      const wrap = detailRow.querySelector("td");
      bindPotenciaButtons(wrap, row);
      updatePonesSelectionSummary();
      _saveOltStateSoon();
      return wrap;
    });
}

function findTrByAid(wrap, aid) {
  const s = String(aid ?? "");
  return Array.from(wrap.querySelectorAll("tr[data-aid]")).find((tr) => String(tr.getAttribute("data-aid") || "") === s);
}

function _findOltTableForCto(wrap, cto) {
  const c = String(cto || "").trim();
  if (!c || !wrap) return null;
  for (const tb of wrap.querySelectorAll("table.olt-tree-table")) {
    const tr = tb.querySelector("tr[data-aid]");
    if (tr && decodeURIComponent(tr.getAttribute("data-cto") || "").trim() === c) {
      return tb;
    }
  }
  return null;
}

function bindPotenciaButtons(wrap, row) {
  wrap.querySelectorAll("button.pot-rama").forEach((br) => {
    br.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const ramaNode = br.closest("[data-node-id]");
      const detailTd = wrap.nodeType === 1 ? wrap : null;
      if (ramaNode) {
        _openAncestorsForNode(ramaNode.getAttribute("data-node-id"));
        if (detailTd) detailTd._skipAutoPotenciasCto = true;
        _expandAllDescendantNodes(ramaNode.getAttribute("data-node-id"), false);
      }
      const p = potenciaRama(decodeURIComponent(br.getAttribute("data-pot-rama") || ""), wrap, row, br);
      if (detailTd && p && typeof p.finally === "function") {
        p.finally(() => {
          delete detailTd._skipAutoPotenciasCto;
        });
      } else if (detailTd) {
        delete detailTd._skipAutoPotenciasCto;
      }
    });
  });
  wrap.querySelectorAll("button.pot-cto").forEach((bc) => {
    bc.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const ctoNode = bc.closest("[data-node-id]");
      if (ctoNode) {
        _expandOnlyTargetCto(ctoNode.getAttribute("data-node-id"));
      }
      potenciaCto(decodeURIComponent(bc.getAttribute("data-pot-cto") || ""), wrap, row, bc);
    });
  });
}

function _setPotButtonLoading(btn, loading) {
  if (!btn) return;
  if (loading) {
    if (!btn.dataset.potLabel) btn.dataset.potLabel = (btn.textContent || "").trim() || "Consultar RX";
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
    lab.textContent = "Cargando TX/RX";
    inner.appendChild(sp);
    inner.appendChild(lab);
    btn.appendChild(inner);
    btn.setAttribute("aria-busy", "true");
  } else {
    btn.disabled = false;
    btn.classList.remove("pot-btn-loading");
    btn.removeAttribute("aria-busy");
    btn.textContent = btn.dataset.potLabel || "Consultar RX";
  }
}

function _setCtoOltTxRxCellsLoading(wrap, cto) {
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (decodeURIComponent(tr.getAttribute("data-cto") || "") !== cto) {
      return;
    }
    if (_oltFatSkipPotencias(tr)) return;
    [OLT_COL_TX, OLT_COL_RX].forEach((idx) => {
      const td = tr.children[idx];
      if (!td) {
        return;
      }
      td.setAttribute("aria-busy", "true");
      td.setAttribute("aria-label", "Cargando");
      td.classList.add("olt-txrx-cell--loading");
      td.innerHTML =
        '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';
    });
  });
}

function _oltFinalizeTxRxPendientesEn(wrap, filterFn) {
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (filterFn && !filterFn(tr)) return;
    const tdTx = tr.children[OLT_COL_TX];
    const tdRx = tr.children[OLT_COL_RX];
    const loading =
      (tdTx && tdTx.classList.contains("olt-txrx-cell--loading")) ||
      (tdRx && tdRx.classList.contains("olt-txrx-cell--loading"));
    if (loading) _applyPotenciaEnFilaOlt(tr, null, null, null);
  });
}

function _oltTxRxCellsStuckToDashForCto(wrap, cto) {
  _oltFinalizeTxRxPendientesEn(wrap, (tr) => decodeURIComponent(tr.getAttribute("data-cto") || "") === cto);
}

function _setOltTxRxCellsLoadingForRama(wrap, rama) {
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (decodeURIComponent(tr.getAttribute("data-rama") || "") !== rama) {
      return;
    }
    if (_oltFatSkipPotencias(tr)) return;
    [OLT_COL_TX, OLT_COL_RX].forEach((idx) => {
      const td = tr.children[idx];
      if (!td) {
        return;
      }
      td.setAttribute("aria-busy", "true");
      td.setAttribute("aria-label", "Cargando");
      td.classList.add("olt-txrx-cell--loading");
      td.innerHTML =
        '<span class="olt-txrx-loading-wrap" title="Cargando potencias…"><span class="olt-txrx-cell-spin" aria-hidden="true"></span></span>';
    });
  });
}

function _oltTxRxCellsStuckToDashForRama(wrap, rama) {
  _oltFinalizeTxRxPendientesEn(wrap, (tr) => decodeURIComponent(tr.getAttribute("data-rama") || "") === rama);
}

function _aplicarPotenciaRamaOlt(rama, wrap, row, data) {
  const res = data.__dashboard_resumen__;
  if (res) _addSem(row, res);

  Object.keys(data).forEach((k) => {
    if (k === "__dashboard_resumen__") return;
    const byAid = data[k];
    Object.keys(byAid).forEach((aid) => {
      const cell = byAid[aid];
      const tr = findTrByAid(wrap, String(aid));
      if (!tr) return;
      if (decodeURIComponent(tr.getAttribute("data-rama") || "") !== rama) return;
      if (_oltFatSkipPotencias(tr)) return;
      _applyPotenciaEnFilaOlt(tr, cell.TX, cell.RX, row);
    });
  });
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (decodeURIComponent(tr.getAttribute("data-rama") || "") !== rama) return;
    if (_oltFatSkipPotencias(tr)) return;
    const tdTx = tr.children[OLT_COL_TX];
    if (tdTx && tdTx.classList.contains("olt-txrx-cell--loading")) {
      _applyPotenciaEnFilaOlt(tr, null, null, row);
    }
  });
  _recomputePeor(wrap, row);
}

function potenciaRama(rama, wrap, row, btnEl) {
  const cacheKey = String(rama || "").trim().toUpperCase();
  const cached = _oltRamaPotenciasCache[cacheKey];
  if (cached && Date.now() - cached.ts < _oltRamaPotenciasCacheMs) {
    _aplicarPotenciaRamaOlt(rama, wrap, row, cached.data);
    toastOlt(`Potencias (cache): ${rama}`);
    return Promise.resolve();
  }

  _setPotButtonLoading(btnEl, true);
  _setOltTxRxCellsLoadingForRama(wrap, rama);
  return fetch("/dashboard/rama/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "rama=" + encodeURIComponent(rama),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
      _oltRamaPotenciasCache[cacheKey] = { ts: Date.now(), data };
      _aplicarPotenciaRamaOlt(rama, wrap, row, data);
      toastOlt(`Potencias actualizadas: ${rama}`);
    })
    .catch(() => {
      toastOlt("Error al consultar potencias (rama)");
      _oltTxRxCellsStuckToDashForRama(wrap, rama);
    })
    .finally(() => {
      _oltTxRxCellsStuckToDashForRama(wrap, rama);
      _setPotButtonLoading(btnEl, false);
    });
}

function potenciaCto(cto, wrap, row, btnEl) {
  const ctoKey = String(cto || "").trim();
  const table = _findOltTableForCto(wrap, ctoKey);
  if (table && table._oltCtoPotFetchPromise) {
    if (btnEl) {
      _setPotButtonLoading(btnEl, true);
      table._oltCtoPotFetchPromise.finally(() => _setPotButtonLoading(btnEl, false));
    }
    return table._oltCtoPotFetchPromise;
  }
  if (btnEl) _setPotButtonLoading(btnEl, true);
  _setCtoOltTxRxCellsLoading(wrap, ctoKey);
  const p = fetch("/dashboard/cto/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "cto=" + encodeURIComponent(ctoKey),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((arr) => {
      if (!Array.isArray(arr)) {
        return;
      }
      arr.forEach((rec) => {
        const tr = findTrByAid(wrap, rec.AID);
        if (!tr || decodeURIComponent(tr.getAttribute("data-cto") || "") !== ctoKey) {
          return;
        }
        if (_oltFatSkipPotencias(tr)) return;
        _applyPotenciaEnFilaOlt(tr, rec.TX, rec.RX, row);
      });
      const seenCto = new Set(arr.map((rec) => String(rec.AID || "")));
      wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
        if (decodeURIComponent(tr.getAttribute("data-cto") || "") !== ctoKey) return;
        if (_oltFatSkipPotencias(tr)) return;
        const aid = String(tr.getAttribute("data-aid") || "");
        if (!aid || seenCto.has(aid)) return;
        if (_npOlt().filaTieneAidConsulta(tr)) {
          _applyPotenciaEnFilaOlt(tr, null, null, row);
        }
      });
      _recomputePeor(wrap, row);
    })
    .catch(() => {
      toastOlt("Error al consultar potencias (CTO)");
      _oltTxRxCellsStuckToDashForCto(wrap, ctoKey);
    })
    .finally(() => {
      _oltTxRxCellsStuckToDashForCto(wrap, ctoKey);
      if (btnEl) _setPotButtonLoading(btnEl, false);
      if (table && table._oltCtoPotFetchPromise === p) {
        delete table._oltCtoPotFetchPromise;
      }
    });
  if (table) table._oltCtoPotFetchPromise = p;
  return p;
}

function _oltRowIsSearchVisible(tr) {
  const pb = tr.closest(".principal-block");
  if (!pb || pb.classList.contains("search-hide")) return false;
  const sec = tr.closest(".olt-section");
  if (!sec || sec.classList.contains("search-hide")) return false;
  const table = tr.closest("table");
  if (table && table.classList.contains("hidden")) return false;
  return true;
}

function _ltTextFromLtRow(tr) {
  const td = tr.querySelector("td.lt-row-toggle");
  if (td) {
    const fromData = (td.dataset.lt || "").trim();
    if (fromData) return fromData;
    const j = td.dataset.ltJson;
    if (j != null && j !== "") {
      try {
        const parsed = JSON.parse(j);
        if (parsed != null) return String(parsed);
      } catch (_) {
        /* ignorar JSON inválido */
      }
    }
  }
  const cell = tr.querySelector("td:nth-child(2)");
  return (cell && cell.textContent.trim()) || "";
}

function _oltQueryRankLt(ltL, q) {
  if (!ltL || !q) return -1;
  if (ltL === q) return 100;
  if (ltL.endsWith(q)) {
    const i = ltL.length - q.length;
    if (i === 0) return 100;
    const prev = ltL.charCodeAt(i - 1);
    const sep = prev === ".".charCodeAt(0) || prev === "_".charCodeAt(0) || prev === "-".charCodeAt(0);
    if (sep) return 92;
  }
  if (ltL.startsWith(q)) return 82;
  if (!ltL.includes(q)) return -1;
  if (q.length >= 10) return 55;
  if (q.length >= 7) return 45;
  if (q.length >= 5) return 32;
  if (q.length >= 3) return 22;
  return -1;
}

function enfocarFilaLtCoincidente(raw) {
  const q = raw.trim().toLowerCase();
  document.querySelectorAll("tr.ltrow.olt-lt-search-hit").forEach((tr) => {
    tr.classList.remove("olt-lt-search-hit");
  });
  if (!q) return;

  const rows = Array.from(document.querySelectorAll("tr.ltrow")).filter(_oltRowIsSearchVisible);
  let bestTr = null;
  let bestRank = -1;

  for (const tr of rows) {
    const ltL = _ltTextFromLtRow(tr).toLowerCase();
    const rank = _oltQueryRankLt(ltL, q);
    if (rank > bestRank) {
      bestRank = rank;
      bestTr = tr;
    }
  }

  if (!bestTr || bestRank < 22) return;

  bestTr.classList.add("olt-lt-search-hit");
  window.requestAnimationFrame(() => {
    const inp = document.getElementById("bus-olt");
    const typingInSearch =
      inp && (document.activeElement === inp || inp.closest(".field")?.contains(document.activeElement));
    bestTr.scrollIntoView({ block: "center", behavior: typingInSearch ? "nearest" : "smooth" });
    /* No mover foco al <tr> mientras se escribe: tabindex en la fila robaba el input */
    if (!typingInSearch) {
      try {
        bestTr.focus({ preventScroll: true });
      } catch (_) {
        /* ignore */
      }
    }
  });
}

function aplicarBusquedaOlt() {
  const raw = (document.getElementById("bus-olt")?.value || "").trim();
  const q = raw.toLowerCase();
  document.querySelectorAll(".principal-block").forEach((pb) => {
    const pName = (pb.getAttribute("data-principal") || "").toLowerCase();
    const sections = pb.querySelectorAll(".olt-section");
    if (!q) {
      sections.forEach((sec) => sec.classList.remove("search-hide"));
      pb.classList.remove("search-hide");
      return;
    }
    let visible = 0;
    sections.forEach((sec) => {
      const st = (sec.getAttribute("data-search") || "").toLowerCase();
      const ok = st.includes(q);
      sec.classList.toggle("search-hide", !ok);
      if (ok) visible++;
    });
    if (visible === 0 && pName.includes(q)) {
      sections.forEach((sec) => {
        sec.classList.remove("search-hide");
        visible++;
      });
    }
    pb.classList.toggle("search-hide", visible === 0);

    if (q && visible > 0 && !pb.classList.contains("search-hide")) {
      const pid = pb.getAttribute("data-pid");
      if (pid) ensureNodeOpen(pid);
      pb.querySelectorAll(".olt-section:not(.search-hide)").forEach((sec) => {
        const oid = sec.getAttribute("data-node-id");
        if (oid) ensureNodeOpen(oid);
      });
    }
  });
  window.requestAnimationFrame(() => {
    enfocarFilaLtCoincidente(raw);
  });
  _saveOltStateSoon();
}

let _busOltTimer = null;

window.addEventListener("load", () => {
  const inp = document.getElementById("bus-olt");
  if (inp) {
    inp.addEventListener("input", () => {
      if (_busOltTimer) clearTimeout(_busOltTimer);
      _busOltTimer = setTimeout(aplicarBusquedaOlt, 220);
    });
  }

  function ltFromToggleCell(td) {
    if (!td) return null;
    const raw = (td.dataset.lt || "").trim();
    if (raw) return raw;
    const j = td.dataset.ltJson;
    if (j == null || j === "") return null;
    try {
      return JSON.parse(j);
    } catch (err) {
      return null;
    }
  }

  document.body.addEventListener("click", (e) => {
    const tr = e.target.closest("tr.ltrow");
    if (!tr) return;
    const td = tr.querySelector("td.lt-row-toggle");
    if (!td) return;
    e.preventDefault();
    const uid = td.dataset.uid;
    const lt = ltFromToggleCell(td);
    if (lt == null || uid == null) return;
    toggleLTCargar(lt, uid);
  });

  document.body.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const tr = e.target.closest("tr.ltrow");
    if (!tr || document.activeElement !== tr) return;
    const td = tr.querySelector("td.lt-row-toggle");
    if (!td) return;
    e.preventDefault();
    const uid = td.dataset.uid;
    const lt = ltFromToggleCell(td);
    if (lt == null || uid == null) return;
    toggleLTCargar(lt, uid);
  });

  document.body.addEventListener("change", (e) => {
    const all = e.target.closest("input.pon-select-all");
    if (all) {
      const uid = all.getAttribute("data-uid") || "";
      const detail = document.getElementById("detail-" + uid);
      if (!detail) return;
      detail.querySelectorAll("input.pon-select").forEach((cb) => {
        cb.checked = !!all.checked;
      });
      updatePonesSelectionSummary();
      return;
    }
    const ponCb = e.target.closest("input.pon-select");
    if (ponCb) {
      updatePonesSelectionSummary();
    }
  });


  if (window.initNocPage) {
    initNocPage({
      page: "olt",
      searchSelector: "#bus-olt",
      onClear: function () {
        const el = document.getElementById("bus-olt");
        if (el) el.value = "";
        if (typeof aplicarBusquedaOlt === "function") aplicarBusquedaOlt();
      },
      onSearchChange: function () {
        if (typeof aplicarBusquedaOlt === "function") aplicarBusquedaOlt();
      },
    });
  }

  window.addEventListener("pagehide", () => persistOltDashboardState());
  window.addEventListener("beforeunload", () => persistOltDashboardState());
  window.addEventListener("scroll", _saveOltStateSoon, { passive: true });

  restoreOltDashboardState();
  updatePonesSelectionSummary();
});
