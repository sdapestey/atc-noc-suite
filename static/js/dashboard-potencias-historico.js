let powerChart = null;
let selectedDays = 30;
let lastRATC = "";
let legendVisible = true;
const snapshotColors = ["#f43f5e", "#22d3ee", "#d946ef", "#fb7185", "#06b6d4"];
const chartCanvas = document.getElementById("power-chart");
const chartStage = document.getElementById("chart-stage");
const noDataEl = document.getElementById("no-data");

function _historicoPanelVisible(el, visible) {
  if (!el) return;
  el.hidden = !visible;
  el.classList.toggle("is-hidden", !visible);
}

function _historicoToast(msg) {
  let el = document.getElementById("historico-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "historico-toast";
    el.className = "historico-toast";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.classList.add("historico-toast--show");
  clearTimeout(_historicoToast._t);
  _historicoToast._t = setTimeout(function () {
    el.classList.remove("historico-toast--show");
  }, 2200);
}

function _copyHistoricoAccessId(accessId) {
  const text = String(accessId || "").trim();
  if (!text) return;
  const done = function () {
    _historicoToast("Access ID copiado: " + text);
  };
  const fallback = function () {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      done();
    } catch (_err) {
      _historicoToast("No se pudo copiar al portapapeles");
    }
    document.body.removeChild(ta);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(fallback);
  } else {
    fallback();
  }
}
const colors = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#06b6d4", "#84cc16", "#f97316", "#a855f7", "#22c55e"];

function _themePalette() {
  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  if (isLight) {
    return {
      grid: "rgba(31, 35, 40, 0.14)",
      ticks: "rgba(31, 35, 40, 0.76)",
      axisTitle: "rgba(31, 35, 40, 0.84)"
    };
  }
  return {
    // Más contraste en dark para que la grilla no se pierda.
    grid: "rgba(230, 237, 243, 0.24)",
    ticks: "rgba(230, 237, 243, 0.90)",
    axisTitle: "rgba(230, 237, 243, 0.92)"
  };
}

function setKPIs(data) {
  const ponEl = document.getElementById("kpi-pon");
  const ponVal = data.pon || "-";
  ponEl.innerText = ponVal;
  ponEl.title = ponVal && ponVal !== "-" ? ponVal : "";
  document.getElementById("kpi-onts").innerText = String(data.total_onts || 0);
  document.getElementById("kpi-median").innerText = String(data.median || "-") + " dBm";
  const days = Number(data.days || selectedDays || 30);
  const rangeLabel = days === 1 ? "24h" : (String(days) + "d");
  const statusEl = document.getElementById("kpi-status");
  const hintEl = document.getElementById("kpi-status-hint");
  statusEl.innerText = data.status || "-";
  statusEl.classList.remove("status-ok", "status-warn", "status-neutral");
  if ((data.status || "").toLowerCase() === "activo") {
    statusEl.classList.add("status-ok");
    hintEl.innerText = "con datos en " + rangeLabel;
  } else if ((data.status || "").toLowerCase().includes("sin")) {
    statusEl.classList.add("status-warn");
    hintEl.innerText = "sin muestras en " + rangeLabel;
  } else {
    statusEl.classList.add("status-neutral");
    hintEl.innerText = "estado no disponible";
  }
}

