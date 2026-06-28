const state = {};
const ltInventarioCargado = {};
const ltCargando = {};
const ltInventarioData = {};
const _oltRamaPotenciasCache = {};
const _oltRamaPotenciasCacheMs = 45000;
const _OLT_LT_SUMMARY_COLSPAN = 6;
const _OLT_STATE_KEY = "oltDashboardStateV1";
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

function toastOlt(msg, opts) {
  if (!window.NocToast) return;
  const options = Object.assign({ durationMs: 2000 }, opts || {});
  window.NocToast.show("toast-olt", msg, options);
}

function copyTextToClipboardOlt(text, label) {
  const done = () =>
    toastOlt(
      label ? label + " copiados al portapapeles" : "Copiados al portapapeles"
    );
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

function _exportDateStamp() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + day;
}

function _collectPonExportData(opts) {
  const raw = opts && opts.filterOperator != null ? opts.filterOperator : "";
  const filterNorm = _normExportOp(raw);
  const applyFilter = filterNorm.length > 0;

  const selected = Array.from(document.querySelectorAll(".pon-select:checked"));
  if (selected.length === 0) {
    return { error: "Seleccioná al menos un PON", rows: [], selected: [] };
  }

  const rows = [];
  const selectedRamas = new Set();
  const selectedCtos = new Set();
  const selectedCtoCodes = new Set();
  const selectedAids = new Set();
  const operadorCounts = _emptyOperadorCounts();
  const aidsByOperador = {};
  _OLT_OPERADORES_ORDEN.forEach((op) => {
    aidsByOperador[op] = new Set();
  });

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
          selectedCtoCodes.add(cto);
          const aid = String(o.AID || "").trim();
          if (aid) selectedAids.add(aid);
          const opCanon = _canonicalOperadorOlt(o.OPERADOR);
          if (opCanon) {
            operadorCounts[opCanon] = (operadorCounts[opCanon] || 0) + 1;
            if (aid) aidsByOperador[opCanon].add(aid);
          }
          rows.push({
            pon: pon,
            rama: rama,
            cto: cto,
            aid: aid,
            operador: o.OPERADOR || "",
            ont: o.ONT || "",
          });
        });
      });
    });
  });

  if (rows.length === 0) {
    if (applyFilter) {
      return {
        error:
          "No hay Access ID IN SERVICE para ese operador con la selección actual",
        rows: [],
        selected: selected,
      };
    }
    return {
      error:
        "No hay Access ID en estado IN SERVICE para exportar con esa selección",
      rows: [],
      selected: selected,
    };
  }

  rows.sort((a, b) => {
    const byPon = String(a.pon).localeCompare(String(b.pon));
    if (byPon) return byPon;
    const byRama = String(a.rama).localeCompare(String(b.rama));
    if (byRama) return byRama;
    const byCto = String(a.cto).localeCompare(String(b.cto));
    if (byCto) return byCto;
    return String(a.aid).localeCompare(String(b.aid));
  });

  const sortAlpha = (x, y) => String(x).localeCompare(String(y));
  return {
    error: null,
    rows: rows,
    selected: selected,
    selectedRamas: selectedRamas,
    selectedCtos: selectedCtos,
    selectedCtoCodes: selectedCtoCodes,
    selectedAids: selectedAids,
    operadorCounts: operadorCounts,
    aidsByOperador: aidsByOperador,
    applyFilter: applyFilter,
    filterNorm: filterNorm,
    sortAlpha: sortAlpha,
  };
}

function _ponExportResumenLines(data) {
  const lines = ["", "RESUMEN:"];
  lines.push("PON: " + String(data.selected.length));
  lines.push("RAMAS: " + String(data.selectedRamas.size));
  lines.push("CTO: " + String(data.selectedCtos.size));
  lines.push("ONT: " + String(data.rows.length));
  _OLT_OPERADORES_ORDEN.forEach((op) => {
    const nOp = data.operadorCounts[op] || 0;
    if (nOp > 0) lines.push(op + ": " + String(nOp));
  });
  return lines;
}

function _formatPonExportFlatSparse(rows) {
  const lines = [["PON", "RAMA", "CTO", "ACCESS ID", "OPERADOR", "ONT"].join("\t")];
  let prevPon = null;
  let prevRama = null;
  let prevCto = null;
  rows.forEach((r) => {
    const ponCol = r.pon !== prevPon ? r.pon : "";
    const ramaCol = r.pon !== prevPon || r.rama !== prevRama ? r.rama : "";
    const ctoCol =
      r.pon !== prevPon || r.rama !== prevRama || r.cto !== prevCto ? r.cto : "";
    lines.push([ponCol, ramaCol, ctoCol, r.aid, r.operador, r.ont].join("\t"));
    prevPon = r.pon;
    prevRama = r.rama;
    prevCto = r.cto;
  });
  return lines;
}

