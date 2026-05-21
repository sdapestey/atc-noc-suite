"""Smoke del endpoint JSON de coordenadas CTO para el mapa RAMA / CTO."""

import web.routes as routes


def test_cto_map_requires_cto(client):
    r = client.get("/dashboard/rama/cto-map")
    assert r.status_code == 400
    data = r.get_json()
    assert data.get("ok") is False


def test_cto_map_returns_coords(monkeypatch, client):
    monkeypatch.setattr(
        routes,
        "consultar_cto_coordenadas",
        lambda cto: {"lat": -34.6037, "lon": -58.3816},
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas_desde_sfat", lambda cto: None)
    r = client.get("/dashboard/rama/cto-map", query_string={"cto": "X-FATC-1"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("cto") == "X-FATC-1"
    assert data.get("lat") == -34.6037
    assert data.get("lon") == -58.3816


def test_cto_map_no_coords(monkeypatch, client):
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda cto: None)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas_desde_sfat", lambda cto: None)
    r = client.get("/dashboard/rama/cto-map", query_string={"cto": "Y-FATC-2"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is False
    assert "coordenadas" in (data.get("error") or "").lower()


def test_cto_map_uses_sfat_fallback(monkeypatch, client):
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda cto: None)
    monkeypatch.setattr(
        routes,
        "consultar_cto_coordenadas_desde_sfat",
        lambda cto: {"lat": -34.39, "lon": -58.73},
    )
    r = client.get("/dashboard/rama/cto-map", query_string={"cto": "TG01-FATC-8-104022"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("lat") == -34.39
    assert data.get("lon") == -58.73


def test_cto_address_requires_cto(client):
    r = client.get("/dashboard/rama/cto-address")
    assert r.status_code == 400
    data = r.get_json()
    assert data.get("ok") is False


def test_cto_address_returns_value(monkeypatch, client):
    monkeypatch.setattr(
        routes,
        "consultar_cto_direccion_postal",
        lambda cto: "Alvear 2464 (BA San Fernando)",
    )
    r = client.get("/dashboard/rama/cto-address", query_string={"cto": "X-FATC-1"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("address") == "Alvear 2464 (BA San Fernando)"


def test_cto_address_no_value(monkeypatch, client):
    monkeypatch.setattr(routes, "consultar_cto_direccion_postal", lambda cto: None)
    r = client.get("/dashboard/rama/cto-address", query_string={"cto": "X-FATC-1"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is False
    assert "dirección" in (data.get("error") or "").lower()
