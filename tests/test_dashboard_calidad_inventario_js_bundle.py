from pathlib import Path


def test_dashboard_calidad_js_contains_core_handlers():
    js = Path("static/js/dashboard-calidad-inventario.js").read_text(encoding="utf-8")
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
    html = Path("templates/dashboard_calidad_inventario.html").read_text(encoding="utf-8")
    assert "dashboard-calidad-resumen.js" in html
    assert 'id="panel-resumen"' in html


def test_dashboard_calidad_resumen_js_bundle():
    js = Path("static/js/dashboard-calidad-resumen.js").read_text(encoding="utf-8")
    assert "renderCalidadResumenGeneral" in js
    assert "loadCalidadResumenGeneral" in js
    assert "resumen-general.json" in js
    assert "calidad-superset-block" in js
    assert "tabla.json" in js
    assert "calidad-big-card__kpi" in js
    assert "motion.div" not in js