function buildLegend(items) {
  const legendWrap = document.getElementById("legend-wrap");
  const toggleLegendBtn = document.getElementById("btn-toggle-legend");
  const btnShowAll = document.getElementById("btn-show-all");
  const btnHideAll = document.getElementById("btn-hide-all");
  const legendContainer = document.getElementById("legend-container");
  legendContainer.innerHTML = "";
  if (!items || !items.length) {
    _historicoPanelVisible(legendWrap, false);
    toggleLegendBtn.disabled = true;
    btnShowAll.disabled = true;
    btnHideAll.disabled = true;
    return;
  }
  items.forEach(function (item) {
    const row = document.createElement("div");
    row.className = "historico-legend-item";
    if ((item.label || "").toLowerCase().includes("umbral")) {
      row.setAttribute("data-threshold", "1");
    }
    const chk = document.createElement("input");
    chk.type = "checkbox";
    chk.className = "historico-legend-check";
    chk.setAttribute("data-dataset-index", String(item.index));
    chk.checked = !powerChart.isDatasetVisible(item.index) ? false : true;
    chk.addEventListener("change", function () {
      powerChart.setDatasetVisibility(item.index, chk.checked);
      powerChart.update();
    });
    const dot = document.createElement("span");
    dot.className = "historico-legend-dot";
    dot.style.borderColor = item.color;
    const text = document.createElement("span");
    text.className = "historico-legend-text";
    text.innerText = item.label;
    row.appendChild(chk);
    row.appendChild(dot);
    row.appendChild(text);
    legendContainer.appendChild(row);
  });
  _historicoPanelVisible(legendWrap, legendVisible);
  toggleLegendBtn.disabled = false;
  toggleLegendBtn.innerText = legendVisible ? "Ocultar leyenda" : "Mostrar leyenda";
  btnShowAll.disabled = false;
  btnHideAll.disabled = false;
}

function _isOntDatasetLabel(label) {
  return String(label || "").trim().toUpperCase().startsWith("ONT ");
}

function _isUmbralDataset(ds) {
  return String(ds.label || "").toLowerCase().includes("umbral");
}

function _isSnapshotDatasetLabel(label) {
  return String(label || "").trim().toUpperCase().startsWith("RX MANUAL ONT ");
}

function _umbralDbmDesdeDatasetLabel(label) {
  var s = String(label || "");
  if (s.indexOf("-27") !== -1) return -27;
  if (s.indexOf("-25") !== -1) return -25;
  return -27;
}

function plotDatasetsFromChart() {
  return powerChart.data.datasets.map(function (d, idx) {
    return {label: d.label, color: d.borderColor, index: idx};
  });
}

function _upsertLabelAtTimestamp(ts) {
  const labels = powerChart.data.labels;
  let idx = labels.indexOf(ts);
  if (idx !== -1) return idx;
  let i = 0;
  while (i < labels.length && labels[i] < ts) {
    i += 1;
  }
  labels.splice(i, 0, ts);
  powerChart.data.datasets.forEach(function (ds) {
    if (_isUmbralDataset(ds)) {
      const val = _umbralDbmDesdeDatasetLabel(ds.label);
      ds.data.splice(i, 0, val);
      return;
    }
    if (_isSnapshotDatasetLabel(ds.label)) {
      ds.data.splice(i, 0, null);
      return;
    }
    ds.data.splice(i, 0, null);
  });
  return i;
}

function _applyRecentZoom() {
  if (!powerChart || !powerChart.options || !powerChart.options.scales || !powerChart.options.scales.x) {
    return;
  }
  const labels = powerChart.data.labels || [];
  if (labels.length < 3) {
    powerChart.update();
    return;
  }
  const keep = Math.min(12, labels.length);
  const xScale = powerChart.options.scales.x;
  xScale.min = labels.length - keep;
  xScale.max = labels.length - 1;
  powerChart.update();
}

function _setSnapshotKpiHint(message) {
  const el = document.getElementById("kpi-snapshot-hint");
  if (el) el.innerText = message;
}

function _roundToSingleDecimal(value) {
  return Math.round(Number(value) * 10) / 10;
}

function _median(numbers) {
  if (!numbers.length) return null;
  const sorted = numbers.slice().sort(function (a, b) { return a - b; });
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid];
  return (sorted[mid - 1] + sorted[mid]) / 2;
}

function _clearOntCtoSummary() {
  var wrap = document.getElementById("ont-cto-summary-wrap");
  var tbody = document.getElementById("ont-cto-summary-tbody");
  var cap = document.getElementById("ont-cto-summary-caption");
  if (tbody) tbody.innerHTML = "";
  if (cap) cap.textContent = "";
  if (wrap) wrap.hidden = true;
}

function _rxDbmSemaforoTone(db) {
  return window.NocPower ? window.NocPower.rxHistoricoTone(db) : "";
}

