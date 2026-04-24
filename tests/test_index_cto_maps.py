from urllib.parse import quote_plus


def _mock_cto_rows():
    return [
        {
            "AID": "1",
            "OPERADOR": "TASA",
            "RAMA": "TG01-RATC-0-000001",
            "PRINCIPAL": "Tigre",
            "ONT": "ONT-1",
            "STATUS": "IN SERVICE",
            "TX": None,
            "RX": None,
        }
    ]


def test_index_cto_shows_google_maps_link_when_coords_exist(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_cto_estructura", lambda _cto: _mock_cto_rows())
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: {"lat": -34.429816, "lon": -58.661158})

    r = client.post("/", data={"value": "TG01-FATC-8-601814"})
    assert r.status_code == 200

    html = r.get_data(as_text=True)
    expected_query = quote_plus("-34.429816,-58.661158")
    expected_href = f"https://www.google.com/maps/search/?api=1&amp;query={expected_query}"
    assert "CTO consultada" in html
    assert "Ver en Google Maps" in html
    assert expected_href in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_index_cto_shows_no_coords_when_missing(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_cto_estructura", lambda _cto: _mock_cto_rows())
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "TG01-FATC-8-601814"})
    assert r.status_code == 200

    html = r.get_data(as_text=True)
    assert "CTO consultada" in html
    assert "Sin coordenadas" in html
    assert "Ver en Google Maps" not in html
