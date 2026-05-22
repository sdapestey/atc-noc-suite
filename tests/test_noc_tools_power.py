from pathlib import Path

from services.domain import clasificar_rx_dbm, resumen_semaforo_desde_rx_values


def test_noc_tools_js_exports_noc_power_api():
    js = Path("static/js/noc-tools.js").read_text(encoding="utf-8")
    assert "window.NocPower" in js
    assert "parseRxDbm" in js
    assert "clasificarRxDbm" in js
    assert "formatPowerDbm" in js
    assert "rxHistoricoTone" in js
    assert "\\u2212" in js


def test_resumen_semaforo_desde_rx_values():
    assert resumen_semaforo_desde_rx_values([]) == {
        "ROJAS": 0,
        "AMARILLAS": 0,
        "VERDES": 0,
    }
    vals = [-28.0, -26.6, -24.0, None, "bad"]
    out = resumen_semaforo_desde_rx_values(vals)
    assert out["ROJAS"] == 1
    assert out["AMARILLAS"] == 1
    assert out["VERDES"] == 1
    assert clasificar_rx_dbm(-27) == "amarillo"
    assert clasificar_rx_dbm(-27.01) == "rojo"


def test_dashboards_use_noc_power():
    rama = Path("static/js/dashboard-rama.js").read_text(encoding="utf-8")
    olt = Path("static/js/dashboard-olt.js").read_text(encoding="utf-8")
    index_js = Path("static/js/consulta-index.js").read_text(encoding="utf-8")
    assert "NocPower" in rama
    assert "NocPower" in olt
    assert "window.NocPower" in index_js
