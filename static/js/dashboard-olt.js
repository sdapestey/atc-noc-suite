const state = {};
const ltInventarioCargado = {};
const ltCargando = {};
const ltInventarioData = {};
const _OLT_STATE_KEY = "oltDashboardStateV1";
let _toastTimerOlt = null;
let _restoringOltState = false;
const _oltStateStore = window.createNocPageStateStore
  ? window.createNocPageStateStore(_OLT_STATE_KEY, { debounceMs: 120 })
  : null;

/** Sin columna SN ni botón TX/RX por fila (alineado con dashboard RAMA / CTO). */
const OLT_COL_TX = 7;
const OLT_COL_RX = 8;
const OLT_COL_EST = 9;

function _oltFatSkipPotencias(tr) {
  const st = (tr.getAttribute("data-fat-status") || "").trim().toUpperCase();
  return st === "FREE" || st === "RESERVED";
}

function _hasPowerOlt(v) {
  return !(v === null || v === undefined || String(v).trim() === "" || String(v).trim() === "-");
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
  let estCell;
  if (st === "FREE") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
    estCell = '<td class="mono">-</td>';
  } else if (st === "RESERVED") {
    txCell = '<td class="mono">-</td>';
    rxCell = '<td class="mono">-</td>';
    estCell = '<td class="mono status-down">DOWN</td>';
  } else {
    txCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    rxCell = `<td class="mono olt-txrx-cell--loading" aria-busy="true" aria-label="Cargando">${spin}</td>`;
    estCell = '<td class="mono status-pending">Cargando...</td>';
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
                      ${rxCell}
                      ${estCell}`;
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

function _rowsPonesSeleccionados() {
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
          selectedRamas.add(rama);
          selectedCtos.add(rama + "||" + cto);
          selectedOnts += 1;
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
    return {
      error: "No hay Access ID en estado IN SERVICE para exportar con esa selección",
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
  return {
    error: null,
    lines: lines,
    count: n,
    resumen: {
      ramas: selectedRamas.size,
      ctos: selectedCtos.size,
      onts: selectedOnts,
    },
  };
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
  const res = _rowsPonesSeleccionados();
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  descargarCsv("pones_seleccionados.csv", res.lines, ",");
  toastOlt("CSV exportado");
}

function exportarPonesSeleccionados() {
  copiarPonesSeleccionados();
}

function exportarPonesSeleccionadosPortapapeles() {
  const res = _rowsPonesSeleccionados();
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  copyTextToClipboardOlt(res.lines.join("\n"));
}

function _oltMetricPillHtml(n, label, kind, title) {
  const v = String(Math.max(0, Number(n) || 0));
  const empty = v === "0";
  return (
    '<span class="olt-metric-pill olt-metric-pill--' +
    kind +
    (empty ? " olt-metric-pill--empty" : "") +
    '" title="' +
    title +
    '">' +
    '<span class="olt-metric-pill__n">' +
    v +
    "</span> " +
    '<span class="olt-metric-pill__l">' +
    label +
    "</span></span>"
  );
}

function _oltPonSummaryHtml(pon, ramas, cto, ont) {
  const p = String(Math.max(0, Number(pon) || 0));
  const r = String(Math.max(0, Number(ramas) || 0));
  const c = String(Math.max(0, Number(cto) || 0));
  const o = String(Math.max(0, Number(ont) || 0));
  const emptyPon = p === "0";
  return (
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
    )
  );
}

function updatePonesSelectionSummary() {
  const el = document.getElementById("pon-selection-summary");
  if (!el) return;
  const selectedPones = document.querySelectorAll(".pon-select:checked").length;
  if (!selectedPones) {
    el.innerHTML = _oltPonSummaryHtml(0, 0, 0, 0);
    return;
  }
  const res = _rowsPonesSeleccionados();
  if (res.error || !res.resumen) {
    el.innerHTML = _oltPonSummaryHtml(selectedPones, 0, 0, 0);
    return;
  }
  el.innerHTML = _oltPonSummaryHtml(
    selectedPones,
    res.resumen.ramas,
    res.resumen.ctos,
    res.resumen.onts
  );
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

function closeNode(id, skipSave) {
  state[id] = false;
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

function toggleNode(id) {
  if (state[id]) {
    closeNode(id);
    return;
  }
  state[id] = true;
  const arrow = document.getElementById("arrow-" + id);
  if (arrow) {
    arrow.textContent = "▼";
  }
  childrenByParent(id).forEach((el) => {
    el.classList.remove("hidden");
  });
  _autoPotenciaCtoOltAlExpandir(id);
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
  const detailTr = ctoNode.closest("tr");
  const uid =
    detailTr && detailTr.id && detailTr.id.indexOf("detail-") === 0 ? detailTr.id.slice("detail-".length) : "";
  const ltRow = uid ? document.getElementById("lt-row-" + uid) : null;
  if (wrap && ltRow) {
    potenciaCto(cto, wrap, ltRow, null);
  }
}

function ensureNodeOpen(id) {
  if (!id || state[id]) {
    return;
  }
  state[id] = true;
  const arrow = document.getElementById("arrow-" + id);
  if (arrow) {
    arrow.textContent = "▼";
  }
  childrenByParent(id).forEach((el) => {
    el.classList.remove("hidden");
  });
  _autoPotenciaCtoOltAlExpandir(id);
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

function _expandAllDescendantNodes(rootNodeId) {
  const rootId = String(rootNodeId || "").trim();
  if (!rootId) return;
  ensureNodeOpen(rootId);
  const stack = [rootId];
  while (stack.length) {
    const parentId = stack.pop();
    childrenByParent(parentId).forEach((child) => {
      const childId = (child.getAttribute("data-node-id") || "").trim();
      if (!childId) return;
      ensureNodeOpen(childId);
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
  if (v === null || v === undefined) return "-";
  const raw = String(v).trim();
  if (!raw || raw === "-" || raw === "⏳") return raw || "-";
  if (/dbm$/i.test(raw)) return raw;
  return raw + " dBm";
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
  if (rx == null || rx === "" || rx === "-") return null;
  const v = parseFloat(String(rx).replace(",", "."));
  if (!isFinite(v)) return null;
  if (v < -27) return "rojo";
  if (v <= -25) return "amarillo";
  return "verde";
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
    const v = parseFloat(t.replace(",", "."));
    if (isFinite(v) && (min === null || v < min)) min = v;
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
                <span class="olt-tree-kind rama-row-kind rama-row-kind--rama">${kindLabel}</span>
                <span class="arrow" id="arrow-${ramaId}">▶</span> <span class="olt-tree-label rama-row-label">${_esc(rama)}</span>
                <button type="button" class="btn-mini pot-rama" data-pot-rama="${encodeURIComponent(rama)}">Consultar</button>
            </div>`;

  const ctos = block.CTOS || {};
  const ctoDepth = d + 1;
  const tblDepth = d + 2;

  for (const cto of sortNaturalKeys(Object.keys(ctos))) {
    const ctoId = ramaId + "_C_" + encodeURIComponent(cto).replace(/%/g, "_");

    html += `
                <div class="node olt-tree-row olt-tree-depth-${ctoDepth} olt-tree-cto hidden"
                     data-parent="${ramaId}"
                     data-node-id="${ctoId}"
                     data-olt-tree-kind="CTO"
                     onclick="toggleNode('${ctoId}')">
                    <span class="olt-tree-kind rama-row-kind rama-row-kind--cto">CTO</span>
                    <span class="arrow" id="arrow-${ctoId}">▶</span> <span class="olt-tree-label rama-row-label">${_esc(cto)}</span>
                    <button type="button" class="btn-mini pot-cto" data-pot-cto="${encodeURIComponent(cto)}">Consultar</button>
                </div>

                <div class="table-wrap olt-tree-table-shell olt-tree-depth-${tblDepth} hidden" data-parent="${ctoId}">
                <table class="olt-tree-table">
                <tr><th>OUT</th><th>AID</th><th>Operador</th><th>Sitio</th><th>RAMA</th><th>ONT</th><th>Status</th><th>TX (dBm)</th><th>RX (dBm)</th><th>Estado</th></tr>`;

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
                <span class="olt-tree-kind">PON</span>
                <span class="arrow" id="arrow-${ponId}">▶</span> <span class="olt-tree-label">${_esc(pon)}</span>
                <span class="muted">RAMAs ${ramasN} · CTO ${ctoN} · ONT ${ontN}</span>
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
        '<p class="hint">Inventario cargado. Expandí cada <strong>PON</strong> para ver RAMA (RATC) → FATC → CTO → ONT. <span class="muted">Las mismas ramas FATC se listan bajo cada RATC (sin vínculo padre/hijo en BD).</span> Al expandir una <strong>CTO</strong> o con <strong>Consultar</strong> se cargan las potencias (Altiplano).</p>';
      html += `<p class="hint"><strong>Impacto LT:</strong> PON ${ponCount} · RAMAs ${ramasCount} · CTO ${ctoCount} · ONT ${ontCount}</p>`;
      html += `<p class="hint"><label><input type="checkbox" class="pon-select-all" data-uid="${uid}"> Seleccionar todos los PON de este LT</label></p>`;

      const pones = sortNaturalKeys(Object.keys(data.PONES || {}));
      for (const pon of pones) {
        html += buildPonBlockHtml(uid, pon, data.PONES[pon]);
      }

      detailRow.innerHTML = `<td colspan="10">${html}</td>`;
      detailRow.classList.remove("hidden");

      const wrap = detailRow.querySelector("td");
      bindPotenciaButtons(wrap, row);
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
      if (ramaNode) {
        _openAncestorsForNode(ramaNode.getAttribute("data-node-id"));
        _expandAllDescendantNodes(ramaNode.getAttribute("data-node-id"));
      }
      potenciaRama(decodeURIComponent(br.getAttribute("data-pot-rama") || ""), wrap, row, br);
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
    if (!btn.dataset.potLabel) btn.dataset.potLabel = (btn.textContent || "").trim() || "Consultar";
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
    btn.textContent = btn.dataset.potLabel || "Consultar";
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

function _oltTxRxCellsStuckToDashForCto(wrap, cto) {
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (decodeURIComponent(tr.getAttribute("data-cto") || "") !== cto) {
      return;
    }
    [OLT_COL_TX, OLT_COL_RX].forEach((idx) => {
      const td = tr.children[idx];
      if (td && td.classList && td.classList.contains("olt-txrx-cell--loading")) {
        td.classList.remove("olt-txrx-cell--loading");
        td.removeAttribute("aria-busy");
        td.removeAttribute("aria-label");
        td.textContent = "-";
      }
    });
  });
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
  wrap.querySelectorAll("tr[data-aid]").forEach((tr) => {
    if (decodeURIComponent(tr.getAttribute("data-rama") || "") !== rama) {
      return;
    }
    [OLT_COL_TX, OLT_COL_RX].forEach((idx) => {
      const td = tr.children[idx];
      if (td && td.classList && td.classList.contains("olt-txrx-cell--loading")) {
        td.classList.remove("olt-txrx-cell--loading");
        td.removeAttribute("aria-busy");
        td.removeAttribute("aria-label");
        td.textContent = "-";
      }
    });
  });
}

