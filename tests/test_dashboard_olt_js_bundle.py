from pathlib import Path


def test_dashboard_olt_pon_badge_selected_style():
    css = Path("static/css/devops-dashboard.css").read_text(encoding="utf-8")
    assert ":has(.pon-select:checked) .rama-row-kind--pon" in css
    assert "var(--success-text)" in css
    assert ".olt-selection-summary-operadores" in css
    assert ".olt-metric-pill--op-tasa" in css
    assert "olt-metric-pill--copy" in css


def test_dashboard_olt_js_contains_core_handlers():
    js = Path("static/js/dashboard-olt.js").read_text(encoding="utf-8")
    assert "function buildPonBlockHtml(" in js
    assert "updatePonesSelectionSummary" in js
    assert 'getElementById("pon-selection-summary")' in js
    assert "data-pon-id=" in js
    assert "function findTrByAid(" in js
    assert "Consultar RX" in js
    assert "rama-row-kind--pon" in js
    assert "cto-head-row" in js
    assert "function toggleLTCargar(" in js
    assert "function restoreOltDashboardState(" in js
    assert "function potenciaCto(" in js
    assert "function potenciaRama(" in js
    assert "function enfocarFilaLtCoincidente(" in js
    assert "function _scheduleOltLtRowScroll(" in js
    assert 'behavior: "smooth"' in js
    assert "typingInSearch" not in js
    assert "olt-lt-search-hit" in js
    assert 'id="olt-export-operador"' in Path("templates/dashboard_olt.html").read_text(
        encoding="utf-8"
    )
    assert "function _buildPonExportLines(" in js
    assert "function _collectPonExportData(" in js
    assert "function _formatPonExportGrouped(" in js
    assert "function _formatPonExportFlatSparse(" in js
    assert 'format: "grouped"' in js
    assert 'format: "flat-sparse"' in js
    assert "function _copyPonSelectionList(" in js
    assert "function _copyPonSelectionOperador(" in js
    assert "data-olt-copy" in js
    assert "data-olt-operador" in js
    assert "_OLT_OPERADORES_ORDEN" in js
    assert "function _oltOperadorSummaryHtml(" in js
    assert "(counts[op] || 0) > 0" in js
    assert "olt-selection-summary-operadores" in js
    assert "function _sanitizeExportBasename(" in js
    assert "function _exportDateStamp(" in js
    assert "pones_seleccionados_" in js
    assert "function _shouldListExportOperator(" in js
    assert "finalizeTxRxLoadingCell" in js
    assert "filaTieneAidConsulta" in js
    assert "_oltFinalizeTxRxPendientesEn" in js
    assert "_skipAutoPotenciasCto" in js
    assert "_oltRamaPotenciasCache" in js
    assert "autoPotencias !== false" in js
    assert "_syncTreeNodeAccentVisual" in js
    assert "_OLT_TREE_ACCENT_CLASSES" in js
    assert "<th>Estado</th>" not in js
    assert "OLT_COL_EST" not in js
    assert "/dashboard/olt/semaforo-historico" in js
    assert "function _cargarSemaforoHistoricoOlt(" in js
    assert "olt-lt-row--semaforo-historico" in js
    assert "_restorePeorSiPendiente" in js
    assert 'peCell.textContent.trim() === "…"' in js
    assert "function applyOltUrlDeepLink(" in js
    assert "select_pon" in js
    assert "_parseOltPonKey" in js
    assert "_showOltDeepLinkLoading" in js
    assert "Completado" in js
    tpl = Path("templates/dashboard_olt.html").read_text(encoding="utf-8")
    assert "olt-deep-link-status" in tpl
    assert "lt-detail-spinner" in tpl
