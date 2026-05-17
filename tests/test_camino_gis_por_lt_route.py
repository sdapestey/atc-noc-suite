"""POST /dashboard/camino-optico/gis-por-lt — GIS agregado por LT (superposición)."""


def test_gis_por_lt_lt_requerido(client):
    r = client.post("/dashboard/camino-optico/gis-por-lt", json={})
    assert r.status_code == 400
    assert r.get_json().get("ok") is False


def test_gis_por_lt_ok(client, monkeypatch):
    import web.routes as routes

    def fake(lt):
        assert lt == "BA_OLTA_X.LT1"
        return {
            "ok": True,
            "lt": lt,
            "resumen": {"rama_count": 2, "ramas": ["A-RATC-0-1", "A-RATC-0-2"]},
            "cto_markers": [],
            "gis": {"ok": True, "geojson": {"type": "FeatureCollection", "features": []}},
        }

    monkeypatch.setattr(routes, "gis_payload_para_lt", fake)
    r = client.post(
        "/dashboard/camino-optico/gis-por-lt",
        json={"lt": "BA_OLTA_X.LT1"},
        content_type="application/json",
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["lt"] == "BA_OLTA_X.LT1"


def test_gis_por_lt_sin_ramas_400(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "gis_payload_para_lt",
        lambda _lt: {"ok": False, "error": "Sin ramas"},
    )
    r = client.post("/dashboard/camino-optico/gis-por-lt", json={"lt": "BA_OLTA_Z.LT9"})
    assert r.status_code == 400