function _worstRxDbmSemaforoTone(v1, v2) {
  return window.NocPower ? window.NocPower.worstRxHistoricoTone(v1, v2) : "";
}

function _stripOntRxSemaforo(tr) {
  tr.classList.remove(
    "historico-cto-summary__ont--rx-ok",
    "historico-cto-summary__ont--rx-warn",
    "historico-cto-summary__ont--rx-bad"
  );
  tr.querySelectorAll("[data-rx-tone-cell]").forEach(function (cell) {
    cell.classList.remove(
      "historico-cto-summary__cell--rx-ok",
      "historico-cto-summary__cell--rx-warn",
      "historico-cto-summary__cell--rx-bad"
    );
    cell.removeAttribute("data-rx-tone-cell");
  });
}

function _applyOntRowRxSemaforo(tr, lastHistDbm, actualDbm) {
  _stripOntRxSemaforo(tr);
  var rowTone = _worstRxDbmSemaforoTone(lastHistDbm, actualDbm);
  if (rowTone === "warn") tr.classList.add("historico-cto-summary__ont--rx-warn");
  else if (rowTone === "bad") tr.classList.add("historico-cto-summary__ont--rx-bad");
}

function _groupOntSummaryByCto(rows) {
  var groups = [];
  var cur = null;
  (rows || []).forEach(function (r) {
    var ctoRaw = r && r.cto != null ? String(r.cto).trim() : "";
    var ctoKey = ctoRaw || "—";
    if (!cur || cur.ctoKey !== ctoKey) {
      cur = { ctoKey: ctoKey, ctoLabel: ctoRaw || "—", onts: [] };
      groups.push(cur);
    }
    cur.onts.push(r);
  });
  return groups;
}

function _buildOntCtoTable(payload) {
  var wrap = document.getElementById("ont-cto-summary-wrap");
  var tbody = document.getElementById("ont-cto-summary-tbody");
  var cap = document.getElementById("ont-cto-summary-caption");
  if (!wrap || !tbody) return;
  tbody.innerHTML = "";
  var rows = (payload && payload.ont_summary) || [];
  var groups = _groupOntSummaryByCto(rows);
  groups.forEach(function (g) {
    var trGroup = document.createElement("tr");
    trGroup.className = "historico-cto-summary__group";
    var tdGroup = document.createElement("td");
    tdGroup.colSpan = 6;
    tdGroup.textContent = g.ctoLabel;
    trGroup.appendChild(tdGroup);
    tbody.appendChild(trGroup);
    g.onts.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.className = "historico-cto-summary__ont";
      var key = String(r && r.ont_key != null ? r.ont_key : "").trim();
      tr.setAttribute("data-ont-key", key);
      var lastHistNum =
        r.last_hist_rx !== null && r.last_hist_rx !== undefined && r.last_hist_rx !== ""
          ? Number(r.last_hist_rx)
          : null;
      tr.dataset.lastHistRx =
        lastHistNum !== null && Number.isFinite(lastHistNum) ? String(lastHistNum) : "";

      var tdSp = document.createElement("td");
      tdSp.className = "historico-cto-summary__spacer";
      tdSp.innerHTML = "&nbsp;";
      tr.appendChild(tdSp);

      var tdOnt = document.createElement("td");
      tdOnt.className = "historico-cto-summary__ont-label";
      var accessId = String((r && r.access_id != null) ? r.access_id : "").trim();
      if (accessId) {
        tdOnt.textContent = key ? "ONT " + key : "—";
        tdOnt.classList.add("historico-cto-summary__ont-label--copy");
        tdOnt.setAttribute("data-access-id", accessId);
        tdOnt.setAttribute("role", "button");
        tdOnt.setAttribute("tabindex", "0");
        tdOnt.setAttribute(
          "title",
          "Clic para copiar Access ID " + accessId + " al portapapeles"
        );
        tdOnt.setAttribute("aria-label", "ONT " + (key || "—") + ", copiar Access ID " + accessId);
      } else {
        tdOnt.textContent = key ? "ONT " + key : "—";
        if (key) {
          tdOnt.title = "Access ID no disponible en inventario para ONT " + key;
        }
      }
      tr.appendChild(tdOnt);

      var tdHist = document.createElement("td");
      tdHist.textContent =
        lastHistNum !== null && Number.isFinite(lastHistNum)
          ? String(_roundToSingleDecimal(lastHistNum))
          : "—";
      tr.appendChild(tdHist);

      var tdTs = document.createElement("td");
      tdTs.textContent = r.last_hist_ts ? String(r.last_hist_ts) : "—";
      tr.appendChild(tdTs);

      var tdRx = document.createElement("td");
      tdRx.textContent = "—";
      tr.appendChild(tdRx);

      var tdDelta = document.createElement("td");
      tdDelta.textContent = "—";
      tr.appendChild(tdDelta);

      _applyOntRowRxSemaforo(tr, lastHistNum, null);
      tbody.appendChild(tr);
    });
  });
  if (cap) {
    cap.textContent =
      "Agrupado por CTO. Umbrales RX como consulta índice (clasificar_rx_dbm): rojo si Rx < −27 dBm; amarillo si −27 < Rx ≤ −25 dBm; verde si Rx > −25 dBm (Rx = −27 dBm es verde). Las líneas del gráfico marcan −27 y −25 dBm. Las filas se resaltan en amarillo o rojo según el peor valor entre último histórico y Rx actual. «Rx actual» y «Δ» al pulsar Consultar RX; Δ = Rx actual menos el último punto histórico en el gráfico inmediatamente anterior a esa consulta. Clic en el nombre ONT copia el Access ID.";
  }
  wrap.hidden = rows.length === 0;
}

