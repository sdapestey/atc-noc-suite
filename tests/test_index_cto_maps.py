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


def test_consulta_index_map_delegates_cto_marker_wiring_to_noc_maps():
    from pathlib import Path

    js = Path("static/js/consulta-index-map.js").read_text(encoding="utf-8")
    assert "__CONSULTA_MAP_BUILD__" in js
    assert "wireConsultaCtoMarker" in js
    assert "NocMaps.wireCtoCircleMarker" in js
    assert "NocMaps.wireCtoAddressPrefetch" in js
    assert "NocMaps.ctoPopupHtml" in js
    assert 'toastId: "toast"' in js
    assert "bindPopup" not in js
    assert "copyCoordsToClipboard" not in js


def test_index_cto_renders_cto_head_and_embedded_map_when_coords_exist(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_cto_estructura", lambda _cto: _mock_cto_rows())
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: {"lat": -34.429816, "lon": -58.661158})
    monkeypatch.setattr(routes, "consultar_cto_coordenadas_desde_sfat", lambda _cto: None)
    monkeypatch.setattr(routes, "consultar_cto_direccion_postal", lambda _cto: "Alvear 2464 (BA San Fernando)")

    r = client.post("/", data={"value": "TG01-FATC-8-601814"})
    assert r.status_code == 200

    html = r.get_data(as_text=True)
    assert "Sitio principal" in html
    assert "consulta-cto-ficha" in html
    assert "consulta-cto-ficha__row" in html
    assert html.index("Sitio principal") < html.index("Dirección")
    assert html.index("RAMA (path ATC)") < html.index("Dirección")
    assert "consulta-ubicacion-card" not in html
    assert "Ver en Google Maps" not in html
    assert "Google Maps" not in html
    assert "consulta-cto-head-row" in html
    assert "rama-row-kind--cto" in html
    assert "TG01-FATC-8-601814" in html
    assert "Ubicación (CTO)" in html
    assert "consulta-cto-ficha__value" in html
    assert "Alvear 2464 (BA San Fernando)" in html
    assert "data-consulta-cto-map" in html
    assert "noc-map-tiles.js" in html
    assert "noc-tools.js" in html
    assert html.index("noc-tools.js") < html.index("consulta-index-map.js")
    assert "consulta-index-map.js" in html


def test_index_cto_shows_no_coords_when_missing(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_cto_estructura", lambda _cto: _mock_cto_rows())
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas_desde_sfat", lambda _cto: None)
    monkeypatch.setattr(routes, "consultar_cto_direccion_postal", lambda _cto: None)

    r = client.post("/", data={"value": "TG01-FATC-8-601814"})
    assert r.status_code == 200

    html = r.get_data(as_text=True)
    assert "Sitio principal" in html
    assert "consulta-cto-head-row" in html
    assert "Google Maps" not in html
    assert "consulta-cto-no-ext-maps" not in html
    assert "Ver en Google Maps" not in html
    assert "Dirección:" not in html
    assert "data-consulta-cto-postal-fetch" in html
    assert "Buscando dirección" in html
    assert "data-consulta-cto-map" in html


def test_index_cto_search_no_ver_mapa_beside_rama_in_breadcrumb(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "consultar_cto_estructura", lambda _cto: _mock_cto_rows())
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas_desde_sfat", lambda _cto: None)
    monkeypatch.setattr(routes, "consultar_cto_direccion_postal", lambda _cto: None)

    r = client.post("/", data={"value": "TG01-FATC-8-601814"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "consultaToggleMapaRama" not in html
    assert "panel-mapa-rama" not in html
    assert "/dashboard/potencias-historico?ratc=" not in html