function _formatPonExportGrouped(rows, data) {
  const lines = [];
  if (data.applyFilter && data.filterNorm) {
    lines.push("Filtro operador: " + data.filterNorm);
    lines.push("");
  }

  const ctoCounts = new Map();
  rows.forEach((r) => {
    const key = r.pon + "\0" + r.rama + "\0" + r.cto;
    ctoCounts.set(key, (ctoCounts.get(key) || 0) + 1);
  });

  let curPon = null;
  let curRama = null;
  let curCto = null;
  rows.forEach((r) => {
    if (r.pon !== curPon) {
      if (curPon !== null) lines.push("");
      lines.push("=== " + r.pon + " ===");
      curPon = r.pon;
      curRama = null;
      curCto = null;
    }
    if (r.rama !== curRama) {
      lines.push("RAMA: " + r.rama);
      curRama = r.rama;
      curCto = null;
    }
    if (r.cto !== curCto) {
      const key = r.pon + "\0" + r.rama + "\0" + r.cto;
      const cnt = ctoCounts.get(key) || 0;
      lines.push("  CTO: " + r.cto + " (" + cnt + " ONT)");
      lines.push("    ACCESS ID\tOPERADOR\tONT");
      curCto = r.cto;
    }
    lines.push("    " + [r.aid, r.operador, r.ont].join("\t"));
  });
  return lines;
}

function _buildPonExportLines(opts) {
  const data = _collectPonExportData(opts);
  if (data.error) {
    return { error: data.error, lines: [], count: 0 };
  }

  const format = opts && opts.format === "flat-sparse" ? "flat-sparse" : "grouped";
  const bodyLines =
    format === "flat-sparse"
      ? _formatPonExportFlatSparse(data.rows)
      : _formatPonExportGrouped(data.rows, data);
  const lines = bodyLines.concat(_ponExportResumenLines(data));
  const sortAlpha = data.sortAlpha;

  return {
    error: null,
    lines: lines,
    count: data.rows.length,
    resumen: {
      ramas: data.selectedRamas.size,
      ctos: data.selectedCtos.size,
      onts: data.rows.length,
      operadores: data.operadorCounts,
    },
    lists: {
      ramas: Array.from(data.selectedRamas).sort(sortAlpha),
      ctos: Array.from(data.selectedCtoCodes).sort(sortAlpha),
      aids: Array.from(data.selectedAids).sort(sortAlpha),
      aidsByOperador: Object.fromEntries(
        _OLT_OPERADORES_ORDEN.filter((op) => data.aidsByOperador[op].size > 0).map((op) => [
          op,
          Array.from(data.aidsByOperador[op]).sort(sortAlpha),
        ])
      ),
    },
  };
}

function _rowsPonesSeleccionados() {
  return _buildPonExportLines({
    filterOperator: _oltExportFilterFromUi(),
    format: "grouped",
  });
}

function copiarPonesSeleccionados() {
  const res = _rowsPonesSeleccionados();
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  copyTextToClipboardOlt(res.lines.join("\n"));
}

function _copyPonSelectionList(kind) {
  const res = _buildPonExportLines({ filterOperator: _oltExportFilterFromUi() });
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  const lists = res.lists || {};
  let items = [];
  let label = "";
  if (kind === "ramas") {
    items = lists.ramas || [];
    label = "RAMAs";
  } else if (kind === "cto") {
    items = lists.ctos || [];
    label = "CTO";
  } else if (kind === "ont") {
    items = lists.aids || [];
    label = "ONT";
  } else {
    return;
  }
  if (!items.length) {
    toastOlt("No hay " + label + " para copiar con esa selección");
    return;
  }
  copyTextToClipboardOlt(items.join("\n"), label);
}

function copiarRamasPonSeleccionados() {
  _copyPonSelectionList("ramas");
}

function copiarCtosPonSeleccionados() {
  _copyPonSelectionList("cto");
}

function copiarOntsPonSeleccionados() {
  _copyPonSelectionList("ont");
}

function _copyPonSelectionOperador(operador) {
  const op =
    _canonicalOperadorOlt(operador) ||
    String(operador || "")
      .trim()
      .toUpperCase();
  if (!op) return;
  const selected = document.querySelectorAll(".pon-select:checked").length;
  if (!selected) {
    toastOlt("Seleccioná al menos un PON");
    return;
  }
  const res = _buildPonExportLines({ filterOperator: "" });
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  const items =
    (res.lists && res.lists.aidsByOperador && res.lists.aidsByOperador[op]) || [];
  if (!items.length) {
    toastOlt("No hay Access ID IN SERVICE para operador " + op);
    return;
  }
  copyTextToClipboardOlt(items.join("\n"), op);
}

