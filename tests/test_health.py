def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True


def test_potencias_empty_value_400(client):
    r = client.post("/potencias", data={"value": ""})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_dash_rama_consultar_empty_400(client):
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
