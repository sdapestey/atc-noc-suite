def test_dashboard_altiplano_get_login_page_sin_sesion(client):
    r = client.get("/dashboard/altiplano")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="orquestador-login-form"' in html
    assert "Acceso Orquestador" in html


def test_dashboard_altiplano_get_panel_cuando_hay_sesion(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "tester_inp"
        sess["orquestador_inp_token"] = "dummy-token"

    r = client.get("/dashboard/altiplano")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Crear ONT Connection" in html
    assert "ont-connection" in html
    assert 'id="alt-tab-inp"' in html
    assert 'id="alt-tab-vno"' in html
    assert 'id="alt-vno-tab-tasa"' in html
    assert 'id="alt-vno-tab-directv"' in html
    assert 'id="alt-vno-tab-iplan"' in html
    assert 'id="alt-vno-tab-metrotel"' in html
    assert 'id="alt-vno-tab-sion"' in html
    assert 'id="alt-vno-tab-cambio-cto"' in html
    assert "altiplano-subtab--highlight" in html
    assert "Próximamente." in html
    assert "Próximamente." in html
    assert 'id="sitio"' in html
    assert '<optgroup label="Moreno">' in html
    assert '<option value="MR01_01">MR01_01</option>' in html
    assert '<option value="VL01_03">VL01_03</option>' in html
    assert "Operador" not in html
    assert "Entorno NBI" not in html
    assert 'id="lt" type="text" autocomplete="off"' in html
    assert 'id="pon" type="text" autocomplete="off"' in html
    assert 'id="vno"' in html
    assert '<option value="1001">1001 - TASA</option>' in html
    assert '<option value="3001">3001 - DIRECTV</option>' in html
    assert '<option value="2806">2806 - ATC</option>' in html
    assert "for=\"pir\"" not in html
    assert "for=\"cir\"" not in html
    assert "tester_inp" in html
    assert 'id="btn-orquestador-logout"' in html


def test_dashboard_altiplano_login_ok(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: "fresh-token")

    r = client.post(
        "/dashboard/altiplano/login",
        json={"username": "u_inp", "password": "secret"},
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True

    with client.session_transaction() as sess:
        assert sess.get("orquestador_ok") is True
        assert sess.get("orquestador_user") == "u_inp"
        assert sess.get("orquestador_inp_token") == "fresh-token"


def test_dashboard_altiplano_login_fallo_altiplano(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)

    r = client.post(
        "/dashboard/altiplano/login",
        json={"username": "bad", "password": "bad"},
    )
    assert r.status_code == 401
    payload = r.get_json()
    assert payload["ok"] is False


def test_dashboard_altiplano_logout_limpia_sesion(client):
    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "x"
        sess["orquestador_inp_token"] = "t"

    r = client.post("/dashboard/altiplano/logout")
    assert r.status_code == 200
    with client.session_transaction() as sess:
        assert "orquestador_ok" not in sess
        assert "orquestador_inp_token" not in sess


def test_dashboard_altiplano_ont_connection_missing_field_400(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "device_name": "BA_OLTA_VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "fiber_name": "FIBRA-1",
            # access_id faltante
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "access_id" in payload["message"]


def test_dashboard_altiplano_ont_connection_missing_sitio_400(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
        },
    )
    assert r.status_code == 400
    payload = r.get_json()
    assert payload["ok"] is False
    assert "sitio" in payload["message"]


def test_dashboard_altiplano_ont_connection_sin_sesion_ni_body_401(client):
    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
        },
    )
    assert r.status_code == 401


def test_dashboard_altiplano_ont_connection_success_201(client, monkeypatch):
    import web.routes as routes

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "ONT Connection creada correctamente",
            "target": "BA_OLTA_VL01_01-1-1-66#1001#gpon",
        }

    monkeypatch.setattr(
        routes,
        "crear_ont_connection_intent",
        fake_create,
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_user"] = "sess_u"
        sess["orquestador_inp_token"] = "sess-test-token"

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
            "pir": 9999,
            "cir": 9999,
        },
    )
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["ok"] is True
    assert "target" in payload
    assert captured["entorno_nbi"] == "INP"
    assert captured["device_name"] == "BA_OLTA_VL01_01"
    assert captured["fiber_name"] == "BA_OLTA_VL01_01-1-1"
    assert captured["pir"] == 1000
    assert captured["cir"] == 35
    assert captured["nbi_bearer_token"] == "sess-test-token"


def test_dashboard_altiplano_ont_connection_success_con_credenciales_body(client, monkeypatch):
    """Compatibilidad: sin sesión pero con usuario/contraseña en el JSON (scripts/tests)."""
    import web.routes as routes

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "message": "ONT Connection creada correctamente",
            "target": "x",
        }

    monkeypatch.setattr(routes, "crear_ont_connection_intent", fake_create)

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "METROTEL",
            "sitio": "VL01_01",
            "lt": "1",
            "pon": "1",
            "ont": "66",
            "vno": "1001",
            "access_id": "1051234567",
            "altiplano_user": "user_ui_test",
            "altiplano_password": "pass_ui_test",
        },
    )
    assert r.status_code == 201
    assert captured["nbi_username"] == "user_ui_test"
    assert captured["nbi_password"] == "pass_ui_test"


def test_dashboard_altiplano_ont_connection_upstream_fail_502(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "crear_ont_connection_intent",
        lambda **_kwargs: {
            "ok": False,
            "message": "No se pudo autenticar contra Altiplano",
        },
    )

    with client.session_transaction() as sess:
        sess["orquestador_ok"] = True
        sess["orquestador_inp_token"] = "tok"

    r = client.post(
        "/dashboard/altiplano/ont-connection",
        json={
            "operador": "IPLAN",
            "sitio": "TG01_01",
            "lt": "2",
            "pon": "5",
            "ont": "12",
            "vno": "1001",
            "access_id": "1050000012",
        },
    )
    assert r.status_code == 502
    payload = r.get_json()
    assert payload["ok"] is False
