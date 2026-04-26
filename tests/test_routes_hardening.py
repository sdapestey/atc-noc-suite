def test_api_historico_internal_error_returns_request_id(client, monkeypatch):
    import web.routes as routes

    def _boom(_ratc, days=30):
        raise RuntimeError("db failure")

    monkeypatch.setattr(routes, "consultar_potencias_historico_rama", _boom)
    resp = client.get("/api/potencias-historico/MR01-RATC-0-000200")
    assert resp.status_code == 500
    payload = resp.get_json()
    assert payload["error"] == "Error interno consultando historico de potencias"
    assert isinstance(payload.get("request_id"), str)
    assert payload["request_id"]

