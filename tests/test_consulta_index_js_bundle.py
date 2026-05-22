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