function _fillOntCtoRxAfterSnapshot(payload, labelIdx) {
  var tbody = document.getElementById("ont-cto-summary-tbody");
  if (!tbody || !payload || !powerChart) return;
  var samples = (Array.isArray(payload.samples) ? payload.samples : []).filter(function (s) {
    return String(s && s.ont_key != null ? s.ont_key : "").trim() !== "";
  });
  var sampleMap = {};
  samples.forEach(function (s) {
    sampleMap[String(s.ont_key).trim()] = s.rx_dbm;
  });
  tbody.querySelectorAll("tr[data-ont-key]").forEach(function (tr) {
    var key = tr.getAttribute("data-ont-key");
    var cells = tr.querySelectorAll("td");
    if (!key || cells.length < 6) return;
    var ds = _findOntDataset(key);
    var lastH = ds ? _findLastHistoricRxBefore(ds, labelIdx) : {value: null, tsLabel: null};
    var manualRaw = sampleMap[key];
    var manualNum =
      manualRaw !== null && manualRaw !== undefined && Number.isFinite(Number(manualRaw))
        ? Number(manualRaw)
        : null;
    cells[4].textContent = manualNum != null ? String(_roundToSingleDecimal(manualNum)) : "—";
    if (manualNum != null && lastH.value != null) {
      var d = _roundToSingleDecimal(manualNum - lastH.value);
      cells[5].textContent = (d >= 0 ? "+" : "") + String(d);
    } else {
      cells[5].textContent = "—";
    }
    var lastHistNum =
      tr.dataset.lastHistRx !== "" && Number.isFinite(Number(tr.dataset.lastHistRx))
        ? Number(tr.dataset.lastHistRx)
        : null;
    _applyOntRowRxSemaforo(tr, lastHistNum, manualNum);
  });
  var wrap = document.getElementById("ont-cto-summary-wrap");
  if (wrap) wrap.hidden = tbody.querySelectorAll("tr[data-ont-key]").length === 0;
}

