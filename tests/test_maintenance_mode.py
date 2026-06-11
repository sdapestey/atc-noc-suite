def test_maintenance_mode_disabled_by_default(client):
    r = client.get("/")
    assert r.status_code == 200


def test_maintenance_mode_blocks_html_pages(client, monkeypatch):
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    r = client.get("/")
    assert r.status_code == 503
    assert b"En mantenimiento" in r.data
    assert b"ATC NOC Suite" not in r.data or b"En mantenimiento" in r.data


def test_maintenance_mode_custom_message(client, monkeypatch):
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    monkeypatch.setenv("MAINTENANCE_MESSAGE", "Actualizando base de datos")
    r = client.get("/dashboard/rama")
    assert r.status_code == 503
    assert b"Actualizando base de datos" in r.data


def test_maintenance_mode_allows_health_and_static(client, monkeypatch):
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    health = client.get("/health")
    assert health.status_code == 200
    static = client.get("/static/css/splash.css")
    assert static.status_code == 200


def test_maintenance_mode_blocks_api_json(client, monkeypatch):
    monkeypatch.setenv("MAINTENANCE_MODE", "1")
    r = client.get("/api/potencias-historico", headers={"Accept": "application/json"})
    assert r.status_code == 503
    data = r.get_json()
    assert data.get("maintenance") is True
    assert data.get("error") == "En mantenimiento"
