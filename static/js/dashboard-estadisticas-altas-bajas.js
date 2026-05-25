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

  function _fpMonthNames(fp) {
    const loc = fp.l10n || (flatpickr.l10ns && flatpickr.l10ns.es) || {};
    return (loc.months && loc.months.longhand) || flatpickr.l10ns.default.months.longhand;
  }

  function _fpTodayParts() {
    const t = new Date();
    return { y: t.getFullYear(), m: t.getMonth() };
  }

  function _fpMaxDate() {
    const t = new Date();
    t.setHours(23, 59, 59, 999);
    return t;
  }

  function _fpIsMonthDisabled(monthIdx, year) {
    const { y, m } = _fpTodayParts();
    if (year > y) return true;
    if (year === y && monthIdx > m) return true;
    return false;
  }

  function _fpIsYearDisabled(year) {
    return year > _fpTodayParts().y;
  }

  function _fpYearBounds(fp) {
    let minY = fp.currentYear - 8;
    let maxY = _fpTodayParts().y;
    const minD = fp.config.minDate;
    const maxD = fp.config.maxDate;
    if (minD instanceof Date) {
      minY = minD.getFullYear();
    }
    if (maxD instanceof Date) {
      maxY = Math.min(maxD.getFullYear(), maxY);
    }
    return { minY, maxY };
  }

  function _applyFpMonthDisabled(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    cal.querySelectorAll(".noc-fp-month-grid .noc-fp-picker-opt").forEach((btn) => {
      const idx = Number(btn.dataset.month);
      const disabled = _fpIsMonthDisabled(idx, fp.currentYear);
      btn.disabled = disabled;
      btn.classList.toggle("is-disabled", disabled);
      btn.setAttribute("aria-disabled", disabled ? "true" : "false");
    });
  }

  function _closeFpPickerPanel(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    const panel = cal.querySelector(".noc-fp-picker-panel");
    if (panel) panel.hidden = true;
    cal.querySelectorAll(".noc-fp-chip.is-open").forEach((el) => el.classList.remove("is-open"));
  }

  function _highlightFpMonthYear(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    cal.querySelectorAll(".noc-fp-month-grid .noc-fp-picker-opt").forEach((btn) => {
      btn.classList.toggle("is-active", Number(btn.dataset.month) === fp.currentMonth);
    });
    cal.querySelectorAll(".noc-fp-year-grid .noc-fp-picker-opt").forEach((btn) => {
      const y = Number(btn.textContent);
      btn.classList.toggle("is-active", y === fp.currentYear);
      const disabled = _fpIsYearDisabled(y);
      btn.disabled = disabled;
      btn.classList.toggle("is-disabled", disabled);
    });
    _applyFpMonthDisabled(fp);
  }

  function _syncFpMonthYearTriggers(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;
    const monthBtn = cal.querySelector(".noc-fp-month-trigger");
    const yearBtn = cal.querySelector(".noc-fp-year-trigger");
    if (!monthBtn || !yearBtn) return;
    const months = _fpMonthNames(fp);
    monthBtn.textContent = months[fp.currentMonth] || "";
    yearBtn.textContent = String(fp.currentYear);
    _highlightFpMonthYear(fp);
  }

  function _renderFpYearGrid(fp, yearGrid) {
    yearGrid.innerHTML = "";
    const { minY, maxY } = _fpYearBounds(fp);
    for (let y = maxY; y >= minY; y -= 1) {
      if (_fpIsYearDisabled(y)) continue;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "noc-fp-picker-opt";
      btn.textContent = String(y);
      btn.setAttribute("role", "option");
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        if (_fpIsYearDisabled(y)) return;
        fp.changeYear(y);
        _closeFpPickerPanel(fp);
        _syncFpMonthYearTriggers(fp);
      });
      yearGrid.appendChild(btn);
    }
    _highlightFpMonthYear(fp);
  }

  function _enhanceFpMonthYear(fp) {
    const cal = fp.calendarContainer;
    if (!cal) return;

    if (cal.dataset.nocFpEnhanced !== "1") {
      cal.dataset.nocFpEnhanced = "1";
      const currentMonth = cal.querySelector(".flatpickr-current-month");
      if (!currentMonth) return;

      currentMonth
        .querySelectorAll(".flatpickr-monthDropdown-months, .numInput.cur-year, .cur-month")
        .forEach((el) => {
          el.style.display = "none";
          el.setAttribute("aria-hidden", "true");
        });

      const row = document.createElement("div");
      row.className = "noc-fp-current-row";

      const monthBtn = document.createElement("button");
      monthBtn.type = "button";
      monthBtn.className = "noc-fp-chip noc-fp-month-trigger";
      monthBtn.setAttribute("aria-haspopup", "listbox");

      const yearBtn = document.createElement("button");
      yearBtn.type = "button";
      yearBtn.className = "noc-fp-chip noc-fp-year-trigger";
      yearBtn.setAttribute("aria-haspopup", "listbox");

      row.append(monthBtn, yearBtn);
      currentMonth.appendChild(row);

      const panel = document.createElement("div");
      panel.className = "noc-fp-picker-panel";
      panel.hidden = true;

      const monthGrid = document.createElement("div");
      monthGrid.className = "noc-fp-month-grid";
      monthGrid.setAttribute("role", "listbox");

      const yearGrid = document.createElement("div");
      yearGrid.className = "noc-fp-year-grid";
      yearGrid.hidden = true;
      yearGrid.setAttribute("role", "listbox");

      panel.append(monthGrid, yearGrid);
      cal.querySelector(".flatpickr-months")?.appendChild(panel);

      _fpMonthNames(fp).forEach((label, idx) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "noc-fp-picker-opt";
        btn.textContent = label;
        btn.dataset.month = String(idx);
        btn.setAttribute("role", "option");
        btn.addEventListener("click", (ev) => {
          ev.stopPropagation();
          if (_fpIsMonthDisabled(idx, fp.currentYear)) return;
          fp.changeMonth(idx, false);
          _closeFpPickerPanel(fp);
          _syncFpMonthYearTriggers(fp);
        });
        monthGrid.appendChild(btn);
      });

      monthBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const panelEl = cal.querySelector(".noc-fp-picker-panel");
        const monthEl = cal.querySelector(".noc-fp-month-grid");
        const yearEl = cal.querySelector(".noc-fp-year-grid");
        if (!panelEl || !monthEl || !yearEl) return;
        const showingMonth = !panelEl.hidden && !monthEl.hidden;
        if (showingMonth) {
          _closeFpPickerPanel(fp);
          return;
        }
        panelEl.hidden = false;
        monthEl.hidden = false;
        yearEl.hidden = true;
        monthBtn.classList.add("is-open");
        yearBtn.classList.remove("is-open");
        _highlightFpMonthYear(fp);
        _applyFpMonthDisabled(fp);
      });

      yearBtn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const panelEl = cal.querySelector(".noc-fp-picker-panel");
        const monthEl = cal.querySelector(".noc-fp-month-grid");
        const yearEl = cal.querySelector(".noc-fp-year-grid");
        if (!panelEl || !monthEl || !yearEl) return;
        const showingYear = !panelEl.hidden && !yearEl.hidden;
        if (showingYear) {
          _closeFpPickerPanel(fp);
          return;
        }
        _renderFpYearGrid(fp, yearEl);
        panelEl.hidden = false;
        monthEl.hidden = true;
        yearEl.hidden = false;
        yearBtn.classList.add("is-open");
        monthBtn.classList.remove("is-open");
      });

      cal.addEventListener("mousedown", (ev) => ev.stopPropagation());
    }

    _syncFpMonthYearTriggers(fp);
  }

  function _initFechaPicker() {
    const input = document.getElementById("estadisticas-fecha");
    if (!input || typeof flatpickr === "undefined") {
      return;
    }
    if (_fechaPicker) {
      return;
    }
    const locale =
      flatpickr.l10ns && flatpickr.l10ns.es ? flatpickr.l10ns.es : flatpickr.l10ns.default;
    _fechaPicker = flatpickr(input, {
      locale,
      dateFormat: "Y-m-d",
      altInput: true,
      altFormat: "j \\d\\e F \\d\\e Y",
      allowInput: false,
      disableMobile: true,
      clickOpens: true,
      monthSelectorType: "static",
      maxDate: _fpMaxDate(),
      onChange(_selected, dateStr) {
        _fechaSeleccionada = dateStr || "";
        window.loadCalidadEstadisticas();
      },
      onMonthChange() {
        if (_fechaPicker) {
          _syncFpMonthYearTriggers(_fechaPicker);
          _applyFpMonthDisabled(_fechaPicker);
        }
      },
      onYearChange() {
        if (_fechaPicker) {
          _syncFpMonthYearTriggers(_fechaPicker);
          _applyFpMonthDisabled(_fechaPicker);
        }
      },
      onOpen() {
        if (_fechaPicker) {
          _enhanceFpMonthYear(_fechaPicker);
          _closeFpPickerPanel(_fechaPicker);
        }
      },
      onClose() {
        if (_fechaPicker) _closeFpPickerPanel(_fechaPicker);
      },
      onReady(_selected, _str, instance) {
        instance.calendarContainer.classList.add("noc-estadisticas-cal");
        if (instance.altInput) {
          instance.altInput.classList.add("noc-estadisticas-fecha-visible");
        }
        _enhanceFpMonthYear(instance);
      },
    });
    if (_fechaPicker.calendarContainer) {
      _fechaPicker.calendarContainer.classList.add("noc-estadisticas-cal");
    }
    if (_fechaPicker.altInput) {
      _fechaPicker.altInput.classList.add("noc-estadisticas-fecha-visible");
    }
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
    _fechaPicker.set("maxDate", _fpMaxDate());
    const input = document.getElementById("estadisticas-fecha");
    if (input) {
      input.max = data.data_date_max || "";
    }
    const ref = data.reference_date || "";
    const next = _fechaSeleccionada || ref;
    if (next && _fechaPicker.input.value !== next) {
      _fechaPicker.setDate(next, false);
    }
    _syncFpMonthYearTriggers(_fechaPicker);
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
    root.innerHTML = '<p class="muted calidad-resumen-loading">Cargando estadísticas…</p>';
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
