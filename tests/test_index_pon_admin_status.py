def _mock_altiplano_env_creds(monkeypatch, user="noc_user", password="secret"):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "_altiplano_creds_from_env",
        lambda _entorno: (user, password, None),
    )


def test_pon_admin_status_endpoint_success(client, monkeypatch):
    import services.inventory as inventory

    _mock_altiplano_env_creds(monkeypatch)
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
        },
    )
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["admin_status"] == "LOCKED"


def test_pon_admin_status_endpoint_sin_credenciales_env(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "_altiplano_creds_from_env",
        lambda _entorno: (
            "",
            "",
            ({"ok": False, "message": "Credenciales Altiplano no configuradas en .env"}, 503),
        ),
    )

    r = client.post(
        "/pon/admin-status",
        json={
            "access_id": "1856388788",
            "operador": "TASA",
            "toggle": True,
            "current_pon_admin": "UNLOCKED",
        },
    )
    assert r.status_code == 503
    assert ".env" in (r.get_json() or {}).get("message", "")
