"""GET /dashboard/camino-optico/arbol-olt.json — jerarquía OLT para mapa por casillas."""


def test_arbol_olt_json_ok(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_olts",
        lambda: [
            {
                "PRINCIPAL": "Moreno",
                "SEARCH_TEXT": "moreno",
                "OLTS": [
                    {
                        "OLT_LOGICO": "BA_OLTA_MR01_01",
                        "SITIO_CODIGO": "MR01_01",
                        "SEARCH_TEXT": "x",
                        "LTS": [{"LT": "BA_OLTA_MR01_01.LT1", "RAMAS": 2}],
                    }
                ],
            }
        ],
    )

    r = client.get("/dashboard/camino-optico/arbol-olt.json")
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["tree"][0]["PRINCIPAL"] == "Moreno"
    assert j["tree"][0]["OLTS"][0]["LTS"][0]["LT"] == "BA_OLTA_MR01_01.LT1"
