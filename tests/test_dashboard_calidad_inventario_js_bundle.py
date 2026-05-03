from pathlib import Path


def test_dashboard_calidad_js_contains_core_handlers():
    js = Path("static/js/dashboard-calidad-inventario.js").read_text(encoding="utf-8")
    assert "function refreshCalidadDashboard()" in js
    assert "function fetchResumen()" in js
    assert "function fetchFindings(" in js
    assert "function syncExportLink(" in js
    assert "function syncReglaRuleHelp()" in js
    assert "f-regla-rule-help" in js
