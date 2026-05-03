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
    r = client.get("/dashboard/rama/cto-map", query_string={"cto": "X-FATC-1"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("cto") == "X-FATC-1"
    assert data.get("lat") == -34.6037
    assert data.get("lon") == -58.3816


def test_cto_map_no_coords(monkeypatch, client):
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda cto: None)
    r = client.get("/dashboard/rama/cto-map", query_string={"cto": "Y-FATC-2"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is False
    assert "coordenadas" in (data.get("error") or "").lower()
