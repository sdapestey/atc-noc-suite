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
    assert "NocMapTiles" in js