function copiarOperadorPonSeleccionados(operador) {
  _copyPonSelectionOperador(operador);
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
  a.download = filename || "pones_seleccionados_" + _exportDateStamp() + ".csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportarPonesSeleccionadosCsv() {
  const filt = _oltExportFilterFromUi();
  const res = _buildPonExportLines({
    filterOperator: filt,
    format: "flat-sparse",
  });
  if (res.error) {
    toastOlt(res.error);
    return;
  }
  const date = _exportDateStamp();
  const fname = filt
    ? "pones_seleccionados_" + date + "_" + _sanitizeExportBasename(filt) + ".csv"
    : "pones_seleccionados_" + date + ".csv";
  descargarCsv(fname, res.lines, ",");
  toastOlt("CSV exportado");
}

function _oltMetricPillHtml(n, label, kind, title, copyKind) {
  const v = String(Math.max(0, Number(n) || 0));
  const empty = v === "0";
  const copyable = !empty && copyKind;
  const copyTitle =
    copyKind === "ramas"
      ? "Clic para copiar lista de RAMAs (IN SERVICE, uno por línea)"
      : copyKind === "cto"
        ? "Clic para copiar lista de CTO (IN SERVICE, uno por línea)"
        : copyKind === "ont"
          ? "Clic para copiar Access ID IN SERVICE (uno por línea)"
          : title;
  return (
    '<span class="dashboard-metric-pill olt-metric-pill olt-metric-pill--' +
    kind +
    (empty ? " olt-metric-pill--empty" : "") +
    (copyable ? " olt-metric-pill--copy" : "") +
    '"' +
    (copyable
      ? ' role="button" tabindex="0" data-olt-copy="' +
        copyKind +
        '" aria-label="' +
        v +
        " " +
        label +
        ', copiar al portapapeles"'
      : "") +
    ' title="' +
    (copyable ? copyTitle : title) +
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
  const empty = v === "0";
  return (
    '<span class="dashboard-metric-pill olt-metric-pill olt-metric-pill--operador olt-metric-pill--op-' +
    slug +
    (empty ? " olt-metric-pill--empty" : " olt-metric-pill--copy") +
    '"' +
    (empty
      ? ""
      : ' role="button" tabindex="0" data-olt-copy="operador" data-olt-operador="' +
        op +
        '" aria-label="' +
        v +
        " ONT IN SERVICE operador " +
        op +
        ', copiar Access ID al portapapeles"') +
    ' title="' +
    (empty
      ? "ONT IN SERVICE · operador " + op
      : "Clic para copiar Access ID IN SERVICE de operador " +
        op +
        " (uno por línea)") +
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
    '<span class="olt-selection-summary-operadores olt-grand-totals__ops" aria-label="ONT IN SERVICE por operador">' +
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
  const metrics =
    '<span class="olt-selection-summary-main olt-grand-totals__main">' +
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
      "RAMAs únicas con al menos un AID IN SERVICE en la selección",
      "ramas"
    ) +
    ' <span class="olt-summary-sep" aria-hidden="true">·</span> ' +
    _oltMetricPillHtml(
      c,
      "CTO",
      "cto",
      "CTO únicas con al menos un AID IN SERVICE en la selección",
      "cto"
    ) +
    ' <span class="olt-summary-sep" aria-hidden="true">·</span> ' +
    _oltMetricPillHtml(
      o,
      "ONT",
      "ont",
      "Filas de inventario con estado IN SERVICE (copiar / exportar)",
      "ont"
    ) +
    "</span>";
  return (
    '<span class="olt-selection-summary-layout">' +
    '<span class="olt-selection-summary-label">Seleccionados:</span>' +
    metrics +
    _oltOperadorSummaryHtml(operadores) +
    "</span>"
  );
}

function _toggleOltSummaryMode(hasSelection) {
  const grandEl = document.getElementById("olt-grand-totals-row");
  const selEl = document.getElementById("pon-selection-summary");
  if (grandEl) grandEl.hidden = !!hasSelection;
  if (selEl) selEl.hidden = !hasSelection;
}

function updatePonesSelectionSummary() {
  const el = document.getElementById("pon-selection-summary");
  if (!el) return;
  _syncOltExportOperatorSelect();
  const selectedPones = document.querySelectorAll(".pon-select:checked").length;
  if (!selectedPones) {
    _toggleOltSummaryMode(false);
    el.innerHTML = _oltPonSummaryHtml(0, 0, 0, 0);
    return;
  }
  _toggleOltSummaryMode(true);
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

const _OLT_PON_KEY_RE = /^(BA_OLTA_[A-Za-z0-9_]+)-(\d+)-(\d+)$/;

function _parseOltPonKey(pk) {
  const m = String(pk || "").trim().match(_OLT_PON_KEY_RE);
  if (!m) return null;
  const ltName = m[1] + ".LT" + m[2];
  return {
    olt: m[1],
    lt: m[2],
    pon: m[3],
    lt_name: ltName,
    uid: ltName.replace(/\./g, "_"),
    pon_label: "PON " + m[3],
  };
}

function _ltUidFromName(ltName) {
  return String(ltName || "").trim().replace(/\./g, "_");
}

function _openLtAncestors(uid) {
  const row = document.getElementById("lt-row-" + uid);
  if (!row) return false;
  const pb = row.closest(".principal-block");
  if (pb) {
    const pid = pb.getAttribute("data-pid");
    if (pid) ensureNodeOpen(pid, false);
  }
  const oltSection = row.closest(".olt-section");
  if (oltSection) {
    const oid = oltSection.getAttribute("data-node-id");
    if (oid) ensureNodeOpen(oid, false);
  }
  return true;
}

function _oltUrlDeepLinkParams() {
  const params = new URLSearchParams(window.location.search);
  const selectPonRaw = params.get("select_pon") || params.get("pon_keys") || "";
  const ponKeys = selectPonRaw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const ltParam = (params.get("lt") || "").trim();
  const ponParam = (params.get("pon") || "").trim();
  const qParam = (params.get("q") || "").trim();
  return { ponKeys, ltParam, ponParam, qParam };
}

function _oltUrlHasDeepLink() {
  const { ponKeys, ltParam } = _oltUrlDeepLinkParams();
  return ponKeys.length > 0 || !!ltParam;
}

async function _ensureLtInventarioLoaded(uid) {
  const ltMeta = _getLtMetaFromUid(uid);
  if (!ltMeta) return null;
  const { lt, row } = ltMeta;
  if (!ltInventarioCargado[uid] && !ltCargando[uid]) {
    ltCargando[uid] = true;
    try {
      await cargarInventarioLT(lt, uid, row);
      ltInventarioCargado[uid] = true;
    } catch (_err) {
      return null;
    } finally {
      ltCargando[uid] = false;
      hideLtLoading(uid);
    }
  }
  ensureNodeOpen(uid, false);
  return document.getElementById("detail-" + uid);
}

function _selectPonCheckboxesInDetail(detailRow, labels, selectAll) {
  if (!detailRow) return 0;
  let n = 0;
  if (selectAll) {
    detailRow.querySelectorAll("input.pon-select").forEach((cb) => {
      cb.checked = true;
      n += 1;
    });
    return n;
  }
  const want = labels instanceof Set ? labels : new Set(labels || []);
  detailRow.querySelectorAll("input.pon-select").forEach((cb) => {
    const lbl = (cb.getAttribute("data-pon-label") || "").trim();
    if (want.has(lbl)) {
      cb.checked = true;
      n += 1;
    }
  });
  return n;
}

function _showOltDeepLinkLoading(show) {
  const el = document.getElementById("olt-deep-link-status");
  const summary = document.getElementById("pon-selection-summary");
  const stack = summary?.closest(".olt-selection-summary-stack");
  if (el) {
    el.hidden = !show;
    el.setAttribute("aria-busy", show ? "true" : "false");
  }
  if (summary) summary.hidden = !!show;
  if (stack) stack.classList.toggle("olt-selection-summary-stack--loading", !!show);
}

async function applyOltUrlDeepLink() {
  const { ponKeys, ltParam, ponParam, qParam } = _oltUrlDeepLinkParams();
  if (!ponKeys.length && !ltParam) return false;

  _showOltDeepLinkLoading(true);

  const input = document.getElementById("bus-olt");
  if (qParam && input) {
    input.value = qParam;
  } else if (ponKeys.length === 1) {
    const parsed = _parseOltPonKey(ponKeys[0]);
    if (parsed && input && !input.value.trim()) {
      input.value = parsed.olt;
    }
  } else if (ltParam && input && !input.value.trim()) {
    input.value = ltParam.split(".")[0] || ltParam;
  }
  aplicarBusquedaOlt();

  const byLt = new Map();
  for (const pk of ponKeys) {
    const parsed = _parseOltPonKey(pk);
    if (!parsed) continue;
    if (!byLt.has(parsed.uid)) {
      byLt.set(parsed.uid, { labels: new Set() });
    }
    byLt.get(parsed.uid).labels.add(parsed.pon_label);
  }

  if (!ponKeys.length && ltParam) {
    const uid = _ltUidFromName(ltParam);
    const labels = new Set();
    if (ponParam) labels.add(/^PON\s/i.test(ponParam) ? ponParam : "PON " + ponParam);
    byLt.set(uid, { labels, selectAll: !ponParam });
  }

  if (!byLt.size) {
    _showOltDeepLinkLoading(false);
    return false;
  }

  let selectedCount = 0;
  _restoringOltState = true;
  try {
    document.querySelectorAll("input.pon-select, input.pon-select-all").forEach((cb) => {
      cb.checked = false;
    });
    for (const [uid, spec] of byLt) {
      _openLtAncestors(uid);
      const detailRow = await _ensureLtInventarioLoaded(uid);
      selectedCount += _selectPonCheckboxesInDetail(detailRow, spec.labels, spec.selectAll);
    }
    updatePonesSelectionSummary();
    const firstUid = byLt.keys().next().value;
    const firstRow = firstUid ? document.getElementById("lt-row-" + firstUid) : null;
    if (firstRow) {
      firstRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  } finally {
    _restoringOltState = false;
    _showOltDeepLinkLoading(false);
  }
  if (selectedCount > 0) {
    toastOlt("Completado", { variant: "success" });
  }
  return selectedCount > 0;
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
  _hideOltRamaMapFor(id);
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
}

function sortNaturalKeys(keys) {
  return [...keys].sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }));
}

