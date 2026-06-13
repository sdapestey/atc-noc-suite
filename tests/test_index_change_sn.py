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
    assert 'class="btn-mini consulta-sn-btn"' in html
    assert 'onclick="cambiarSNDesdeUIBtn(this)"' in html


def _mock_altiplano_login_ok(monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-test")


def test_cambiar_sn_endpoint_success(client, monkeypatch):
    import web.routes as routes

    _mock_altiplano_login_ok(monkeypatch)
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
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["sn"] == "ALCLF0000002"


def test_cambiar_sn_endpoint_error_from_altiplano(client, monkeypatch):
    import web.routes as routes

    _mock_altiplano_login_ok(monkeypatch)
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
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
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
            "altiplano_user": "u",
            "altiplano_password": "p",
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "SN inválido" in payload["message"]


def test_consulta_altiplano_validate_ok(client, monkeypatch):
    _mock_altiplano_login_ok(monkeypatch)
    r = client.post(
        "/consulta/altiplano/validate",
        json={
            "operador": "TASA",
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    assert (r.get_json() or {}).get("ok") is True


def test_consulta_altiplano_validate_rechaza_credenciales(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)
    r = client.post(
        "/consulta/altiplano/validate",
        json={
            "operador": "TASA",
            "altiplano_user": "bad",
            "altiplano_password": "bad",
        },
    )
    assert r.status_code == 401


def test_cambiar_sn_endpoint_rechaza_credenciales_invalidas(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)

    r = client.post(
        "/sn/cambiar",
        json={
            "access_id": "105",
            "operador": "TASA",
            "ont_target": "BA_OLTA_TG01_02-2-15-8",
            "new_sn": "ALCLF0000002",
            "altiplano_user": "bad",
            "altiplano_password": "bad",
        },
    )
    assert r.status_code == 401
    assert "incorrectos" in (r.get_json() or {}).get("message", "")


def test_index_template_incluye_dialogo_altiplano_auth(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_access_id_detalle_desde_bajada_inventario",
        lambda _aid: _mock_access_result_bajada(),
    )
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post("/", data={"value": "105"})
    html = r.get_data(as_text=True)
    assert "consulta-altiplano-auth-dialog" in html
    assert "consulta-sn-change-dialog" in html
    assert "consulta-altiplano-auth.js" in html
    assert "altiplanoAuthCacheSeconds" in html
