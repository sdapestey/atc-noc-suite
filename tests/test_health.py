def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True


def test_potencias_empty_value_400(client):
    r = client.post("/potencias", data={"value": ""})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_potencias_cto_refresh_bypasses_cache(client, monkeypatch):
    import web.routes as routes

    calls = []

    def fake_cached(cto):
        calls.append(("cached", cto))
        return [{"AID": "1", "TX": "1.0", "RX": "-20.0"}]

    def fake_live(cto, *, carga_masiva=False):
        calls.append(("live", cto, carga_masiva))
        return [{"AID": "1", "TX": "2.0", "RX": "-18.0"}]

    monkeypatch.setattr(routes, "consultar_cto_potencias_cached", fake_cached)
    monkeypatch.setattr(routes, "consultar_cto_potencias", fake_live)

    r1 = client.post("/potencias", data={"value": "ES01-FATC-8-105295"})
    assert r1.status_code == 200
    assert calls == [("cached", "ES01-FATC-8-105295")]

    calls.clear()
    r2 = client.post(
        "/potencias",
        data={"value": "ES01-FATC-8-105295", "refresh": "1"},
    )
    assert r2.status_code == 200
    assert calls == [("live", "ES01-FATC-8-105295", False)]
    assert r2.get_json()[0]["TX"] == "2.0"


    r = client.post("/dashboard/rama/consultar", data={"rama": ""})
    assert r.status_code == 400


def test_dash_cto_consultar_empty_400(client):
    r = client.post("/dashboard/cto/consultar", data={"cto": ""})
    assert r.status_code == 400


def test_dash_camino_consultar_empty_400(client):
    r = client.post(
        "/dashboard/camino-optico/consultar",
        json={"valor": "%%%sin-formato%%%"},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "error" in r.get_json()
    r2 = client.post(
        "/dashboard/camino-optico/consultar",
        json={"tipo": "cto", "valor": ""},
        content_type="application/json",
    )
    assert r2.status_code == 400