function buildRamaBlockHtml(uid, rama, block, parentRamaId, depth) {
  block = block || {};
  const d = typeof depth === "number" && depth > 0 ? depth : 1;
  const enc = encodeURIComponent(rama).replace(/%/g, "_");
  const ramaEnc = encodeURIComponent(rama);
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
                 data-rama="${ramaEnc}"
                 onclick="toggleNode('${ramaId}')">
                <span class="rama-row-head">
                  <span class="rama-row-kind rama-row-kind--rama">${kindLabel}</span>
                  <span class="arrow" id="arrow-${ramaId}">▶</span>
                  <span class="mono rama-row-label">${_esc(rama)}</span>
                </span>
                <span class="rama-row-actions" onclick="event.stopPropagation()">
                  <button type="button" class="btn pot-rama" data-pot-rama="${ramaEnc}">Consultar RX</button>
                  <button type="button" class="btn" data-olt-rama-map-btn onclick="event.stopPropagation(); verMapaRamaOlt(this);" title="Mapa con todas las CTO que tengan coordenadas" aria-expanded="false">Ver mapa</button>
                  <a class="btn btn-ghost" href="/dashboard/potencias-historico?ratc=${ramaEnc}&days=1" title="Abrir histórico de potencia para esta rama" onclick="event.stopPropagation();">Ver historico</a>
                </span>
            </div>
            <div class="olt-rama-map-branch olt-tree-depth-${d + 1} hidden" data-olt-rama-map-for="${ramaId}">
              <div class="rama-branch-map-panel hidden" data-rama-map-panel data-rama="${ramaEnc}" aria-hidden="true">
                <p class="hint rama-mapa-kicker">Mapa — CTO con ubicación</p>
                <p class="mono rama-mapa-rama-label" data-rama-mapa-label></p>
                <p class="hint rama-mapa-msg" aria-live="polite"></p>
                <div class="rama-mapa-canvas" data-rama-mapa-canvas hidden></div>
                <p class="hint rama-mapa-footer" aria-live="polite"></p>
              </div>
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

const _OLT_RAMA_MAP_URL = "/dashboard/rama/rama-map";
const _OLT_RAMA_CAMINO_GIS_URL = "/dashboard/camino-optico/gis";
const _OLT_RAMA_CTO_ADDRESS_URL = "/dashboard/rama/cto-address";

function _oltRamaCoordText(lat, lon) {
  if (window.NocMaps && window.NocMaps.coordTextFromLatLon) {
    return window.NocMaps.coordTextFromLatLon(lat, lon);
  }
  const latN = Number(lat);
  const lonN = Number(lon);
  if (!Number.isFinite(latN) || !Number.isFinite(lonN)) return "";
  return latN.toFixed(6) + ", " + lonN.toFixed(6);
}

function _oltExtendBoundsFromGeoJSON(bounds, gj) {
  const depthByType = {
    Point: 0,
    MultiPoint: 1,
    LineString: 1,
    MultiLineString: 2,
    Polygon: 2,
    MultiPolygon: 3,
  };
  function scanPair(lon, lat) {
    if (typeof lon !== "number" || typeof lat !== "number") return;
    if (Number.isNaN(lon) || Number.isNaN(lat)) return;
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
    bounds.extend(window.L.latLng(lat, lon));
  }
  function scan(coords, depth) {
    if (depth === 0) {
      scanPair(coords[0], coords[1]);
      return;
    }
    if (Array.isArray(coords)) coords.forEach((c) => scan(c, depth - 1));
  }
  (gj && gj.features ? gj.features : []).forEach((f) => {
    const g = f && f.geometry;
    if (!g || !g.coordinates) return;
    const d = depthByType[g.type];
    if (d != null) scan(g.coordinates, d);
  });
}

function _oltFitRamaMapToData(map, gj, markers) {
  const b = window.L.latLngBounds([]);
  if (gj) _oltExtendBoundsFromGeoJSON(b, gj);
  (markers || []).forEach((m) => {
    const lat = Number(m.lat);
    const lon = Number(m.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    b.extend(window.L.latLng(lat, lon));
  });
  if (!b.isValid()) return false;
  try {
    map.fitBounds(b, { padding: [28, 28], maxZoom: 17 });
    return true;
  } catch (_e) {
    return false;
  }
}

function _oltRefreshRamaMapTiles(map, basemapCtrl) {
  if (basemapCtrl && typeof basemapCtrl.redraw === "function") {
    basemapCtrl.redraw();
  } else if (map && window.NocMapTiles && window.NocMapTiles.refreshLeafletMapLayout) {
    window.NocMapTiles.refreshLeafletMapLayout(map);
    setTimeout(() => {
      if (map && window.NocMapTiles) window.NocMapTiles.refreshLeafletMapLayout(map);
    }, 120);
  }
}

function _loadOltRamaMapPanel(panel, rama) {
  const msg = panel.querySelector(".rama-mapa-msg");
  const footer = panel.querySelector(".rama-mapa-footer");
  const canvas = panel.querySelector("[data-rama-mapa-canvas]");
  if (!msg || !canvas) return;

  if (panel.dataset.oltRamaMapFetched === "1" && panel._ramaLeafletMap) {
    _oltRefreshRamaMapTiles(panel._ramaLeafletMap, panel._nocMapBasemap);
    return;
  }

  msg.textContent = "Cargando mapa…";
  if (footer) footer.textContent = "";
  canvas.hidden = true;

  Promise.all([
    fetch(_OLT_RAMA_MAP_URL + "?rama=" + encodeURIComponent(rama)).then((r) => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }),
    fetch(_OLT_RAMA_CAMINO_GIS_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ rama: rama }),
    })
      .then((r) => (r.ok ? r.json() : { ok: false, error: "Error HTTP GIS" }))
      .catch(() => ({ ok: false, error: "Error GIS" })),
  ])
    .then(([data, gis]) => {
      if (!data || !data.ok) {
        msg.textContent = (data && data.error) || "No se pudo cargar el mapa de la RAMA.";
        canvas.hidden = true;
        return;
      }
      const markers = Array.isArray(data.markers) ? data.markers : [];
      const sinCoord =
        data.ctos_sin_coordenadas != null ? Number(data.ctos_sin_coordenadas) : 0;
      const ctosTotal = data.ctos_total != null ? Number(data.ctos_total) : 0;
      const gj = gis && gis.ok && gis.geojson ? gis.geojson : null;
      const hasPath = !!(gj && Array.isArray(gj.features) && gj.features.length > 0);

      if (markers.length === 0 && !hasPath) {
        msg.textContent =
          ctosTotal === 0
            ? "No hay CTO en inventario para esta RAMA."
            : "Ninguna CTO de esta RAMA tiene coordenadas cargadas.";
        if (gis && gis.error) msg.textContent += " " + gis.error;
        canvas.hidden = true;
        if (footer) footer.textContent = sinCoord > 0 ? `${sinCoord} CTO sin coordenadas.` : "";
        return;
      }

      msg.textContent = "";
      canvas.hidden = false;
      if (footer) {
        let foot = `${markers.length} CTO en el mapa`;
        if (sinCoord > 0) foot += ` · ${sinCoord} sin coordenadas`;
        if (hasPath) foot += " · trazado ci_op visible";
        footer.textContent = foot + ".";
      }

      if (typeof window.L === "undefined") {
        msg.textContent = "No se pudo cargar el mapa (Leaflet).";
        canvas.hidden = true;
        return;
      }

      let map = panel._ramaLeafletMap;
      if (!map) {
        if (window.NocMapTiles && window.NocMapTiles.createLeafletMap) {
          const created = window.NocMapTiles.createLeafletMap(canvas, { marker: false, zoom: 11 });
          map = created ? created.map : null;
          if (created) panel._nocMapBasemap = created.basemap;
        }
        if (!map) {
          const mapOpts =
            window.NocLeafletMap && window.NocLeafletMap.baseMapOptions
              ? window.NocLeafletMap.baseMapOptions()
              : { attributionControl: true, zoomControl: true, scrollWheelZoom: false };
          map = window.L.map(canvas, mapOpts);
          if (window.NocMapTiles && window.NocMapTiles.addBasemapLayer) {
            panel._nocMapBasemap = window.NocMapTiles.addBasemapLayer(map, window.L);
          }
          if (window.NocLeafletMap && window.NocLeafletMap.attachScrollActivation) {
            window.NocLeafletMap.attachScrollActivation(map, canvas);
          }
          if (window.NocMapFullscreen) {
            window.NocMapFullscreen.attachMapFullscreen(map, canvas);
          }
        }
        panel._ramaLeafletMap = map;
      }

      if (panel._ramaMarkerLayer) {
        map.removeLayer(panel._ramaMarkerLayer);
        panel._ramaMarkerLayer = null;
      }
      if (panel._ramaPathLayer) {
        map.removeLayer(panel._ramaPathLayer);
        panel._ramaPathLayer = null;
      }

      if (hasPath) {
        try {
          panel._ramaPathLayer = window.L.geoJSON(gj, {
            style: function () {
              return {
                color: "#22c55e",
                weight: 6,
                opacity: 1,
                lineCap: "round",
                lineJoin: "round",
              };
            },
            filter: function (feature) {
              return !!(feature && feature.geometry);
            },
          }).addTo(map);
        } catch (_ePath) {
          panel._ramaPathLayer = null;
        }
      }

      const fg = window.L.featureGroup();
      markers.forEach((mk) => {
        const lat = Number(mk.lat);
        const lon = Number(mk.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const pointStyle = {
          radius: 9,
          fillColor: "#3b82f6",
          color: "#e0f2fe",
          weight: 2,
          opacity: 1,
          fillOpacity: 0.95,
        };
        const marker = window.L.circleMarker([lat, lon], pointStyle);
        const cto = String(mk.cto || "").trim();
        const coordText = _oltRamaCoordText(lat, lon);
        const popupHtml =
          window.NocMaps && window.NocMaps.ctoPopupHtml
            ? window.NocMaps.ctoPopupHtml(cto, lat, lon, "", { showAddrLoading: true, mapsLink: true })
            : "";
        if (window.NocMaps && window.NocMaps.wireCtoCircleMarker) {
          window.NocMaps.wireCtoCircleMarker(marker, popupHtml, pointStyle, coordText, {
            map,
            toastId: "toast-olt",
          });
        }
        if (cto && window.NocMaps && window.NocMaps.wireCtoAddressPrefetch) {
          window.NocMaps.wireCtoAddressPrefetch(
            marker,
            _OLT_RAMA_CTO_ADDRESS_URL + "?cto=" + encodeURIComponent(cto),
            (addr) =>
              window.NocMaps.ctoPopupHtml(cto, lat, lon, addr, {
                showAddrLoading: false,
                mapsLink: true,
              })
          );
        }
        fg.addLayer(marker);
      });
      if (fg.getLayers().length > 0) {
        fg.addTo(map);
        panel._ramaMarkerLayer = fg;
      }

      panel.dataset.oltRamaMapFetched = "1";
      requestAnimationFrame(() => {
        if (!_oltFitRamaMapToData(map, gj, markers)) {
          map.setView([-34.6, -58.38], 11);
        }
        _oltRefreshRamaMapTiles(map, panel._nocMapBasemap);
      });
    })
    .catch(() => {
      msg.textContent = "No se pudo cargar el mapa.";
      canvas.hidden = true;
    });
}

