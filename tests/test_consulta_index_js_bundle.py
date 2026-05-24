from pathlib import Path


def test_consulta_index_uses_external_js_bundle():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    js = Path("static/js/consulta-index.js").read_text(encoding="utf-8")
    assert "consulta-index.js" in html
    assert "__CONSULTA_INDEX_CFG__" in html
    assert "let _activeOperador" not in html
    assert "function cargarPotenciasSeccion" in js
    assert "togglePonAdminDesdeUI" in js
    assert "window.NocPower" in js
    assert "clearUrlInd" in js
    assert "clearUrlMas" in js
    assert "potenciasParallelMax" in html
    assert "_consultaPotenciasParallelMax" in js
    assert "_setConsultaDownPollCountdown" not in js
    assert "_CONSULTA_DOWN_POLL_COUNTDOWN_SEC" not in js
    assert "window.cargarPotenciasSeccion = cargarPotenciasSeccion" in js
    assert "window.consultaPotenciasCola = consultaPotenciasCola" in js
    assert "/potencias/batch" in js
    assert "_consultaCargarPotenciasEntries" in js
    assert "_consultaPotenciasTokenEsRamaOCto" in js
    assert '_consultaPotenciasTokenEsRamaOCto(tok)) return false' in js
    assert "window.cambiarSNDesdeUIBtn = cambiarSNDesdeUIBtn" in js
    assert "consultaSetBtnConsultando" in js
    assert "_consultaAcquireSectionPotenciaBtnsLoading" in js
    assert "skipBtnLoading" in js
    assert "releaseEntriesBtns" in js
    assert "window.togglePonAdminDesdeUIBtn = togglePonAdminDesdeUIBtn" in js
