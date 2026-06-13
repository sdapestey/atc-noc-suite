from pathlib import Path


def test_dashboard_calidad_js_contains_core_handlers():
    js = Path("static/js/dashboard-estadisticas-reglas.js").read_text(encoding="utf-8")
    assert "function refreshCalidadDashboard()" in js
    assert "function fetchResumen()" in js
    assert "function fetchFindings(" in js
    assert "function switchTab(" in js
    assert "function renderKpiGrid(" in js
    assert "function syncExportLink(" in js
    assert "function syncReglaRuleHelp()" in js
    assert "calidad-rules-chart" in js
    assert "calidad-pagination" in js
    assert "f-regla-rule-help" in js
    assert "window.switchTab = switchTab" in js
    assert "window.resetCalidadHallazgosPage" in js
    html = Path("templates/dashboard_estadisticas.html").read_text(encoding="utf-8")
    est_js = Path("static/js/dashboard-estadisticas-altas-bajas.js").read_text(encoding="utf-8")
    assert "dashboard-estadisticas-shared.js" in html
    assert "dashboard-estadisticas-inventario.js" in html
    assert "dashboard-estadisticas-reglas.js" in html
    assert "dashboard-estadisticas-altas-bajas.js" in html
    assert "CalidadDashboard" in Path("static/js/dashboard-estadisticas-shared.js").read_text(encoding="utf-8")
    assert 'id="panel-inventario"' in html
    assert "apiBase" in Path("static/js/dashboard-estadisticas-shared.js").read_text(encoding="utf-8")
    assert "CD.api.altasBajas" in est_js
    assert "loadCalidadEstadisticas" in est_js
    assert "calidad-big-card--stat-alta" in est_js
    assert "calidad-big-card--stat-baja" in est_js
    assert "calidad-big-card--op-" in est_js
    assert "Totales — Altas" in est_js
    assert "calidad-big-card--ab" not in est_js
    assert "calidad-big-row--" in est_js
    assert "_renderBigRow" in est_js
    assert "by_operator" in est_js
    assert "estadisticas-range" not in est_js
    assert 'id="estadisticas-fecha"' in html
    assert "estadisticas-flatpickr.css" in html
    assert "flatpickr" in html
    assert "data-granularity=\"month\"" in html
    assert "data-granularity=\"day\"" not in html
    assert "estadisticas-fecha" in est_js
    assert "sftp_backup_latest" not in est_js
    assert html.count("Fuentes de datos (referencia)") == 4
    assert "ibn:search-intents" in html
    assert "aux.bajas_de_inventario" in html


def test_dashboard_calidad_resumen_js_bundle():
    js = Path("static/js/dashboard-estadisticas-inventario.js").read_text(encoding="utf-8")
    assert "renderCalidadResumenGeneral" in js
    assert "loadCalidadResumenGeneral" in js
    assert "resumen-general.json" not in js
    assert "CD.api.inventario" in js
    assert "calidad-superset-block" in js
    assert "CD.api.inventarioTabla" in js
    assert "calidad-big-card__kpi" in js
    assert "motion.div" not in js
