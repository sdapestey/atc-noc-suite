import re


def test_dashboard_calidad_inventario_get_renders(client):
    r = client.get("/dashboard/calidad-inventario")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Calidad Inventario" in html
    assert 'id="f-regla"' in html
    assert 'id="f-operador"' in html
    assert 'id="f-q"' in html
    assert "dashboard-calidad-inventario.js" in html


def test_dashboard_entry_redirect_calidad(client):
    r = client.get("/dashboard?tab=calidad-inventario", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/calidad-inventario")


def test_dashboard_calidad_resumen_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_resumen",
        lambda: {
            "total_aid_in_service": 10,
            "aid_sin_match_serial": 1,
            "aid_sin_match_olt": 2,
            "aid_path_atc_nulo_vacio": 3,
            "aid_cto_nulo_vacio": 4,
            "aid_serial_nulo_vacio": 5,
            "aid_invocator_system_nulo_en_olt": 6,
        },
    )
    r = client.get("/dashboard/calidad-inventario/resumen.json")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_aid_in_service"] == 10
    assert payload["aid_sin_match_serial"] == 1


def test_dashboard_calidad_hallazgos_json_filters(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_hallazgos(**kwargs):
        captured.update(kwargs)
        return {"rules": [], "filters": kwargs, "count": 1, "findings": []}

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", fake_hallazgos)
    r = client.get("/dashboard/calidad-inventario/hallazgos.json?regla=missing_olt_match&operador=1001&q=TG01")
    assert r.status_code == 200
    assert captured["regla"] == "missing_olt_match"
    assert captured["operador"] == "1001"
    assert captured["q"] == "TG01"


def test_dashboard_calidad_export_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_dashboard_calidad_inventario_csv",
        lambda **_kwargs: "regla,access_id,path_atc,cto,operador,severidad\r\nSin match en OLT,123,R1,C1,1001,alta\r\n",
    )
    r = client.get("/dashboard/calidad-inventario/export.csv?regla=missing_olt_match")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert "attachment; filename=dashboard_calidad_inventario.csv" in r.headers["Content-Disposition"]
    assert "regla,access_id,path_atc,cto,operador,severidad" in r.get_data(as_text=True)


def test_dashboard_calidad_hallazgos_internal_error_includes_request_id(client, monkeypatch):
    import web.routes as routes

    def _boom(**_kwargs):
        raise RuntimeError("failed")

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", _boom)
    r = client.get("/dashboard/calidad-inventario/hallazgos.json")
    assert r.status_code == 500
    payload = r.get_json()
    assert "request_id" in payload
    assert re.search(r".+", payload["request_id"])
