"""Smoke del endpoint JSON de mapa por RAMA (todas las CTO con coordenadas)."""

import web.routes as routes


def test_rama_map_requires_rama(client):
    r = client.get("/dashboard/rama/rama-map")
    assert r.status_code == 400
    assert r.get_json().get("ok") is False


def test_rama_map_empty_inventory(monkeypatch, client):
    monkeypatch.setattr(routes, "inventario_dashboard_rama", lambda r: {})
    r = client.get("/dashboard/rama/rama-map", query_string={"rama": "R1-RATC"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("markers") == []
    assert data.get("ctos_total") == 0


def test_rama_map_marks_partial_coords(monkeypatch, client):
    monkeypatch.setattr(
        routes,
        "inventario_dashboard_rama",
        lambda rama: {"A-FATC-1": [], "B-FATC-2": []},
    )
    monkeypatch.setattr(
        routes,
        "consultar_cto_coordenadas_batch",
        lambda ctos: {
            c: {"lat": -34.6, "lon": -58.4}
            for c in ctos
            if c == "A-FATC-1"
        },
    )
    monkeypatch.setattr(routes, "_consultar_cto_coords_con_fallback", lambda cto: None)

    r = client.get("/dashboard/rama/rama-map", query_string={"rama": "SF01-RATC"})
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok") is True
    assert data.get("ctos_total") == 2
    assert data.get("ctos_sin_coordenadas") == 1
    assert len(data.get("markers") or []) == 1
    assert data["markers"][0]["cto"] == "A-FATC-1"
    assert data["markers"][0]["lat"] == -34.6
