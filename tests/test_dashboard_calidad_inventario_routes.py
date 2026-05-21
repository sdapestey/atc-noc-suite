import re


def test_dashboard_calidad_inventario_get_renders(client):
    r = client.get("/dashboard/calidad-inventario")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Calidad Inventario" in html
    assert 'class="page-lead"' in html
    assert "cm.inventory_fat_occupation" in html
    assert "cm.inventory_olt_occupation" in html
    assert "altiplano.serial" in html
    assert "aux.bajada_inventario" in html
    assert 'data-tab="resumen"' in html
    assert 'id="tab-resumen"' in html
    assert html.index('data-tab="resumen"') < html.index('data-tab="reglas"')
    assert 'id="panel-resumen"' in html
    assert 'id="panel-reglas"' in html
    assert 'id="panel-reglas" class="panel calidad-panel" role="tabpanel" aria-labelledby="tab-reglas" hidden' in html
    assert 'id="f-regla"' in html
    assert 'id="f-estado"' in html
    assert 'id="f-operador"' in html
    assert 'id="f-q"' in html
    assert 'id="qualityCount"' in html
    assert "calidad-hallazgos-count-wrap" in html
    assert "dashboard-calidad-inventario.js" in html
    assert "dashboard-calidad-resumen.js" in html
    assert "chart.js" in html
    assert 'class="calidad-tabs"' in html
    assert 'id="calidad-resumen-root"' in html
    assert 'id="calidad-rules-chart"' in html
    assert 'id="calidad-pagination"' in html
    assert "aux.conciliaciones" in html
    assert html.index('id="qualityCount"') > html.index('class="controls"')
    assert html.index('id="qualityCount"') < html.index('id="f-operador"')


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
            "total_aid_reserved": 3,
            "total_aid_to_be_deleted": 2,
            "total_aid_free": 7,
            "aid_sin_match_serial": 1,
            "aid_sin_match_olt": 2,
            "aid_path_atc_nulo_vacio": 3,
            "aid_serial_nulo_vacio": 5,
        },
    )
    r = client.get("/dashboard/calidad-inventario/resumen.json")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_aid_in_service"] == 10
    assert payload["total_aid_reserved"] == 3
    assert payload["total_aid_to_be_deleted"] == 2
    assert payload["total_aid_free"] == 7
    assert payload["aid_sin_match_serial"] == 1


def test_dashboard_calidad_resumen_general_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_resumen_general",
        lambda days=90: {
            "operators": [{"id": "1001", "label": "TASA", "altiplano": 1, "connect_master": 2}],
            "totals": {"connect_master_in_service": 10, "altiplano_activos": 11},
            "comparativa_operadores": [],
            "total_casos_rotos": 399,
            "historico": {"days": days, "series": []},
        },
    )
    r = client.get("/dashboard/calidad-inventario/resumen-general.json?days=30")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_casos_rotos"] == 399
    assert payload["historico"]["days"] == 30


def test_dashboard_calidad_tabla_json_invalid_tipo(client):
    r = client.get("/dashboard/calidad-inventario/tabla.json?tipo=invalid")
    assert r.status_code == 400


def test_dashboard_calidad_hallazgos_json_pagination(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_hallazgos(**kwargs):
        captured.update(kwargs)
        return {"rules": [], "filters": kwargs, "total_count": 120, "count": 50, "findings": []}

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", fake_hallazgos)
    r = client.get("/dashboard/calidad-inventario/hallazgos.json?limit=50&offset=50")
    assert r.status_code == 200
    assert captured["limit"] == 50
    assert captured["offset"] == 50


def test_dashboard_calidad_conciliacion_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_conciliacion",
        lambda: {
            "operators": [{
                "id": "1001",
                "label": "TASA",
                "vno": "1001",
                "connect_master": 84656,
                "altiplano": 85451,
                "in_service": 84656,
                "reserved": 0,
            }],
            "totals": {
                "connect_master_in_service": 91286,
                "altiplano_activos": 93517,
            },
        },
    )
    r = client.get("/dashboard/calidad-inventario/conciliacion.json")
    assert r.status_code == 200
    assert r.get_json()["operators"][0]["id"] == "1001"


def test_dashboard_calidad_historico_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_historico",
        lambda days=90: {"days": days, "series": [{"fecha": "2026-01-01", "cm_no_nokia": 1, "nokia_no_cm": 2}]},
    )
    r = client.get("/dashboard/calidad-inventario/historico.json?days=30")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["days"] == 30
    assert payload["series"][0]["cm_no_nokia"] == 1


def test_dashboard_calidad_hallazgos_json_filters(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_hallazgos(**kwargs):
        captured.update(kwargs)
        return {"rules": [], "filters": kwargs, "count": 1, "findings": []}

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", fake_hallazgos)
    r = client.get(
        "/dashboard/calidad-inventario/hallazgos.json?regla=missing_olt_match&estado_base=RESERVED&operador=1001&q=TG01"
    )
    assert r.status_code == 200
    assert captured["regla"] == "missing_olt_match"
    assert captured["estado_base"] == "RESERVED"
    assert captured["operador"] == "1001"
    assert captured["q"] == "TG01"


def test_dashboard_calidad_export_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_dashboard_calidad_inventario_csv",
        lambda **_kwargs: (
            "regla,access_id,estado_base,path_atc,cto,operador\r\n"
            "Sin match en OLT,123,IN SERVICE,R1,C1,1001\r\n"
        ),
    )
    r = client.get("/dashboard/calidad-inventario/export.csv?regla=missing_olt_match")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert "attachment; filename=dashboard_calidad_inventario.csv" in r.headers["Content-Disposition"]
    assert "regla,access_id,estado_base,path_atc,cto,operador" in r.get_data(as_text=True)


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
