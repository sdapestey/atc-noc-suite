from pathlib import Path


def test_dashboard_olt_pon_badge_selected_style():
    css = Path("static/css/devops-dashboard.css").read_text(encoding="utf-8")
    assert ":has(.pon-select:checked) .rama-row-kind--pon" in css
    assert "var(--success-text)" in css
    assert ".olt-selection-summary-operadores" in css
    assert ".olt-metric-pill--op-tasa" in css


def test_dashboard_olt_js_contains_core_handlers():
    js = Path("static/js/dashboard-olt.js").read_text(encoding="utf-8")
    assert "function buildPonBlockHtml(" in js
    assert "Consultar RX" in js
    assert "rama-row-kind--pon" in js
    assert "cto-head-row" in js
    assert "function toggleLTCargar(" in js
    assert "function restoreOltDashboardState(" in js
    assert "function potenciaCto(" in js
    assert "function potenciaRama(" in js
    assert "function enfocarFilaLtCoincidente(" in js
    assert "olt-lt-search-hit" in js
    assert 'id="olt-export-operador"' in Path("templates/dashboard_olt.html").read_text(
        encoding="utf-8"
    )
    assert "function _buildPonExportLines(" in js
    assert "_OLT_OPERADORES_ORDEN" in js
    assert "function _oltOperadorSummaryHtml(" in js
    assert "(counts[op] || 0) > 0" in js
    assert "olt-selection-summary-operadores" in js
    assert "function _sanitizeExportBasename(" in js
    assert "function _shouldListExportOperator(" in js
    assert "finalizeTxRxLoadingCell" in js
    assert "filaTieneAidConsulta" in js
    assert "_oltFinalizeTxRxPendientesEn" in js
    assert "_skipAutoPotenciasCto" in js
    assert "_oltRamaPotenciasCache" in js
    assert "autoPotencias !== false" in js
    assert "<th>Estado</th>" not in js
    assert "OLT_COL_EST" not in js
