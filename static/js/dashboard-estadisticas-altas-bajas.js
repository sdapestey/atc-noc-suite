/* Estadísticas altas/bajas — mismas tarjetas que Resumen general */
(function () {
  let _estadisticasChart = null;
  let _estadisticasGranularity = "day";

  const _PERIOD = {
    day: { key: "hoy", label: "Hoy" },
    month: { key: "mes_actual", label: "Mes en curso" },
    year: { key: "anio_actual", label: "Año en curso" },
  };

  const _SUMMARY = [
    { key: "hoy", title: "Hoy", heroAlta: true },
    { key: "ayer", title: "Ayer" },
    { key: "ultimos_7_dias", title: "Últimos 7 días" },
    { key: "mes_actual", title: "Mes en curso", heroAlta: true },
    { key: "anio_actual", title: "Año en curso", heroBaja: true },
  ];

  const CD = window.CalidadDashboard || {};
  const _fmtCount = CD.fmtCount || ((n) => String(n));
  const _esc = CD.esc || ((v) => String(v || ""));
  const _opSlug = CD.opSlug || ((l) => String(l || ""));
  const _renderBigRow = CD.renderBigRow || ((html, cols) => `<div class="calidad-big-row calidad-big-row--${cols}">${html}</div>`);

  function _granularityLabel() {
    if (_estadisticasGranularity === "month") return "Mes";
    if (_estadisticasGranularity === "year") return "Año";
    return "Día";
  }

  function _todayIsoLocal() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function _formatRefDate(iso) {
    if (!iso) return "";
    const parts = String(iso).slice(0, 10).split("-");
    if (parts.length !== 3) return iso;
    const dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    return dt.toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" });
  }

  function _summaryTitle(item, referenceDate) {
    if (item.key !== "hoy" || !referenceDate || referenceDate === _todayIsoLocal()) {
      return item.title;
    }
    return `${item.title} (${_formatRefDate(referenceDate)})`;
  }

  function _referenceMeta(data) {
    const ref = data.reference_date || data.latest_snapshot;
    if (!ref) return "";
    const lag = data.reference_date_is_today === false;
    const refFmt = _formatRefDate(ref);
    if (lag) {
      return ` · Datos al <strong>${_esc(refFmt)}</strong> (último backup; el calendario de hoy se actualiza con el próximo backup)`;
    }
    return ` · Datos al <strong>${_esc(refFmt)}</strong>`;
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
    const labels =
      _estadisticasGranularity === "day"
        ? points.map((p) => p.fecha || p.periodo)
        : points.map((p) => p.periodo || p.fecha);
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

    const cards = data.cards || {};
    const byOperator = Array.isArray(data.by_operator) ? data.by_operator : [];
    const period = _PERIOD[_estadisticasGranularity] || _PERIOD.day;

    const refDate = data.reference_date || data.latest_snapshot || null;
    const periodLabel =
      refDate && refDate !== _todayIsoLocal()
        ? `${_PERIOD[_estadisticasGranularity]?.label || "Hoy"} (${_formatRefDate(refDate)})`
        : _PERIOD[_estadisticasGranularity]?.label || "Hoy";

    const altasTotales = _SUMMARY.map((s) => {
      const c = cards[s.key] || {};
      return _bigCard(_summaryTitle(s, refDate), c.altas, "Altas", "alta", !!s.heroAlta, false);
    }).join("");

    const bajasTotales = _SUMMARY.map((s) => {
      const c = cards[s.key] || {};
      return _bigCard(s.title, c.bajas, "Bajas", "baja", !!s.heroBaja, false);
    }).join("");

    const altasOps = byOperator
      .map((op) => {
        const c = (op.cards && op.cards[period.key]) || { altas: 0, bajas: 0 };
        return _bigCard(`Altas ${op.label}`, c.altas, op.label, "alta", false, true);
      })
      .join("");

    const bajasOps = byOperator
      .map((op) => {
        const c = (op.cards && op.cards[period.key]) || { altas: 0, bajas: 0 };
        return _bigCard(`Bajas ${op.label}`, c.bajas, op.label, "baja", false, true);
      })
      .join("");

    const opsEmpty = '<p class="muted">Sin datos por operador.</p>';

    root.classList.add("calidad-estadisticas-root--loaded");
    root.innerHTML = `
      <div class="calidad-resumen-shell">
        <p class="calidad-estadisticas-meta muted">
          Gráfico en vista <strong>${_esc(_granularityLabel())}</strong>${_referenceMeta(data)}
          ${data.sftp_backup_latest ? ` · Backup SFTP ${_esc(data.sftp_backup_latest)}` : ""}
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
    root.innerHTML = '<p class="muted calidad-resumen-loading">Cargando estadísticas…</p>';
    root.classList.remove("calidad-estadisticas-root--loaded");
    try {
      const params = new URLSearchParams({ granularity: _estadisticasGranularity });
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
    _estadisticasGranularity = g === "month" || g === "year" ? g : "day";
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-refresh-estadisticas")?.addEventListener("click", window.loadCalidadEstadisticas);
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
