import re

def test_dashboard_potencias_historico_get_renders(client):
    r = client.get("/dashboard/potencias-historico")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Historico Potencias" in html
    assert 'id="ratc-input"' in html
    assert 'id="power-chart"' in html
    assert "/api/potencias-historico/" in html
    assert "btn-toggle-legend" in html
    assert "btn-show-all" in html
    assert "btn-hide-all" in html


def test_api_potencias_historico_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": True,
            "labels": ["2026-04-24 20:00"],
            "datasets": [{"label": "ONT 1", "data": [-18.5]}],
            "pon": "BA_OLTA_MR01_01-1-1",
            "median": -18.5,
            "total_onts": 1,
            "status": "Activo",
            "days": days,
            "rows": [],
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200?days=15")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["pon"] == "BA_OLTA_MR01_01-1-1"
    assert payload["total_onts"] == 1
    assert payload["days"] == 15


def test_api_potencias_historico_not_found(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": False,
            "status_code": 404,
            "error": "Rama RATC no encontrada en inventario",
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-999999")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_dashboard_entry_redirect_historico(client):
    r = client.get("/dashboard?tab=potencias-historico", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/potencias-historico")


def test_api_potencias_historico_invalid_days_400(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 7, 15, 30",
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200?days=8")
    assert r.status_code == 400
    assert "days" in r.get_json()["error"]


def test_export_potencias_historico_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": True,
            "csv": "timestamp,objectname,ont,rx_dbm,pon\r\n2026-04-25 00:00,BA_OLTA_X-1-1-1,1,-18.3,BA_OLTA_X-1-1\r\n",
            "ratc": _ratc,
            "days": days,
        },
    )
    r = client.get("/dashboard/potencias-historico/export.csv?ratc=MR01-RATC-0-000200&days=7")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    cd = r.headers["Content-Disposition"]
    assert "attachment; filename=potencias_historico_MR01-RATC-0-000200_7d_" in cd
    assert re.search(r"\d{8}_\d{4}\.csv", cd)
    assert "timestamp,objectname,ont,rx_dbm,pon" in r.get_data(as_text=True)


def test_export_potencias_historico_csv_invalid_days_400(client):
    r = client.get("/dashboard/potencias-historico/export.csv?ratc=MR01-RATC-0-000200&days=9")
    assert r.status_code == 400
    assert "days" in r.get_json()["error"]


def test_api_potencias_historico_internal_error_includes_request_id(client, monkeypatch):
    import web.routes as routes

    def _boom(_ratc, days=30):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes, "consultar_potencias_historico_rama", _boom)
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200")
    assert r.status_code == 500
    payload = r.get_json()
    assert "error" in payload
    assert "request_id" in payload