function _clearOntCtoRxSnapshotCells() {
  var tbody = document.getElementById("ont-cto-summary-tbody");
  if (!tbody) return;
  tbody.querySelectorAll("tr[data-ont-key]").forEach(function (tr) {
    var cells = tr.querySelectorAll("td");
    if (cells.length >= 6) {
      cells[4].textContent = "—";
      cells[5].textContent = "—";
    }
    var lastHistNum =
      tr.dataset.lastHistRx !== "" && Number.isFinite(Number(tr.dataset.lastHistRx))
        ? Number(tr.dataset.lastHistRx)
        : null;
    _applyOntRowRxSemaforo(tr, lastHistNum, null);
  });
}

function _findOntDataset(labelOntKey) {
  var want = "ONT " + String(labelOntKey || "").trim();
  if (!powerChart || !powerChart.data || !powerChart.data.datasets) return null;
  for (var i = 0; i < powerChart.data.datasets.length; i++) {
    if (String(powerChart.data.datasets[i].label || "") === want) return powerChart.data.datasets[i];
  }
  return null;
}

function _findLastHistoricRxBefore(dataset, beforeIdx) {
  if (!dataset || !Array.isArray(dataset.data) || !powerChart) {
    return { value: null, tsLabel: null };
  }
  var labels = powerChart.data.labels || [];
  var start = Math.min(beforeIdx - 1, dataset.data.length - 1);
  for (var j = start; j >= 0; j--) {
    var v = dataset.data[j];
    if (v !== null && v !== undefined && Number.isFinite(Number(v))) {
      return { value: Number(v), tsLabel: labels[j] != null ? String(labels[j]) : null };
    }
  }
  return { value: null, tsLabel: null };
}

function mergeSnapshot(payload) {
  if (!payload || !payload.ok || !powerChart) return { validCount: 0, totalCount: 0, medianValue: null };
  const ts = payload.timestamp;
  const sampleRows = (payload.samples || []).filter(function (s) {
    return String(s && s.ont_key != null ? s.ont_key : "").trim() !== "";
  });
  const sampleMap = {};
  sampleRows.forEach(function (s) {
    const k = String(s.ont_key).trim();
    sampleMap[k] = s.rx_dbm;
  });
  const idx = _upsertLabelAtTimestamp(ts);
  const validValues = [];

  powerChart.data.datasets.forEach(function (ds, dsIndex) {
    if (!_isOntDatasetLabel(ds.label)) return;
    const m = ds.label.match(/^ONT\s+(.+)$/);
    const key = m ? m[1].trim() : "";
    const v = sampleMap[key];
    if (v === undefined || v === null) return;
    const num = Number(v);
    if (!Number.isFinite(num)) return;
    validValues.push(num);

    const snapshotLabel = "RX manual ONT " + key;
    let snapshotDataset = powerChart.data.datasets.find(function (candidate) {
      return String(candidate.label) === snapshotLabel;
    });
    if (!snapshotDataset) {
      snapshotDataset = {
        type: "scatter",
        label: snapshotLabel,
        data: powerChart.data.labels.map(function () { return null; }),
        borderColor: snapshotColors[dsIndex % snapshotColors.length],
        backgroundColor: snapshotColors[dsIndex % snapshotColors.length],
        pointRadius: 6,
        pointHoverRadius: 8,
        pointBorderWidth: 1.5,
        showLine: false,
      };
      powerChart.data.datasets.push(snapshotDataset);
    }
    snapshotDataset.data[idx] = num;
  });

  powerChart.update();
  buildLegend(plotDatasetsFromChart());
  _fillOntCtoRxAfterSnapshot(payload, idx);
  return {
    validCount: validValues.length,
    totalCount: sampleRows.length,
    medianValue: _median(validValues),
    timestamp: ts,
  };
}

function _syncLegendChecks() {
  document.querySelectorAll(".historico-legend-check[data-dataset-index]").forEach(function (el) {
    const idx = Number(el.getAttribute("data-dataset-index"));
    if (!Number.isFinite(idx) || !powerChart) return;
    el.checked = !!powerChart.isDatasetVisible(idx);
  });
}

