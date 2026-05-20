from pathlib import Path


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
    assert "function _sanitizeExportBasename(" in js
    assert "function _shouldListExportOperator(" in js
    assert "finalizeTxRxLoadingCell" in js
    assert "filaTieneAidConsulta" in js
    assert "_oltFinalizeTxRxPendientesEn" in js
    assert "<th>Estado</th>" not in js
    assert "OLT_COL_EST" not in js
