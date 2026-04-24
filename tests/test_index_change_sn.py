def _mock_access_result_bajada():
    return {
        "AID": "105",
        "OPERADOR": "TASA",
        "Status": "IN SERVICE",
        "CTO": "TG01-FATC-8-100987",
        "RAMA": "TG01-RATC-0-000308",
        "ONT": "BA_OLTA_TG01_02-2-15-8",
        "SN": "ALCLF0000001",
        "TX": None,
        "RX": None,
        "fuente_detalle": "bajada_inventario",
    }


def test_index_access_id_bajada_muestra_cambiar_sn(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda _aid: _mock_access_result_bajada(),
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "105"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="btn-cambiar-sn"' in html
    assert 'onclick="cambiarSNDesdeUIBtn(this)"' in html


def test_cambiar_sn_endpoint_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "cambiar_sn_ont",
        lambda **_kwargs: {"ok": True, "message": "SN actualizado correctamente", "sn": "ALCLF0000002"},
    )

    r = client.post(
        "/sn/cambiar",
        json={
            "access_id": "105",
            "operador": "TASA",
            "ont_target": "BA_OLTA_TG01_02-2-15-8",
            "new_sn": "ALCLF0000002",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["sn"] == "ALCLF0000002"


def test_cambiar_sn_endpoint_error_from_altiplano(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "cambiar_sn_ont",
        lambda **_kwargs: {"ok": False, "message": "Altiplano rechazó la operación"},
    )

    r = client.post(
        "/sn/cambiar",
        json={
            "access_id": "105",
            "operador": "TASA",
            "ont_target": "BA_OLTA_TG01_02-2-15-8",
            "new_sn": "ALCLF0000002",
        },
    )
    assert r.status_code == 502
    payload = r.get_json()
    assert payload["ok"] is False
    assert "Altiplano" in payload["message"]


def test_cambiar_sn_endpoint_validates_sn(client):
    r = client.post(
        "/sn/cambiar",
        json={
            "access_id": "105",
            "operador": "TASA",
            "ont_target": "BA_OLTA_TG01_02-2-15-8",
            "new_sn": " A ",
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "SN inválido" in payload["message"]