function potenciaRama(rama, wrap, row, btnEl) {
  _setPotButtonLoading(btnEl, true);
  _setOltTxRxCellsLoadingForRama(wrap, rama);
  fetch("/dashboard/rama/consultar", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "rama=" + encodeURIComponent(rama),
  })
    .then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then((data) => {
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
          const tdTx = tr.children[OLT_COL_TX];
          const tdRx = tr.children[OLT_COL_RX];
          const tdEst = tr.children[OLT_COL_EST];
          if (tdTx && tdRx) {
            tdTx.classList.remove("olt-txrx-cell--loading");
            tdTx.removeAttribute("aria-busy");
            tdTx.removeAttribute("aria-label");
            tdRx.classList.remove("olt-txrx-cell--loading");
            tdRx.removeAttribute("aria-busy");
            tdRx.removeAttribute("aria-label");
            tdTx.textContent = _formatPowerDbm(cell.TX);
            tdRx.textContent = _formatPowerDbm(cell.RX);
            if (tdEst) {
              tdEst.classList.remove("status-pending");
              const up = _hasPowerOlt(cell.TX) || _hasPowerOlt(cell.RX);
              tdEst.textContent = up ? "UP" : "DOWN";
              tdEst.classList.remove("status-up", "status-down");
              tdEst.classList.add(up ? "status-up" : "status-down");
            }
          }
        });
      });
      _recomputePeor(wrap, row);
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
        const tdTx = tr.children[OLT_COL_TX];
        const tdRx = tr.children[OLT_COL_RX];
        const tdEst = tr.children[OLT_COL_EST];
        if (tdTx && tdRx) {
          tdTx.classList.remove("olt-txrx-cell--loading");
          tdTx.removeAttribute("aria-busy");
          tdTx.removeAttribute("aria-label");
          tdRx.classList.remove("olt-txrx-cell--loading");
          tdRx.removeAttribute("aria-busy");
          tdRx.removeAttribute("aria-label");
          tdTx.textContent = _formatPowerDbm(rec.TX);
          tdRx.textContent = _formatPowerDbm(rec.RX);
          _addSemFromRx(row, rec.RX);
          if (tdEst) {
            tdEst.classList.remove("status-pending");
            const up = _hasPowerOlt(rec.TX) || _hasPowerOlt(rec.RX);
            tdEst.textContent = up ? "UP" : "DOWN";
            tdEst.classList.remove("status-up", "status-down");
            tdEst.classList.add(up ? "status-up" : "status-down");
          }
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
  _saveOltStateSoon();
}

window.addEventListener("load", () => {
  const inp = document.getElementById("bus-olt");
  if (inp) inp.addEventListener("input", aplicarBusquedaOlt);

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