function applyThemeToChart() {
  if (!powerChart || !powerChart.options || !powerChart.options.scales) return;
  const palette = _themePalette();
  if (powerChart.options.scales.x) {
    if (powerChart.options.scales.x.grid) {
      powerChart.options.scales.x.grid.color = palette.grid;
    }
    if (powerChart.options.scales.x.ticks) {
      powerChart.options.scales.x.ticks.color = palette.ticks;
    }
  }
  if (powerChart.options.scales.y) {
    if (powerChart.options.scales.y.grid) {
      powerChart.options.scales.y.grid.color = palette.grid;
    }
    if (powerChart.options.scales.y.ticks) {
      powerChart.options.scales.y.ticks.color = palette.ticks;
    }
    if (powerChart.options.scales.y.title) {
      powerChart.options.scales.y.title.color = palette.axisTitle;
    }
  }
  // Repaint rápido sin animación para evitar "fade" ilegible al cambiar tema.
  powerChart.update("none");
}

function updateDeepLink() {
  const ratc = String(document.getElementById("ratc-input").value || "").trim();
  const params = new URLSearchParams(window.location.search);
  if (ratc) params.set("ratc", ratc);
  else params.delete("ratc");
  params.set("days", String(selectedDays));
  const next = window.location.pathname + "?" + params.toString();
  window.history.replaceState(null, "", next);
}

function resetDashboard() {
  document.getElementById("ratc-input").value = "";
  lastRATC = "";
  _clearOntCtoSummary();
  setKPIs({pon: "-", total_onts: 0, median: "-", status: "Sin datos"});
  _setSnapshotKpiHint("sin snapshot manual RX");
  noDataEl.innerText = "Ingresa una rama RATC para visualizar el historico de potencia Rx.";
  noDataEl.style.display = "";
  _historicoPanelVisible(chartStage, false);
  document.getElementById("btn-export").disabled = true;
  document.getElementById("btn-consultar-ahora").disabled = true;
  document.getElementById("btn-reset-zoom").disabled = true;
  document.getElementById("btn-toggle-legend").disabled = true;
  document.getElementById("btn-show-all").disabled = true;
  document.getElementById("btn-hide-all").disabled = true;
  buildLegend([]);
  updateDeepLink();
  if (powerChart) {
    powerChart.destroy();
    powerChart = null;
  }
}

function renderChart(data) {
  _buildOntCtoTable(data);
  if (powerChart) powerChart.destroy();
  const axisPalette = _themePalette();
  var rawDatasets = data.datasets || [];
  const datasets = rawDatasets.map(function (d, idx) {
    return {
      ...d,
      borderColor: colors[idx % colors.length],
      borderWidth: 2,
      pointRadius: 1,
      pointHoverRadius: 4
    };
  });
  const threshold27 = {
    label: "Umbral -27 dBm",
    data: (data.labels || []).map(() => -27),
    borderColor: "rgba(239, 68, 68, 0.85)",
    borderWidth: 1.5,
    borderDash: [4, 4],
    pointRadius: 0,
    fill: false
  };
  const threshold25 = {
    label: "Umbral -25 dBm",
    data: (data.labels || []).map(() => -25),
    borderColor: "rgba(245, 158, 11, 0.85)",
    borderWidth: 1.5,
    borderDash: [6, 4],
    pointRadius: 0,
    fill: false
  };
  const plotDatasets = datasets.concat([threshold27, threshold25]);

  powerChart = new Chart(chartCanvas.getContext("2d"), {
    type: "line",
    data: { labels: data.labels || [], datasets: plotDatasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      resizeDelay: 150,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (context) {
              var ds = context.dataset;
              var y = context.parsed != null ? context.parsed.y : context.raw;
              var base = ds.label != null ? String(ds.label) : "";
              if (y === null || y === undefined || (typeof y === "number" && !Number.isFinite(y))) {
                return base + ": —";
              }
              return base + ": " + String(y);
            },
          },
        },
        zoom: {
          zoom: {
            drag: { enabled: true },
            mode: "x"
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: axisPalette.grid
          },
          ticks: {
            autoSkip: true,
            maxTicksLimit: selectedDays === 30 ? 9 : 12,
            maxRotation: 45,
            minRotation: 0,
            color: axisPalette.ticks,
          }
        },
        y: {
          grid: {
            color: axisPalette.grid
          },
          ticks: {
            color: axisPalette.ticks
          },
          title: {
            display: true,
            text: "Potencia Rx (dBm)",
            color: axisPalette.axisTitle
          }
        }
      }
    }
  });
  buildLegend(
    plotDatasets.map(function (d, idx) {
      return { label: d.label, color: d.borderColor, index: idx };
    })
  );
  document.getElementById("btn-reset-zoom").disabled = false;
  _setSnapshotKpiHint("sin snapshot manual RX");
}

