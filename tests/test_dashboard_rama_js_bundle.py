from pathlib import Path


def test_dashboard_rama_js_contains_core_handlers():
    js = Path("static/js/dashboard-rama.js").read_text(encoding="utf-8")
    assert "function consultarRama(" in js
    assert "function consultarCtoRama(" in js
    assert "function restoreRamaDashboardState(" in js
    assert "_expandAllCtosInRamaCard" in js
    assert "_skipAutoPotenciasCto" in js
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
    assert "_ramaPotenciasParaCtosExpandidosEn" in js
    assert "function renderInventarioRama(" in js
    assert 'badge hide-sm cto-head-row__ont-count" title="ONT IN SERVICE en esta CTO">ONT ${ontCount}</span>' in js
    assert "NocClipboard" in js
    assert "NocMaps" in js or "Abrir en Maps" in Path("static/js/consulta-index-map.js").read_text(encoding="utf-8")
    assert "Cargando inventario de red…" in js
    assert "rama-detail-spinner" in js
    assert "<th>Estado</th>" not in js
    assert "RAMA_COL_EST" not in js
    assert "/dashboard/rama/semaforo-historico" in js
    assert "function _cargarSemaforoHistoricoSitio(" in js
