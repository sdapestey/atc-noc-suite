/* Estadísticas Altiplano INP — tarjetas por estado RN / alineación */
(function () {
  const CD = window.CalidadDashboard || {};
  const _fmtCount = CD.fmtCount || ((n) => String(n));
  const _esc = CD.esc || ((v) => String(v || ""));
  const _renderBigRow = CD.renderBigRow || ((html, cols) => `<div class="calidad-big-row calidad-big-row--${cols}">${html}</div>`);
  const _loading = CD.renderLoadingStatus || ((msg) => `<p class="muted">${_esc(msg)}</p>`);

  const _THEME_CLASS = {
    rn: " calidad-big-card--hero-cm",
    al: " calidad-big-card--hero-alt",
    aligned: " calidad-big-card--stat-alta",
    misaligned: " calidad-big-card--stat-baja",
  };

  function _formatGeneratedAt(iso) {
    if (!iso) return "";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toLocaleString("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function _bigCard(card) {
    const theme = card.theme || "rn";
    const themeCls = _THEME_CLASS[theme] || _THEME_CLASS.rn;
    const value = card.ok && card.count != null ? _fmtCount(card.count) : "—";
    const title = card.error ? `${card.title} (${card.error})` : card.title;
    const foot = card.foot || "intents";
    return `
      <div class="calidad-big-card${themeCls}" title="${_esc(card.error || card.title)}">
        <span class="calidad-big-card__title">${_esc(card.title)}</span>
        <div class="calidad-big-card__kpi">
          <span class="calidad-big-card__value mono">${_esc(value)}</span>
          <span class="calidad-big-card__foot">${_esc(foot)}</span>
        </div>
      </div>`;
  }

  function _colsForSection(section) {
    const n = (section.cards || []).length;
    if (n <= 2) return 2;
    if (n <= 3) return 3;
    if (n <= 4) return 4;
    return 5;
  }

  window.renderCalidadEstadisticasAltiplano = function (data) {
    const root = document.getElementById("calidad-estadisticas-altiplano-root");
    if (!root || !data) return;

    const sections = Array.isArray(data.sections) ? data.sections : [];
    const generated = _formatGeneratedAt(data.generated_at);
    const notes = Array.isArray(data.notes) ? data.notes : [];

    if (!data.ok && !sections.length) {
      root.innerHTML = `<p class="muted calidad-resumen-loading">${_esc(data.message || "No se pudieron cargar los conteos de Altiplano.")}</p>`;
      return;
    }

    const blocks = sections
      .map((section) => {
        const cards = (section.cards || []).map(_bigCard).join("");
        const cols = _colsForSection(section);
        return `
        <section class="calidad-superset-block calidad-superset-block--altiplano">
          <h2 class="calidad-superset-title">${_esc(section.title || section.id || "")}</h2>
          ${_renderBigRow(cards, cols)}
        </section>`;
      })
      .join("");

    const notesHtml = notes.length
      ? `<ul class="calidad-estadisticas-altiplano-notes muted">${notes.map((n) => `<li>${_esc(n)}</li>`).join("")}</ul>`
      : "";

    root.classList.add("calidad-estadisticas-root--loaded");
    root.innerHTML = `
      <div class="calidad-resumen-shell">
        <p class="calidad-estadisticas-meta muted">
          Conteos globales INP · intent <strong>ont-connection</strong>${generated ? ` · Actualizado <strong>${_esc(generated)}</strong>` : ""}
        </p>
        ${blocks}
        ${notesHtml}
      </div>`;
  };

  window.loadCalidadEstadisticasAltiplano = async function (opts) {
    const root = document.getElementById("calidad-estadisticas-altiplano-root");
    if (!root) return;
    const refresh = !opts || opts.refresh !== false;
    root.innerHTML = _loading("Cargando Altiplano…");
    root.classList.remove("calidad-estadisticas-root--loaded");
    try {
      const api = CD.api?.altiplano || "/dashboard/estadisticas/altiplano.json";
      const params = refresh ? "?refresh=1" : "";
      const r = await fetch(`${api}${params}`);
      const data = await r.json();
      if (!r.ok && !data.sections) {
        throw new Error("altiplano");
      }
      window.renderCalidadEstadisticasAltiplano(data);
    } catch (_e) {
      root.innerHTML =
        '<p class="muted calidad-resumen-loading">No se pudieron cargar las estadísticas de Altiplano.</p>';
      if (typeof qualityToast === "function") {
        qualityToast("No se pudieron cargar estadísticas Altiplano");
      }
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-refresh-estadisticas-altiplano")?.addEventListener("click", () => {
      window.loadCalidadEstadisticasAltiplano();
    });
  });
})();
