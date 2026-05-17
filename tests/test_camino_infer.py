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


def test_infer_camino_lt():
    assert co.infer_camino_consulta_tipo("BA_OLTA_MR01_01.LT1") == "lt"
    assert co.infer_camino_consulta_tipo("  ba_olta_mr01_02.lt2 ") == "lt"


def test_normalize_lt_key_equivalence():
    assert co._normalize_lt_key("BA_OLTA_MR01_01.LT1") == co._normalize_lt_key(
        "BA_OLTA_MR01_01.LT01"
    )


def test_infer_camino_sitio():
    assert co.infer_camino_consulta_tipo("Moreno") == "sitio"
    assert co.infer_camino_consulta_tipo("MR01") == "sitio"
    assert co.infer_camino_consulta_tipo("sitio:Tigre") == "sitio"


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


def test_camino_consultar_lt_por_inferencia(client, monkeypatch):
    import web.routes as routes

    def fake_lt(v):
        assert v.strip() == "BA_OLTA_X.LT1"
        return {"tipo": "lt", "lt": v.strip(), "resumen": {"rama_count": 0, "ramas": []}}

    monkeypatch.setattr(routes, "dashboard_camino_optico_lt", fake_lt)

    r = client.post(
        "/dashboard/camino-optico/consultar",
        json={"valor": "  BA_OLTA_X.LT1  "},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["tipo"] == "lt"
