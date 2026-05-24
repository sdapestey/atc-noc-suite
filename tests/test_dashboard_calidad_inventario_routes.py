import re

from tests.conftest import assert_csv_attachment


def test_dashboard_estadisticas_get_renders(client):
    r = client.get("/dashboard/estadisticas")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Estadisticas" in html
    assert "Inventario</button>" in html
    assert "Clientes ATC</button>" in html
    assert "Reglas de calidad</button>" in html
    assert 'data-tab="inventario"' in html
    assert 'data-tab="altas-bajas"' in html
    assert 'aria-selected="true" data-tab="altas-bajas"' in html
    assert 'aria-selected="false" data-tab="inventario"' in html
    assert (
        'id="panel-inventario" class="panel calidad-panel calidad-panel--inventario" '
        'role="tabpanel" aria-labelledby="tab-inventario" hidden'
    ) in html
    assert (
        'id="panel-altas-bajas" class="panel calidad-panel calidad-panel--altas-bajas" '
        'role="tabpanel" aria-labelledby="tab-altas-bajas">'
    ) in html
    assert "dashboard-estadisticas-shared.js" in html
    assert "dashboard-estadisticas-altas-bajas.js" in html
    assert html.index('data-tab="altas-bajas"') < html.index('data-tab="inventario"')
    assert html.index('data-tab="inventario"') < html.index('data-tab="reglas"')


def test_dashboard_calidad_inventario_legacy_redirects(client):
    r = client.get("/dashboard/calidad-inventario", follow_redirects=False)
    assert r.status_code == 308
    assert r.headers["Location"].endswith("/dashboard/estadisticas")

    r2 = client.get(
        "/dashboard/calidad-inventario/resumen-general.json?days=30",
        follow_redirects=False,
    )
    assert r2.status_code == 308
    assert "/dashboard/estadisticas/inventario.json" in r2.headers["Location"]
    assert "days=30" in r2.headers["Location"]


def test_dashboard_entry_redirect_estadisticas(client):
    for tab in ("estadisticas", "calidad", "calidad-inventario"):
        r = client.get(f"/dashboard?tab={tab}", follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/dashboard/estadisticas")


def test_dashboard_estadisticas_reglas_resumen_json_success(client, monkeypatch):
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
    r = client.get("/dashboard/estadisticas/reglas/resumen.json")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_aid_in_service"] == 10


def test_dashboard_estadisticas_inventario_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_resumen_general",
        lambda days=90: {
            "operators": [{"id": "1001", "label": "TASA", "altiplano": 1, "connect_master": 2}],
            "totales": {"connect_master_in_service": 10, "altiplano_activos": 11},
            "comparativa_operadores": [],
            "total_casos_rotos": 399,
            "historico": {"days": days, "series": []},
        },
    )
    r = client.get("/dashboard/estadisticas/inventario.json?days=30")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["total_casos_rotos"] == 399
    assert payload["historico"]["days"] == 30


def test_dashboard_estadisticas_inventario_tabla_json_invalid_tipo(client):
    r = client.get("/dashboard/estadisticas/inventario/tabla.json?tipo=invalid")
    assert r.status_code == 400


def test_dashboard_estadisticas_reglas_hallazgos_json_pagination(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_hallazgos(**kwargs):
        captured.update(kwargs)
        return {"rules": [], "filters": kwargs, "total_count": 120, "count": 50, "findings": []}

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", fake_hallazgos)
    r = client.get("/dashboard/estadisticas/reglas/hallazgos.json?limit=50&offset=50")
    assert r.status_code == 200
    assert captured["limit"] == 50
    assert captured["offset"] == 50


def test_dashboard_estadisticas_reglas_conciliacion_json_success(client, monkeypatch):
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
    r = client.get("/dashboard/estadisticas/reglas/conciliacion.json")
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    assert "inventario.json" in (r.headers.get("Link") or "")
    assert r.get_json()["operators"][0]["id"] == "1001"


def test_dashboard_estadisticas_altas_bajas_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_estadisticas",
        lambda days=90, granularity="day", operador="": {
            "source": "postgres",
            "days": days,
            "granularity": granularity,
            "filter": {"operador": operador, "operador_label": "TASA" if operador == "1001" else "Todos"},
            "cards": {"hoy": {"altas": 10, "bajas": 2}},
            "series": [{"fecha": "2026-05-22", "altas": 10, "bajas": 2}],
            "by_operator": [],
        },
    )
    r = client.get("/dashboard/estadisticas/altas-bajas.json?granularity=month")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["cards"]["hoy"]["altas"] == 10
    assert payload["granularity"] == "month"


def test_dashboard_estadisticas_reglas_historico_json_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_historico",
        lambda days=90: {"days": days, "series": [{"fecha": "2026-01-01", "cm_no_nokia": 1, "nokia_no_cm": 2}]},
    )
    r = client.get("/dashboard/estadisticas/reglas/historico.json?days=30")
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    assert "inventario.json?days=30" in (r.headers.get("Link") or "")
    payload = r.get_json()
    assert payload["days"] == 30
    assert payload["series"][0]["cm_no_nokia"] == 1


def test_dashboard_calidad_inventario_legacy_conciliacion_redirect_deprecation(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_conciliacion",
        lambda: {"operators": [], "totals": {}},
    )
    r = client.get("/dashboard/calidad-inventario/conciliacion.json", follow_redirects=True)
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    assert "/dashboard/estadisticas/reglas/conciliacion.json" in r.request.path or r.request.path.endswith(
        "conciliacion.json"
    )


def test_dashboard_calidad_inventario_legacy_historico_redirect_deprecation(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_calidad_inventario_historico",
        lambda days=90: {"days": days, "series": []},
    )
    r = client.get("/dashboard/calidad-inventario/historico.json?days=30", follow_redirects=True)
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    assert "inventario.json?days=30" in (r.headers.get("Link") or "")


def test_dashboard_estadisticas_reglas_hallazgos_json_filters(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_hallazgos(**kwargs):
        captured.update(kwargs)
        return {"rules": [], "filters": kwargs, "count": 1, "findings": []}

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", fake_hallazgos)
    r = client.get(
        "/dashboard/estadisticas/reglas/hallazgos.json?regla=missing_olt_match&estado_base=RESERVED&operador=1001&q=TG01"
    )
    assert r.status_code == 200
    assert captured["regla"] == "missing_olt_match"
    assert captured["estado_base"] == "RESERVED"
    assert captured["operador"] == "1001"
    assert captured["q"] == "TG01"


def test_dashboard_estadisticas_reglas_export_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_dashboard_calidad_inventario_csv",
        lambda **_kwargs: (
            "regla,access_id,estado_base,path_atc,cto,operador\r\n"
            "Sin match en OLT,123,IN SERVICE,R1,C1,1001\r\n"
        ),
    )
    r = client.get("/dashboard/estadisticas/reglas/export.csv?regla=missing_olt_match")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert_csv_attachment(r.headers["Content-Disposition"], "estadisticas_reglas.csv")
    assert "regla,access_id,estado_base,path_atc,cto,operador" in r.get_data(as_text=True)


def test_dashboard_estadisticas_reglas_hallazgos_internal_error_includes_request_id(client, monkeypatch):
    import web.routes as routes

    def _boom(**_kwargs):
        raise RuntimeError("failed")

    monkeypatch.setattr(routes, "dashboard_calidad_inventario_hallazgos", _boom)
    r = client.get("/dashboard/estadisticas/reglas/hallazgos.json")
    assert r.status_code == 500
    payload = r.get_json()
    assert "request_id" in payload
    assert re.search(r".+", payload["request_id"])
