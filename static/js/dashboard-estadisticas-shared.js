/* Utilidades compartidas — dashboard Estadisticas */
(function (global) {
  const API_BASE = "/dashboard/estadisticas";

  function fmtCount(n) {
    const x = Number(n);
    if (!Number.isFinite(x)) return "—";
    return x.toLocaleString("es-AR");
  }

  function esc(v) {
    return String(v || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function opSlug(label) {
    return String(label || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  function renderBigRow(cardsHtml, cols) {
    return `<div class="calidad-big-row calidad-big-row--${cols}">${cardsHtml}</div>`;
  }

  function sectionTitle(text, id) {
    return `<h2 class="calidad-superset-title" ${id ? `id="${esc(id)}"` : ""}>${esc(text)}</h2>`;
  }

  function renderLoadingStatus(message) {
    return `<div class="calidad-resumen-loading" role="status" aria-live="polite" aria-busy="true">
      <span class="calidad-resumen-spinner" aria-hidden="true"></span>
      <span>${esc(message)}</span>
    </div>`;
  }

  global.CalidadDashboard = {
    apiBase: API_BASE,
    api: {
      inventario: `${API_BASE}/inventario.json`,
      inventarioTabla: `${API_BASE}/inventario/tabla.json`,
      altasBajas: `${API_BASE}/altas-bajas.json`,
      altiplano: `${API_BASE}/altiplano.json`,
      reglasResumen: `${API_BASE}/reglas/resumen.json`,
      reglasHallazgos: `${API_BASE}/reglas/hallazgos.json`,
      reglasExportCsv: `${API_BASE}/reglas/export.csv`,
    },
    fmtCount,
    esc,
    opSlug,
    renderBigRow,
    sectionTitle,
    renderLoadingStatus,
  };
})(typeof window !== "undefined" ? window : globalThis);