async function fetchData() {
  const ratc = String(document.getElementById("ratc-input").value || "").trim();
  if (!ratc) {
    return false;
  }

  const btn = document.getElementById("btn-search");
  btn.disabled = true;
  btn.innerText = "Consultando...";
  noDataEl.style.display = "none";
  document.getElementById("btn-export").disabled = true;
  document.getElementById("btn-consultar-ahora").disabled = true;

  try {
    const response = await fetch(
      "/api/potencias-historico/" + encodeURIComponent(ratc) + "?days=" + String(selectedDays)
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "No se pudo consultar historico");

    lastRATC = ratc;
    setKPIs(payload);
    renderChart(payload);
    _historicoPanelVisible(chartStage, true);
    document.getElementById("btn-export").disabled = false;
    document.getElementById("btn-consultar-ahora").disabled = false;
    updateDeepLink();
    return true;
  } catch (err) {
    _historicoPanelVisible(chartStage, false);
    noDataEl.style.display = "";
    setKPIs({pon: "-", total_onts: 0, median: "-", status: "Sin datos"});
    buildLegend([]);
    _clearOntCtoSummary();
    const msg = String(err.message || "");
    if (msg.toLowerCase().includes("no encontrada")) {
      noDataEl.innerText = "RATC no encontrada en inventario.";
    } else if (msg.toLowerCase().includes("sin muestras")) {
      noDataEl.innerText = msg;
    } else {
      noDataEl.innerText = "Error interno de consulta.";
    }
    updateDeepLink();
    return false;
  } finally {
    btn.disabled = false;
    btn.innerText = "Buscar";
  }
}

function _setConsultarRxLoading(btn, loading) {
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
    lab.textContent = "Cargando RX";
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

async function consultarAhora() {
  const ratc = String(document.getElementById("ratc-input").value || "").trim();
  if (!ratc) return;

  const btn = document.getElementById("btn-consultar-ahora");
  _setConsultarRxLoading(btn, true);

  try {
    if (!powerChart || lastRATC !== ratc) {
      const loaded = await fetchData();
      if (!loaded || !powerChart) {
        _clearOntCtoSummary();
        return;
      }
    }

    const resp = await fetch(
      "/api/potencias-historico/" + encodeURIComponent(ratc) + "/consultar-ahora",
      {method: "POST"}
    );
    const payload = await resp.json();
    if (!resp.ok) {
      _clearOntCtoRxSnapshotCells();
      noDataEl.innerText = String(payload.error || "No se pudo consultar Altiplano.");
      noDataEl.style.display = "";
      return;
    }
    const merged = mergeSnapshot(payload);
    _applyRecentZoom();
    if (merged.validCount > 0) {
      const med = _roundToSingleDecimal(merged.medianValue);
      const msg = "RX manual agregado: "
        + String(merged.validCount) + "/" + String(merged.totalCount)
        + " ONTs con lectura, mediana " + String(med) + " dBm, " + payload.timestamp;
      noDataEl.innerText = msg;
      _setSnapshotKpiHint(msg);
    } else {
      const msg = "RX manual recibido sin lecturas (rama posiblemente caída o sin respuesta Altiplano).";
      noDataEl.innerText = msg;
      _setSnapshotKpiHint("Snapshot RX sin lecturas válidas (" + payload.timestamp + ")");
    }
    noDataEl.style.display = "";
    setTimeout(function () {
      if (powerChart) {
        noDataEl.style.display = "none";
      }
    }, 4500);
  } catch (_err) {
    _clearOntCtoRxSnapshotCells();
    noDataEl.innerText = "Error al consultar Altiplano.";
    noDataEl.style.display = "";
  } finally {
    _setConsultarRxLoading(btn, false);
  }
}

document.getElementById("ratc-input").addEventListener("keypress", function (e) {
  if (e.key === "Enter") fetchData();
});

document.querySelectorAll("#range-picker [data-days]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    selectedDays = Number(btn.getAttribute("data-days")) || 30;
    document.querySelectorAll("#range-picker [data-days]").forEach(function (el) {
      el.classList.toggle("is-active", el === btn);
    });
    updateDeepLink();
    if (lastRATC) fetchData();
  });
});