function _hideOltRamaMapFor(ramaId) {
  const id = String(ramaId || "").trim();
  if (!id) return;
  const esc = id.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const branch = document.querySelector('[data-olt-rama-map-for="' + esc + '"]');
  if (!branch) return;
  const panel = branch.querySelector("[data-rama-map-panel]");
  branch.classList.add("hidden");
  if (panel) {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
  }
  const row = document.querySelector('[data-node-id="' + esc + '"][data-rama]');
  const mapBtn = row && row.querySelector("[data-olt-rama-map-btn]");
  if (mapBtn) {
    mapBtn.textContent = "Ver mapa";
    mapBtn.setAttribute("aria-expanded", "false");
  }
}

function verMapaRamaOlt(btn) {
  if (!btn) return;
  const row = btn.closest("[data-rama]");
  if (!row) return;
  const rama = decodeURIComponent(row.getAttribute("data-rama") || "").trim();
  const ramaId = row.getAttribute("data-node-id");
  if (!rama || !ramaId) return;
  const branch = document.querySelector('[data-olt-rama-map-for="' + ramaId.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"]');
  if (!branch) return;
  const panel = branch.querySelector("[data-rama-map-panel]");
  if (!panel) return;

  if (!panel.classList.contains("hidden")) {
    _hideOltRamaMapFor(ramaId);
    return;
  }

  branch.classList.remove("hidden");
  panel.classList.remove("hidden");
  panel.setAttribute("aria-hidden", "false");
  btn.textContent = "Ocultar mapa";
  btn.setAttribute("aria-expanded", "true");
  const labelEl = panel.querySelector("[data-rama-mapa-label]");
  if (labelEl) labelEl.textContent = rama;
  _loadOltRamaMapPanel(panel, rama);
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
    '<td colspan="' +
    _OLT_LT_SUMMARY_COLSPAN +
    '"><div class="lt-detail-loading" role="status" aria-live="polite">' +
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

  showLtLoading(uid);

  cargarInventarioLT(lt, uid, row)
    .then((wrap) => {
      ltInventarioCargado[uid] = true;
      toggleNode(uid);
      _saveOltStateSoon();
    })
    .catch(() => {
      const dr = document.getElementById("detail-" + uid);
      if (dr) {
        dr.classList.remove("hidden");
        dr.innerHTML =
          '<td colspan="' +
          _OLT_LT_SUMMARY_COLSPAN +
          '"><p class="lt-detail-error">No se pudo cargar el inventario. Reintentá o revisá la consola de red.</p></td>';
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

      detailRow.innerHTML = `<td colspan="${_OLT_LT_SUMMARY_COLSPAN}">${html}</td>`;
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

let _oltLtScrollTimer = null;
let _oltLastLtScrollKey = "";

function _cancelOltLtRowScroll() {
  if (_oltLtScrollTimer) clearTimeout(_oltLtScrollTimer);
  _oltLtScrollTimer = null;
  _oltLastLtScrollKey = "";
}

function _oltLtRowMostlyInView(tr) {
  if (!tr) return false;
  const r = tr.getBoundingClientRect();
  const pad = 56;
  const vh = window.innerHeight || document.documentElement.clientHeight || 0;
  return r.top >= pad && r.bottom <= vh - pad;
}

function _scrollOltLtRowSmooth(tr) {
  if (!tr || !tr.scrollIntoView) return;
  tr.scrollIntoView({ block: "center", behavior: "smooth" });
}

/** Scroll suave a fila LT tras abrir sitio/OLT; no roba foco del buscador. */
function _scheduleOltLtRowScroll(raw, tr) {
  if (_oltLtScrollTimer) clearTimeout(_oltLtScrollTimer);
  const key = raw.trim().toLowerCase();
  if (!tr || !key) return;
  _oltLtScrollTimer = setTimeout(() => {
    _oltLtScrollTimer = null;
    const inp = document.getElementById("bus-olt");
    const qNow = (inp && inp.value != null ? inp.value : raw).trim().toLowerCase();
    if (qNow !== key) return;
    if (_oltLastLtScrollKey === key && _oltLtRowMostlyInView(tr)) return;
    _oltLastLtScrollKey = key;
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!tr.isConnected || !_oltRowIsSearchVisible(tr)) return;
        _scrollOltLtRowSmooth(tr);
      });
    });
  }, 48);
}

