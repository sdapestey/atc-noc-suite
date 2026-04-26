"""Smoke del template dashboard RAMA (toolbar CTO / sin expandir todo)."""


def _minimal_ramas():
    return [
        {
            "PRINCIPAL": "SitioTest",
            "SEARCH_TEXT": "sitiottest r1 c1",
            "RAMAS": [
                {
                    "RAMA": "R1-RATC",
                    "CTOS": {
                        "C1-FATC": [
                            {"AID": "100", "OPERADOR": "TASA", "ONT": "ONT-1", "TX": None, "RX": None},
                        ],
                    },
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

    monkeypatch.setattr(routes, "dashboard_ramas", lambda: _minimal_ramas())
    r = client.get("/dashboard/rama")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Expandir todo" not in html
    assert "Colapsar todo" in html
    assert "Copiar CTO seleccionadas" in html
    assert "Exportar CTO seleccionadas CSV" in html
    assert 'class="cto-select"' in html
    assert "cto-select-all-in-rama" in html
    assert "Seleccionar todas las CTO de esta RAMA" in html
    assert "Ver historico" in html
    assert "_rowsCtosSeleccionados" in html or "copiarCtosSeleccionadas" in html
