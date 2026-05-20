from pathlib import Path


def test_dashboard_rama_js_contains_core_handlers():
    js = Path("static/js/dashboard-rama.js").read_text(encoding="utf-8")
    assert "function consultarRama(" in js
    assert "function consultarCtoRama(" in js
    assert "function restoreRamaDashboardState(" in js
    assert "_expandAllCtosInRamaCard" in js
    assert "_setRamaCardTxRxCellsLoading" in js
    assert "/dashboard/rama/cto-map" in js
    assert "/dashboard/rama/rama-map" in js
    assert "_bindRamaDashboardTabCollapse" in js
    assert "ensureCtoMapForCtoNode" in js
    assert "verMapaRama" in js
    assert "verMapaCto" in js
    assert "data-cto-map-panel" in js
    assert "NocMapTiles" in js
    assert "_sincronizarResaltadoPotenciasEn" in js
    assert "consulta-fila-sem-amarillo" in js
    assert "NocPower" in js
    assert "finalizeTxRxLoadingCell" in js
    assert "filaTieneAidConsulta" in js
    assert "_ramaFinalizeTxRxPendientes" in js
    assert "<th>Estado</th>" not in js
    assert "RAMA_COL_EST" not in js
