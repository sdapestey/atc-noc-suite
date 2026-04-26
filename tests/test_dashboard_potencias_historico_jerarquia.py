import re


def test_dashboard_potencias_historico_jerarquia_get_renders(client):
    r = client.get("/dashboard/potencias-historico-jerarquia")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Historico Potencias Jerarquia (PoC)" in html
    assert 'id="sel-sitio"' in html
    assert 'id="sel-olt"' in html
    assert "/api/potencias-historico/hierarquia" in html


def test_api_potencias_historico_hierarquia_tree_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_historico_hierarchy_tree",
        lambda: {
            "ok": True,
            "tree": [{"name": "MR01", "olts": [{"name": "BA_OLTA_MR01_01", "lts": []}]}],
        },
    )
    r = client.get("/api/potencias-historico/hierarquia")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["tree"][0]["name"] == "MR01"


def test_api_potencias_historico_hierarquia_consulta_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_hierarquia",
        lambda level, value, days=30: {
            "ok": True,
            "level": level,
            "value": value,
            "labels": ["2026-04-24 20:00"],
            "datasets": [{"label": "BA_OLTA_MR01_01-1-1-1", "data": [-18.1]}],
            "pones": ["BA_OLTA_MR01_01-1-1"],
            "total_onts": 1,
            "status": "Activo",
            "days": days,
            "rows": [],
        },
    )
    r = client.get("/api/potencias-historico/hierarquia/consulta?level=olt&value=BA_OLTA_MR01_01&days=15")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["level"] == "olt"
    assert payload["value"] == "BA_OLTA_MR01_01"
    assert payload["days"] == 15


def test_api_potencias_historico_hierarquia_consulta_invalid_level_400(client):
    r = client.get("/api/potencias-historico/hierarquia/consulta?level=foo&value=BAR&days=15")
    assert r.status_code == 400
    assert "level" in r.get_json()["error"]


def test_export_potencias_historico_hierarquia_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_potencias_historico_hierarquia",
        lambda level, value, days=30: {
            "ok": True,
            "csv": "timestamp,objectname,ont,rx_dbm,pon\r\n2026-04-25 00:00,BA_OLTA_X-1-1-1,1,-18.3,BA_OLTA_X-1-1\r\n",
            "level": level,
            "value": value,
            "days": days,
        },
    )
    r = client.get("/dashboard/potencias-historico/hierarquia/export.csv?level=olt&value=BA_OLTA_MR01_01&days=7")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    cd = r.headers["Content-Disposition"]
    assert "attachment; filename=potencias_historico_olt_BA_OLTA_MR01_01_7d_" in cd
    assert re.search(r"\d{8}_\d{4}\.csv", cd)
    assert "timestamp,objectname,ont,rx_dbm,pon" in r.get_data(as_text=True)

