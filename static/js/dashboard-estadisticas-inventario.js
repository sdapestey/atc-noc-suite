/* Resumen general Calidad Inventario (layout Superset) */
(function () {
  const TABLE_PAGE = 10;
  const _tableState = {};
  let _resumenHistoricoChart = null;
  let _resumenHistoricoDays = 90;

  const CD = window.CalidadDashboard || {};
  const _esc = CD.esc || ((v) => String(v || ""));
  const _fmtCount = CD.fmtCount || ((n) => String(n));
  const _opSlug = CD.opSlug || ((l) => String(l || ""));
  const _sectionTitle = CD.sectionTitle || ((t) => `<h2 class="calidad-superset-title">${t}</h2>`);
  const _renderBigRow = CD.renderBigRow || ((html, cols) => `<div class="calidad-big-row calidad-big-row--${cols}">${html}</div>`);

  function _bigCard(title, value, foot, operatorId, variant) {
    const opAttr = operatorId ? ` data-operator-id="${_esc(operatorId)}"` : "";
    const clickable = operatorId ? " calidad-big-card--clickable" : "";
    const variantCls = variant ? ` calidad-big-card--${variant}` : "";
    const slugCls = foot ? ` calidad-big-card--op-${_opSlug(foot)}` : "";
    const tag = operatorId || (variant && variant.startsWith("hero")) ? "button" : "div";
    const typeAttr = tag === "button" ? ' type="button"' : "";
    const el = tag === "button" ? "button" : "div";
    const kpiBody = `
        <span class="calidad-big-card__value mono">${_esc(_fmtCount(value))}</span>
        ${foot ? `<span class="calidad-big-card__foot">${_esc(foot)}</span>` : ""}`;
    return `
      <${el} class="calidad-big-card${variantCls}${slugCls}${clickable}"${typeAttr}${opAttr}>
        <span class="calidad-big-card__title">${_esc(title)}</span>
        <div class="calidad-big-card__kpi">${kpiBody}</div>
      </${el}>`;
  }

  function _widgetShell(title, bodyHtml, wide) {
    return `
      <article class="calidad-widget${wide ? " calidad-widget--wide" : ""}">
        <header class="calidad-widget__head">
          <h3 class="calidad-widget__title">${_esc(title)}</h3>
        </header>
        <div class="calidad-widget__body">${bodyHtml}</div>
      </article>`;
  }

  function _bindGoReglas(root) {
    root.querySelectorAll("[data-operator-id]").forEach((el) => {
      el.addEventListener("click", () => {
        const op = el.getAttribute("data-operator-id");
        const input = document.getElementById("f-operador");
        if (input && op) input.value = op;
        if (typeof window.switchTab === "function") window.switchTab("reglas");
        if (typeof window.resetCalidadHallazgosPage === "function") window.resetCalidadHallazgosPage();
        if (typeof window.refreshCalidadDashboard === "function") window.refreshCalidadDashboard();
      });
    });
  }

  function _renderActivosBlocks(data) {
    const t = data.totals || {};
    const ops = data.operators || [];
    const cmTotal = t.connect_master_in_service ?? t.bajada_inventario_in_service ?? 0;
    const altCards = ops
      .map((o) => _bigCard(`Activos ${o.label}`, o.altiplano, o.label, o.id, "op"))
      .join("");
    const cmCards = ops
      .map((o) =>
        _bigCard(`Activos ${o.label}`, o.connect_master ?? o.in_service, o.label, o.id, "op")
      )
      .join("");

    return `
      <section class="calidad-superset-block">
        ${_sectionTitle("Total activos", "sup-total")}
        ${_renderBigRow(
          _bigCard("Total Activos en Connect Master", cmTotal, "", null, "hero-cm") +
            _bigCard("Activos Totales Altiplano", t.altiplano_activos, "", null, "hero-alt"),
          2
        )}
      </section>
      <section class="calidad-superset-block calidad-superset-block--alt">
        ${_sectionTitle("Activos — Altiplano", "sup-alt")}
        ${_renderBigRow(altCards, 3)}
      </section>
      <section class="calidad-superset-block calidad-superset-block--cm">
        ${_sectionTitle("Activos — Connect Master", "sup-cm")}
        ${_renderBigRow(cmCards, 3)}
      </section>`;
  }

  function _renderComparativaTable(rows) {
    const body = (rows || [])
      .map(
        (r) => `
      <tr>
        <td>${_esc(r.vno)}</td>
        <td class="num">${_fmtCount(r.altiplano)}</td>
        <td class="num">${_fmtCount(r.connect_master)}</td>
        <td class="num${r.diferencia < 0 ? " num--neg" : ""}">${_fmtCount(r.diferencia)}</td>
      </tr>`
      )
      .join("");
    return `
      <table class="calidad-superset-table">
        <thead>
          <tr><th>vno</th><th>ALTIPLANO</th><th>CONNECT MASTER</th><th>DIFERENCIA</th></tr>
        </thead>
        <tbody>${body || '<tr><td colspan="4">Sin datos</td></tr>'}</tbody>
      </table>`;
  }

  function _renderActivosCmRow(ops) {
    const headers = (ops || []).map((o) => `<th>${_esc(o.label)}</th>`).join("");
    const vals = (ops || [])
      .map((o) => `<td class="num">${_fmtCount(o.connect_master ?? o.in_service)}</td>`)
      .join("");
    return `
      <table class="calidad-superset-table calidad-superset-table--horizontal">
        <thead><tr>${headers}</tr></thead>
        <tbody><tr>${vals}</tr></tbody>
      </table>`;
  }

  function _tableWidgetHtml(widgetId, title, columns) {
    const st = _tableState[widgetId] || { offset: 0, q: "", limit: TABLE_PAGE };
    return _widgetShell(
      title,
      `
      <div class="calidad-table-widget" data-widget-id="${widgetId}">
        <div class="calidad-table-widget__toolbar">
          <label class="calidad-table-widget__pagesize">
            Show
            <select data-role="limit" aria-label="Filas por página">
              <option value="10" ${st.limit === 10 ? "selected" : ""}>10</option>
              <option value="25" ${st.limit === 25 ? "selected" : ""}>25</option>
              <option value="50" ${st.limit === 50 ? "selected" : ""}>50</option>
            </select>
            entries
          </label>
          <label class="calidad-table-widget__search">
            Search:
            <input type="search" data-role="q" placeholder="Buscar…" value="${_esc(st.q)}" />
          </label>
          <span class="calidad-table-widget__meta" data-role="meta">—</span>
        </div>
        <div class="table-wrap calidad-table-widget__table">
          <table>
            <thead><tr>${columns.map((c) => `<th>${_esc(c)}</th>`).join("")}</tr></thead>
            <tbody data-role="tbody"><tr><td colspan="${columns.length}">Cargando…</td></tr></tbody>
          </table>
        </div>
        <div class="calidad-table-widget__pager" data-role="pager"></div>
      </div>`
    );
  }

  async function _fetchTabla(tipo, widgetId) {
    const st = _tableState[widgetId] || { offset: 0, q: "", limit: TABLE_PAGE };
    const params = new URLSearchParams({
      tipo,
      limit: String(st.limit),
      offset: String(st.offset),
    });
    if (st.q) params.set("q", st.q);
    const r = await fetch(`${CD.api.inventarioTabla}?${params}`);
    if (!r.ok) throw new Error("tabla");
    return r.json();
  }

  function _renderTablaWidget(widgetId, payload) {
    const wrap = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (!wrap || !payload) return;
    const cols = payload.columns || [];
    const tbody = wrap.querySelector('[data-role="tbody"]');
    const meta = wrap.querySelector('[data-role="meta"]');
    const pager = wrap.querySelector('[data-role="pager"]');
    const rows = payload.rows || [];
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="${cols.length}">Sin registros</td></tr>`;
    } else {
      tbody.innerHTML = rows
        .map((row) => {
          const cells = cols.map((c) => `<td class="mono">${_esc(row[c])}</td>`).join("");
          return `<tr>${cells}</tr>`;
        })
        .join("");
    }
    const total = payload.total_count || 0;
    meta.textContent = `${total} records…`;
    const st = _tableState[widgetId];
    const page = Math.floor(st.offset / st.limit) + 1;
    const pages = Math.max(1, Math.ceil(total / st.limit));
    pager.innerHTML = `
      <button type="button" class="btn btn-ghost btn-sm" data-pager="prev" ${st.offset <= 0 ? "disabled" : ""}>‹</button>
      <span>Pág. ${page} / ${pages}</span>
      <button type="button" class="btn btn-ghost btn-sm" data-pager="next" ${st.offset + st.limit >= total ? "disabled" : ""}>›</button>`;
  }

  function _setTablaWidgetError(widgetId, message) {
    const wrap = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (!wrap) return;
    const tbody = wrap.querySelector('[data-role="tbody"]');
    const cols = wrap.querySelectorAll("thead th").length || 2;
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="${cols}">${_esc(message)}</td></tr>`;
    }
    const meta = wrap.querySelector('[data-role="meta"]');
    if (meta) meta.textContent = "—";
  }

  async function _loadTablaWidget(widgetId, tipo) {
    try {
      const data = await _fetchTabla(tipo, widgetId);
      _renderTablaWidget(widgetId, data);
    } catch (_e) {
      _setTablaWidgetError(widgetId, "No se pudo cargar la tabla");
      qualityToast("No se pudo cargar tabla");
    }
  }

  function _bindTablaWidget(widgetId, tipo) {
    const wrap = document.querySelector(`[data-widget-id="${widgetId}"]`);
    if (!wrap) return;
    if (!_tableState[widgetId]) _tableState[widgetId] = { offset: 0, q: "", limit: TABLE_PAGE };

    let debounce;
    wrap.querySelector('[data-role="q"]')?.addEventListener("input", (e) => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        _tableState[widgetId].q = e.target.value.trim();
        _tableState[widgetId].offset = 0;
        _loadTablaWidget(widgetId, tipo);
      }, 350);
    });
    wrap.querySelector('[data-role="limit"]')?.addEventListener("change", (e) => {
      _tableState[widgetId].limit = parseInt(e.target.value, 10) || 10;
      _tableState[widgetId].offset = 0;
      _loadTablaWidget(widgetId, tipo);
    });
    wrap.querySelector('[data-role="pager"]')?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-pager]");
      if (!btn) return;
      const st = _tableState[widgetId];
      if (btn.getAttribute("data-pager") === "prev") st.offset = Math.max(0, st.offset - st.limit);
      else st.offset += st.limit;
      _loadTablaWidget(widgetId, tipo);
    });
    _loadTablaWidget(widgetId, tipo);
  }

  function _renderHistoricoChart(canvas, data) {
    if (!canvas || typeof Chart === "undefined") return;
    const series = data?.series || [];
    if (_resumenHistoricoChart) {
      _resumenHistoricoChart.destroy();
      _resumenHistoricoChart = null;
    }
    if (!series.length) return;
    _resumenHistoricoChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: series.map((p) => p.fecha),
        datasets: [
          {
            label: "CM no Nokia",
            data: series.map((p) => p.cm_no_nokia),
            borderColor: "rgba(88, 166, 255, 0.95)",
            backgroundColor: "rgba(88, 166, 255, 0.25)",
            fill: true,
            tension: 0.25,
          },
          {
            label: "Nokia no CM",
            data: series.map((p) => p.nokia_no_cm),
            borderColor: "rgba(57, 197, 207, 0.95)",
            backgroundColor: "rgba(57, 197, 207, 0.2)",
            fill: true,
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#9aa7b2" } },
          tooltip: {
            callbacks: {
              footer(items) {
                const sum = items.reduce((a, i) => a + (i.parsed.y || 0), 0);
                return `Total: ${_fmtCount(sum)}`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { color: "#9aa7b2", maxTicksLimit: 14 } },
          y: { beginAtZero: true, ticks: { color: "#9aa7b2" } },
        },
      },
    });
  }

  window.renderCalidadResumenGeneral = function (data) {
    const root = document.getElementById("calidad-resumen-root");
    if (!root || !data) return;

    const ops = data.operators || [];
    const comparativa = data.comparativa_operadores || [];
    const totalRotos = data.total_casos_rotos ?? 0;

    const reservasCards = ops
      .map((o) => _bigCard(`Reservas ${o.label}`, o.reserved, o.label, o.id, "op"))
      .join("");

    root.classList.add("calidad-resumen-root--loaded");
    root.innerHTML = `
      <div class="calidad-resumen-shell">
        ${_renderActivosBlocks(data)}
        <section class="calidad-superset-block">
          <div class="calidad-widget-grid calidad-widget-grid--2">
            ${_widgetShell("Resumen de Inconsistencia", _renderComparativaTable(comparativa))}
            ${_widgetShell("ACTIVOS CM", _renderActivosCmRow(ops))}
          </div>
        </section>
        <section class="calidad-superset-block">
          ${_sectionTitle("Inconsistencia", "sup-incons")}
          ${_renderBigRow(_bigCard("Total ID con inconsistencia", totalRotos, "Inconsistencia", null, "hero-incons"), 1)}
        </section>
        <section class="calidad-superset-block">
          <div class="calidad-widget-grid calidad-widget-grid--2">
            ${_tableWidgetHtml("w-dtv", "DTV - AIDs sin serial number", [
              "access_id",
              "object_name",
              "vno",
              "serial_number",
            ])}
            ${_tableWidgetHtml("w-aids", "AIDs con inconsistencia de datos en Inventario", [
              "operatorid",
              "access_id",
              "reserved_date",
              "provided_date",
              "nombre_red_olt",
              "marca_olt",
              "modelo_olt",
              "rack_shelf_slot_port",
              "observaciones",
            ])}
          </div>
        </section>
        <section class="calidad-superset-block">
          ${_sectionTitle("Reservas en Connect Master", "sup-reservas")}
          ${_renderBigRow(reservasCards, 3)}
        </section>
        <section class="calidad-superset-block">
          <div class="calidad-widget-grid calidad-widget-grid--2">
            ${_tableWidgetHtml("w-nfc-sin", "FAT SIN TAG_NFC", ["location_description", "nfc_tag_id"])}
            ${_tableWidgetHtml("w-nfc-dup", "FAT con TAG_NFC Duplicados", [
              "location_description",
              "nfc_tag_id",
            ])}
          </div>
        </section>
        <section class="calidad-superset-block">
          ${_sectionTitle("Histórico diferencias entre bases", "sup-hist")}
          ${_widgetShell(
            "",
            '<div class="calidad-chart-stage calidad-chart-stage--historico-resumen"><canvas id="calidad-resumen-historico-chart"></canvas></div>'
          )}
        </section>
      </div>
    `;

    _bindGoReglas(root);
    _bindTablaWidget("w-dtv", "dtv_sin_serial");
    _bindTablaWidget("w-aids", "aids_inconsistencia");
    _bindTablaWidget("w-nfc-sin", "fat_sin_nfc");
    _bindTablaWidget("w-nfc-dup", "fat_nfc_duplicados");
    _renderHistoricoChart(document.getElementById("calidad-resumen-historico-chart"), data.historico);
  };

  window.loadCalidadResumenGeneral = async function () {
    const root = document.getElementById("calidad-resumen-root");
    if (!root) return;
    try {
      const r = await fetch(`${CD.api.inventario}?days=${_resumenHistoricoDays}`);
      if (!r.ok) throw new Error("resumen");
      const data = await r.json();
      window.renderCalidadResumenGeneral(data);
    } catch (_e) {
      qualityToast("No se pudo cargar el resumen");
    }
  };

  window._setResumenHistoricoDays = function (days) {
    _resumenHistoricoDays = days;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-refresh-resumen")?.addEventListener("click", window.loadCalidadResumenGeneral);
    document.querySelectorAll("#resumen-historico-range [data-days]").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll("#resumen-historico-range [data-days]").forEach((b) => {
          b.classList.toggle("is-active", b === btn);
        });
        window._setResumenHistoricoDays(parseInt(btn.getAttribute("data-days"), 10) || 90);
        window.loadCalidadResumenGeneral();
      });
    });
  });
})();
