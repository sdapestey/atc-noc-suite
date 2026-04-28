"""Consulta índice con varios tokens separados por coma."""

def test_index_multiple_access_ids_two_sections(client, monkeypatch):
    import web.routes as routes

    def fake_detalle(aid):
        base = {
            "OPERADOR": "TASA",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-100987",
            "RAMA": "TG01-RATC-0-000308",
            "ONT": "BA_OLTA_TG01_02-2-15-8",
            "SN": "04EDFBADD5F81",
            "TX": None,
            "RX": None,
            "fuente_detalle": "bajada_inventario",
        }
        if aid == "105":
            return {**base, "AID": "105"}
        if aid == "106":
            return {**base, "AID": "106"}
        return None

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", fake_detalle)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "105, 106"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-query-token="105"' in html
    assert 'data-query-token="106"' in html
    assert "<th>Estado</th><td id=\"s0-estado-id\"" in html
    assert "<th>Estado</th><td id=\"s1-estado-id\"" in html


def test_index_comma_only_shows_hint(client):
    r = client.post("/", data={"value": ", ,"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "No se interpretó ningún término" in html
