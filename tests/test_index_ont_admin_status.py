def test_cambiar_admin_status_ont_post_ema(monkeypatch):
    import altiplano

    captured = {}

    def fake_post(url, auth_url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(altiplano, "_http_post_altiplano_expect_ok", fake_post)
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )

    out = altiplano.cambiar_admin_status_ont(
        "1058443222",
        "BA_OLTA_SF01_04:1-1-7-1-5",
        "TASA",
        "LOCKED",
    )
    assert out["ok"] is True
    assert captured["payload"] == {"adminStatus": "LOCKED"}
    assert "ema/entity" in captured["url"]
    assert "v1~BA_OLTA_SF01_04-7-1-5_GPON" in captured["url"]


def _mock_altiplano_login_ok(monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-test")


def test_ont_admin_status_endpoint_success(client, monkeypatch):
    import web.routes as routes

    _mock_altiplano_login_ok(monkeypatch)
    monkeypatch.setattr(
        routes,
        "cambiar_admin_status_access_id",
        lambda *_a, **_k: {
            "ok": True,
            "message": "ONT locked correctamente en Altiplano",
            "admin_status": "LOCKED",
        },
    )

    r = client.post(
        "/ont/admin-status",
        json={
            "access_id": "1058443222",
            "operador": "TASA",
            "object_name": "BA_OLTA_SF01_04-7-1-5",
            "toggle": True,
            "current_admin": "UNLOCKED",
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    assert r.get_json()["admin_status"] == "LOCKED"


def test_ont_admin_status_endpoint_toggle_locked_to_unlocked(client, monkeypatch):
    import web.routes as routes

    _mock_altiplano_login_ok(monkeypatch)
    seen = {}

    def fake(aid, op, status, **kwargs):
        seen["status"] = status
        return {"ok": True, "admin_status": status}

    monkeypatch.setattr(routes, "cambiar_admin_status_access_id", fake)

    r = client.post(
        "/ont/admin-status",
        json={
            "access_id": "1",
            "operador": "TASA",
            "toggle": True,
            "current_admin": "LOCKED",
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    assert seen["status"] == "UNLOCKED"


def test_ont_admin_status_endpoint_rechaza_credenciales_invalidas(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)

    r = client.post(
        "/ont/admin-status",
        json={
            "access_id": "1",
            "operador": "TASA",
            "toggle": True,
            "current_admin": "UNLOCKED",
            "altiplano_user": "bad",
            "altiplano_password": "bad",
        },
    )
    assert r.status_code == 401
    assert "incorrectos" in (r.get_json() or {}).get("message", "")
