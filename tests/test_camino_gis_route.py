"""POST /dashboard/camino-optico/gis — GeoJSON del camino por rama (cm.ci_op)."""


def test_camino_gis_valor_requerido(client):
    r = client.post("/dashboard/camino-optico/gis", json={})
    assert r.status_code == 400
    assert r.get_json().get("ok") is False


def test_camino_gis_ok(client, monkeypatch):
    import web.routes as routes

    def fake(v):
        assert v == "ES01-RATC-0-000001"
        return {
            "ok": True,
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-58.5, -34.6], [-58.4, -34.6]],
                        },
                        "properties": {"nombre_op": "ES01-RATC-0-000001"},
                    }
                ],
            },
            "table": "cm.ci_op",
        }

    monkeypatch.setattr(routes, "consultar_ci_op_por_rama", fake)
    r = client.post(
        "/dashboard/camino-optico/gis",
        json={"valor": "ES01-RATC-0-000001"},
        content_type="application/json",
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["geojson"]["features"][0]["properties"]["nombre_op"] == "ES01-RATC-0-000001"


def test_camino_gis_acepta_clave_rama(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_ci_op_por_rama",
        lambda v: {"ok": True, "geojson": {"type": "FeatureCollection", "features": []}},
    )
    r = client.post("/dashboard/camino-optico/gis", json={"rama": "X-RATC-0-1"})
    assert r.status_code == 200


def test_camino_gis_error_consulta(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_ci_op_por_rama",
        lambda v: {"ok": False, "error": "sin tabla"},
    )
    r = client.post("/dashboard/camino-optico/gis", json={"valor": "x"})
    assert r.status_code == 400
    assert "sin tabla" in r.get_json().get("error", "")
