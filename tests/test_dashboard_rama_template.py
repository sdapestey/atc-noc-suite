"""Smoke del template dashboard RAMA (toolbar CTO / sin expandir todo)."""


def _minimal_ramas():
    return [
        {
            "PRINCIPAL": "SitioTest",
            "SEARCH_TEXT": "sitiottest r1",
            "RAMAS": [
                {
                    "RAMA": "R1-RATC",
                    "CTO_COUNT": 1,
                    "ONT_COUNT": 1,
                    "ROJAS": 0,
                    "AMARILLAS": 0,
                    "VERDES": 0,
                },
            ],
        },
    ]


def test_dashboard_rama_includes_cto_selection_and_no_expand_all(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "dashboard_rama_bundle",
        lambda: {
            "bloques": _minimal_ramas(),
            "totales": {"RAMAS": 1, "CTO": 12, "ONT": 34},
        },
    )
    r = client.get("/dashboard/rama")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Expandir todo" not in html
    assert "Colapsar todo" in html
    assert "Copiar CTO seleccionadas" in html
    assert "Exportar CTO seleccionadas CSV" in html
    assert "Expandí la RAMA para cargar CTO/ONT." in html
    assert 'data-rama-detail' in html
    assert "Ver historico" in html
    assert "noc-map-tiles.js" in html
    assert "noc-map-fullscreen.js" in html
    assert "noc-tools.js" in html
    assert "dashboard-rama.js" in html
    assert "consultarRama(" in html
    assert "Ver mapa" in html
    assert "verMapaRama(" in html
    assert "rama-cto-map.css" in html
    assert "leaflet" in html.lower()
    assert "dashboard-tree-panel" in html
    assert "dashboard-metric-pill" in html
    assert ">12<" in html or "12" in html
    assert "CTO" in html
    assert "34" in html
    assert "ONT" in html