document.getElementById("btn-reset-zoom").addEventListener("click", function () {
  if (powerChart) powerChart.resetZoom();
});

document.getElementById("btn-export").addEventListener("click", function () {
  if (!lastRATC) return;
  const url = "/dashboard/potencias-historico/export.csv?ratc="
    + encodeURIComponent(lastRATC)
    + "&days=" + encodeURIComponent(String(selectedDays));
  window.location.href = url;
});

document.getElementById("btn-consultar-ahora").addEventListener("click", function () {
  consultarAhora();
});

document.getElementById("btn-toggle-legend").addEventListener("click", function () {
  legendVisible = !legendVisible;
  const legendWrap = document.getElementById("legend-wrap");
  _historicoPanelVisible(legendWrap, legendVisible);
  this.innerText = legendVisible ? "Ocultar leyenda" : "Mostrar leyenda";
});

document.getElementById("btn-show-all").addEventListener("click", function () {
  if (!powerChart) return;
  powerChart.data.datasets.forEach(function (ds, idx) {
    if (_isOntDatasetLabel(ds.label)) powerChart.setDatasetVisibility(idx, true);
  });
  powerChart.update();
  _syncLegendChecks();
});

document.getElementById("btn-hide-all").addEventListener("click", function () {
  if (!powerChart) return;
  powerChart.data.datasets.forEach(function (ds, idx) {
    if (_isOntDatasetLabel(ds.label)) powerChart.setDatasetVisibility(idx, false);
  });
  powerChart.update();
  _syncLegendChecks();
});

(function bindHistoricoOntAccessIdCopy() {
  var tbody = document.getElementById("ont-cto-summary-tbody");
  if (!tbody) return;
  tbody.addEventListener("click", function (e) {
    var cell = e.target.closest("[data-access-id]");
    if (!cell || !tbody.contains(cell)) return;
    e.preventDefault();
    _copyHistoricoAccessId(cell.getAttribute("data-access-id"));
  });
  tbody.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var cell = e.target.closest("[data-access-id]");
    if (!cell || !tbody.contains(cell)) return;
    e.preventDefault();
    _copyHistoricoAccessId(cell.getAttribute("data-access-id"));
  });
})();

function initFromQueryString() {
  const params = new URLSearchParams(window.location.search);
  const ratc = (params.get("ratc") || "").trim();
  const days = Number(params.get("days") || 30);
  if ([1, 7, 15, 30].includes(days)) {
    selectedDays = days;
    document.querySelectorAll("#range-picker [data-days]").forEach(function (el) {
      el.classList.toggle("is-active", Number(el.getAttribute("data-days")) === days);
    });
  }
  if (ratc) {
    document.getElementById("ratc-input").value = ratc;
    lastRATC = ratc;
    fetchData();
  } else {
    updateDeepLink();
  }
}

if (window.initNocPage) {
  initNocPage({
    page: "historico-potencias",
    searchSelector: "#ratc-input",
    onClear: resetDashboard,
  });
}

const _themeObserver = new MutationObserver(function (mutations) {
  for (const m of mutations) {
    if (m.type === "attributes" && m.attributeName === "data-theme") {
      applyThemeToChart();
      break;
    }
  }
});
_themeObserver.observe(document.documentElement, { attributes: true });

initFromQueryString();