function enfocarFilaLtCoincidente(raw) {
  const q = raw.trim().toLowerCase();
  document.querySelectorAll("tr.ltrow.olt-lt-search-hit").forEach((tr) => {
    tr.classList.remove("olt-lt-search-hit");
  });
  if (!q) {
    _cancelOltLtRowScroll();
    return;
  }

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

  if (!bestTr || bestRank < 22) {
    _cancelOltLtRowScroll();
    return;
  }

  bestTr.classList.add("olt-lt-search-hit");
  _scheduleOltLtRowScroll(raw, bestTr);
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
  enfocarFilaLtCoincidente(raw);
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

  const ponSummaryEl = document.getElementById("pon-selection-summary");
  if (ponSummaryEl) {
    const triggerPonSummaryCopy = (target) => {
      const pill = target.closest("[data-olt-copy]");
      if (!pill || !ponSummaryEl.contains(pill)) return;
      const kind = pill.getAttribute("data-olt-copy");
      if (kind === "ramas") copiarRamasPonSeleccionados();
      else if (kind === "cto") copiarCtosPonSeleccionados();
      else if (kind === "ont") copiarOntsPonSeleccionados();
      else if (kind === "operador") {
        const op = pill.getAttribute("data-olt-operador");
        if (op) copiarOperadorPonSeleccionados(op);
      }
    };
    ponSummaryEl.addEventListener("click", (e) => {
      triggerPonSummaryCopy(e.target);
    });
    ponSummaryEl.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const pill = e.target.closest("[data-olt-copy]");
      if (!pill) return;
      e.preventDefault();
      triggerPonSummaryCopy(pill);
    });
  }


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

  (async function bootOltDashboard() {
    if (_oltUrlHasDeepLink()) {
      await applyOltUrlDeepLink();
    } else {
      const { qParam } = _oltUrlDeepLinkParams();
      if (qParam) {
        const input = document.getElementById("bus-olt");
        if (input) input.value = qParam;
        aplicarBusquedaOlt();
      } else {
        await restoreOltDashboardState();
      }
    }
    updatePonesSelectionSummary();
  })();
});
