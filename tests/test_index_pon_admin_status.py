def _mock_altiplano_login_ok(monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: "tok-test")


def test_pon_admin_status_endpoint_success(client, monkeypatch):
    import services.inventory as inventory

    _mock_altiplano_login_ok(monkeypatch)
    monkeypatch.setattr(
        inventory,
        "cambiar_pon_admin_access_id",
        lambda *_a, **_k: {
            "ok": True,
            "message": "PON bloqueado",
            "admin_status": "LOCKED",
            "pon_index": "1",
        },
    )

    r = client.post(
        "/pon/admin-status",
        json={
            "access_id": "1856388788",
            "operador": "TASA",
            "object_name": "BA_OLTA_ES01_01-1-1-4",
            "toggle": True,
            "current_pon_admin": "UNLOCKED",
            "altiplano_user": "noc_user",
            "altiplano_password": "secret",
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["admin_status"] == "LOCKED"


def test_pon_admin_status_endpoint_rechaza_credenciales_invalidas(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(routes, "obtener_token_entorno_nbi", lambda *_a, **_k: None)

    r = client.post(
        "/pon/admin-status",
        json={
            "access_id": "1856388788",
            "operador": "TASA",
            "toggle": True,
            "current_pon_admin": "UNLOCKED",
            "altiplano_user": "bad",
            "altiplano_password": "bad",
        },
    )
    assert r.status_code == 401
    assert "incorrectos" in (r.get_json() or {}).get("message", "")
