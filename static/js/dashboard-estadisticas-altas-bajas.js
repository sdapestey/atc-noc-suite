/* Estadísticas altas/bajas — día seleccionable; gráfico por mes o año */
(function () {
  let _estadisticasChart = null;
  let _estadisticasGranularity = "month";
  let _fechaSeleccionada = "";
  let _fechaPicker = null;

  const _SUMMARY = [
    { key: "hoy", title: "Día seleccionado", heroAlta: true },
    { key: "ayer", title: "Día anterior" },
    { key: "ultimos_7_dias", title: "Últimos 7 días" },
    { key: "mes_actual", title: "Mes en curso", heroAlta: true },
    { key: "anio_actual", title: "Año en curso", heroBaja: true },
  ];

  const CD = window.CalidadDashboard || {};
  const _fmtCount = CD.fmtCount || ((n) => String(n));
  const _esc = CD.esc || ((v) => String(v || ""));
  const _opSlug = CD.opSlug || ((l) => String(l || ""));
  const _renderBigRow = CD.renderBigRow || ((html, cols) => `<div class="calidad-big-row calidad-big-row--${cols}">${html}</div>`);
  const _loading = CD.renderLoadingStatus || ((msg) => `<p class="muted">${_esc(msg)}</p>`);

  function _granularityLabel() {
    return _estadisticasGranularity === "year" ? "Año" : "Mes";
  }

  function _formatRefDate(iso) {
    if (!iso) return "";
    const parts = String(iso).slice(0, 10).split("-");
    if (parts.length !== 3) return iso;
    const dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return dt.toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" });
  }

  function _summaryTitle(item, referenceDate) {
    if (item.key !== "hoy" || !referenceDate) {
      return item.title;
    }
    return `${item.title} (${_formatRefDate(referenceDate)})`;
  }

  function _referenceMeta(data) {
    const ref = data.reference_date || data.latest_snapshot;
    if (!ref) return "";
    const refFmt = _formatRefDate(ref);
    const auto = data.reference_date_auto;
    if (_fechaSeleccionada && auto && _fechaSeleccionada !== auto) {
      return ` · Consulta al <strong>${_esc(refFmt)}</strong>`;
    }
    if (data.reference_date_is_today === false) {
      return ` · Último día con datos en Postgres: <strong>${_esc(refFmt)}</strong>`;
    }
    return ` · Datos al <strong>${_esc(refFmt)}</strong>`;
  }

  function _fechaInputValue() {
    if (_fechaPicker?.input) {
      return _fechaPicker.input.value || "";
    }
    return document.getElementById("estadisticas-fecha")?.value || "";
  }

  function _initFechaPicker() {
    const input = document.getElementById("estadisticas-fecha");
    const NFP = window.NocEstadisticasFlatpickr;
    if (!input || !NFP || _fechaPicker) {
      return;
    }
    _fechaPicker = NFP.create(input, {
      onChange(_selected, dateStr) {
        _fechaSeleccionada = dateStr || "";
        window.loadCalidadEstadisticas();
      },
    });
  }

  function _syncFechaPicker(data) {
    if (!_fechaPicker) {
      _initFechaPicker();
    }
    if (!_fechaPicker) {
      return;
    }
    const min = data.data_date_min;
    if (min) {
      _fechaPicker.set("minDate", min);
    }
    _fechaPicker.set("maxDate", window.NocEstadisticasFlatpickr?.maxDateToday() || new Date());
    const input = document.getElementById("estadisticas-fecha");
    if (input) {
      input.max = data.data_date_max || "";
    }
    const ref = data.reference_date || "";
    const next = _fechaSeleccionada || ref;
    if (next && _fechaPicker.input.value !== next) {
      _fechaPicker.setDate(next, false);
    }
    window.NocEstadisticasFlatpickr?.syncMonthYear(_fechaPicker);
  }

  /** Misma estructura que Resumen; color por tipo alta/baja + acento por operador */
  function _bigCard(title, value, foot, kind, emphasize, isOp) {
    const kindCls =
      kind === "alta" ? " calidad-big-card--stat-alta" : " calidad-big-card--stat-baja";
    const heroCls = emphasize ? " calidad-big-card--stat-hero" : "";
    const opCls = isOp ? " calidad-big-card--op" : "";
    const opSlugCls = isOp && foot ? ` calidad-big-card--op-${_opSlug(foot)}` : "";
    const kpiBody = `
        <span class="calidad-big-card__value mono">${_esc(_fmtCount(value))}</span>
        ${foot ? `<span class="calidad-big-card__foot">${_esc(foot)}</span>` : ""}`;
    return `
      <div class="calidad-big-card${kindCls}${heroCls}${opCls}${opSlugCls}">
        <span class="calidad-big-card__title">${_esc(title)}</span>
        <div class="calidad-big-card__kpi">${kpiBody}</div>
      </div>`;
  }

  function _renderChart(canvas, data) {
    if (!canvas || typeof Chart === "undefined") return;
    const points = Array.isArray(data.series) ? data.series : [];
    if (_estadisticasChart) {
      _estadisticasChart.destroy();
      _estadisticasChart = null;
    }
    if (!points.length) return;
    const labels = points.map((p) => p.periodo || p.fecha);
    _estadisticasChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Altas",
            data: points.map((p) => Number(p.altas || 0)),
            backgroundColor: "rgba(63, 185, 80, 0.55)",
            borderColor: "rgba(63, 185, 80, 0.95)",
            borderWidth: 1,
          },
          {
            label: "Bajas",
            data: points.map((p) => Number(p.bajas || 0)),
            backgroundColor: "rgba(248, 81, 73, 0.5)",
            borderColor: "rgba(248, 81, 73, 0.95)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: { labels: { color: "#9aa7b2" } } },
        scales: {
          x: { ticks: { color: "#9aa7b2", maxTicksLimit: 14 } },
          y: { beginAtZero: true, ticks: { color: "#9aa7b2", precision: 0 } },
        },
      },
    });
  }

  window.renderCalidadEstadisticas = function (data) {
    const root = document.getElementById("calidad-estadisticas-root");
    if (!root || !data) return;

    _syncFechaPicker(data);

    const cards = data.cards || {};
    const byOperator = Array.isArray(data.by_operator) ? data.by_operator : [];
    const refDate = data.reference_date || data.latest_snapshot || null;
    const periodLabel = refDate
      ? `Día seleccionado (${_formatRefDate(refDate)})`
      : "Día seleccionado";

    const altasTotales = _SUMMARY.map((s) => {
      const c = cards[s.key] || {};
      return _bigCard(_summaryTitle(s, refDate), c.altas, "Altas", "alta", !!s.heroAlta, false);
    }).join("");

    const bajasTotales = _SUMMARY.map((s) => {
      const c = cards[s.key] || {};
      const title = s.key === "hoy" ? _summaryTitle(s, refDate) : s.title;
      return _bigCard(title, c.bajas, "Bajas", "baja", !!s.heroBaja, false);
    }).join("");

    const altasOps = byOperator
      .map((op) => {
        const c = (op.cards && op.cards.hoy) || { altas: 0, bajas: 0 };
        return _bigCard(`Altas ${op.label}`, c.altas, op.label, "alta", false, true);
      })
      .join("");

    const bajasOps = byOperator
      .map((op) => {
        const c = (op.cards && op.cards.hoy) || { altas: 0, bajas: 0 };
        return _bigCard(`Bajas ${op.label}`, c.bajas, op.label, "baja", false, true);
      })
      .join("");

    const opsEmpty = '<p class="muted">Sin datos por operador.</p>';

    root.classList.add("calidad-estadisticas-root--loaded");
    root.innerHTML = `
      <div class="calidad-resumen-shell">
        <p class="calidad-estadisticas-meta muted">
          Gráfico por <strong>${_esc(_granularityLabel())}</strong>${_referenceMeta(data)}
        </p>
        <section class="calidad-superset-block">
          <h2 class="calidad-superset-title" id="est-altas-totales">Totales — Altas</h2>
          ${_renderBigRow(altasTotales, 5)}
        </section>
        <section class="calidad-superset-block calidad-superset-block--alt">
          <h2 class="calidad-superset-title" id="est-bajas-totales">Totales — Bajas</h2>
          ${_renderBigRow(bajasTotales, 5)}
        </section>
        <section class="calidad-superset-block calidad-superset-block--alt">
          <h2 class="calidad-superset-title" id="est-altas-ops">Altas · ${_esc(periodLabel)}</h2>
          ${altasOps ? _renderBigRow(altasOps, 3) : opsEmpty}
        </section>
        <section class="calidad-superset-block calidad-superset-block--cm">
          <h2 class="calidad-superset-title" id="est-bajas-ops">Bajas · ${_esc(periodLabel)}</h2>
          ${bajasOps ? _renderBigRow(bajasOps, 3) : opsEmpty}
        </section>
        <section class="calidad-superset-block">
          <h2 class="calidad-superset-title">Evolución (${_esc(_granularityLabel())})</h2>
          <div class="calidad-chart-stage calidad-chart-stage--historico-resumen">
            <canvas id="calidad-estadisticas-chart" aria-label="Gráfico de altas y bajas"></canvas>
          </div>
          <p id="calidad-estadisticas-empty" class="muted calidad-estadisticas-empty" hidden>Sin datos en el rango seleccionado.</p>
        </section>
      </div>`;

    const series = data.series || [];
    const empty = document.getElementById("calidad-estadisticas-empty");
    const canvas = document.getElementById("calidad-estadisticas-chart");
    if (!series.length) {
      if (empty) empty.hidden = false;
    } else {
      if (empty) empty.hidden = true;
      _renderChart(canvas, data);
    }
  };

  window.loadCalidadEstadisticas = async function () {
    const root = document.getElementById("calidad-estadisticas-root");
    if (!root) return;
    root.innerHTML = _loading("Cargando estadísticas…");
    root.classList.remove("calidad-estadisticas-root--loaded");
    try {
      const params = new URLSearchParams({ granularity: _estadisticasGranularity });
      if (_fechaSeleccionada) {
        params.set("fecha", _fechaSeleccionada);
      }
      const r = await fetch(`${CD.api.altasBajas}?${params}`);
      if (!r.ok) throw new Error("estadisticas");
      window.renderCalidadEstadisticas(await r.json());
    } catch (_e) {
      root.innerHTML =
        '<p class="muted calidad-resumen-loading">No se pudieron cargar las estadísticas.</p>';
      if (typeof qualityToast === "function") qualityToast("No se pudieron cargar estadísticas");
    }
  };

  window._setEstadisticasGranularity = function (g) {
    _estadisticasGranularity = g === "year" ? "year" : "month";
  };

  document.addEventListener("DOMContentLoaded", () => {
    _initFechaPicker();

    document.getElementById("btn-refresh-estadisticas")?.addEventListener("click", () => {
      _fechaSeleccionada = _fechaInputValue();
      window.loadCalidadEstadisticas();
    });

    document.querySelectorAll("#estadisticas-granularity [data-granularity]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#estadisticas-granularity [data-granularity]").forEach((b) => {
          b.classList.toggle("is-active", b === btn);
        });
        window._setEstadisticasGranularity(btn.getAttribute("data-granularity"));
        window.loadCalidadEstadisticas();
      });
    });
  });
})();
