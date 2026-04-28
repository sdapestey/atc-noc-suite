from pathlib import Path


def test_dashboard_rama_js_contains_core_handlers():
    js = Path("static/js/dashboard-rama.js").read_text(encoding="utf-8")
    assert "function consultarRama(" in js
    assert "function consultarAidRama(" in js
    assert "function restoreRamaDashboardState(" in js
    assert "_expandAllCtosInRamaCard" in js
    assert "_setRamaCardTxRxCellsLoading" in js
