"""Inferencia de tipo de consulta Camino óptico (FATC / RATC / Access ID)."""
import services.camino_optico as co


def test_infer_camino_fatc():
    assert co.infer_camino_consulta_tipo("TG01-FATC-8-110066") == "cto"
    assert co.infer_camino_consulta_tipo("  sf01-fatc-8-200189 ") == "cto"


def test_infer_camino_ratc():
    assert co.infer_camino_consulta_tipo("TG01-RATC-0-000808") == "rama"


def test_infer_camino_access_id():
    assert co.infer_camino_consulta_tipo("1052404324") == "access_id"
    assert co.infer_camino_consulta_tipo("  1052404324  ") == "access_id"
    assert co.infer_camino_consulta_tipo("105 240 4324") == "access_id"


def test_infer_camino_unknown():
    assert co.infer_camino_consulta_tipo("") is None
    assert co.infer_camino_consulta_tipo("texto-sin-subcadena") is None


def test_camino_consultar_sin_tipo_usa_inferencia(client, monkeypatch):
    import web.routes as routes

    def fake_cto(v):
        assert v == "X-FATC-1-1"
        return {"tipo": "cto", "cto": v}

    monkeypatch.setattr(routes, "dashboard_camino_optico_cto", fake_cto)

    r = client.post(
        "/dashboard/camino-optico/consultar",
        json={"valor": "X-FATC-1-1"},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["tipo"] == "cto"
