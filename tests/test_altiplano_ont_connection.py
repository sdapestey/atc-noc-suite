def test_crear_ont_connection_intent_ok_201(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "tasa-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    captured = {}

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers

        class R:
            status_code = 201

            @staticmethod
            def json():
                return {"ok": True}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
        pir=1000,
        cir=35,
    )
    assert out["ok"] is True
    assert out["status_code"] == 201
    assert out["target"] == "BA_OLTA_VL01_01-1-2-66#1001#gpon"
    assert "rest/restconf/data/ibn:ibn" in captured["url"]
    payload = captured["json"]["ibn:intent"]
    assert payload["intent-type"] == "ont-connection"
    assert payload["intent-specific-data"]["ont-connection:ont-connection"]["access-id"] == "1051234567"


def test_crear_ont_connection_intent_login_fail(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "tasa-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: None)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
    )
    assert out["ok"] is False
    assert "autenticar" in out["message"].lower()


def test_crear_ont_connection_intent_api_fail(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "tasa-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    def fake_post(_url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 500

            @staticmethod
            def json():
                return {"error-message": "boom"}

            text = "boom"

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
    )
    assert out["ok"] is False
    assert "rechaz" in out["message"].lower() or "http" in out["message"].lower()


def test_crear_ont_connection_intent_usa_bearer_sin_login(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "_obtener_token",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no debería llamar login")),
    )

    captured = {}

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        captured["auth"] = (headers or {}).get("Authorization", "")
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_X",
        lt="1",
        pon="1",
        ont="1",
        vno="1001",
        fiber_name="BA_OLTA_X-1-1",
        access_id="1",
        nbi_bearer_token="tok-ui",
    )
    assert out["ok"] is True
    assert "Bearer tok-ui" in captured["auth"]


def test_crear_ont_connection_intent_prefiere_credenciales_ui(monkeypatch):
    import altiplano

    env_calls = []

    def fake_env_cred(_op):
        env_calls.append(_op)
        return ("env_u", "env_p")

    tok_calls = []

    def fake_token(auth_url, username=None, password=None, force_refresh=False):
        tok_calls.append((username, password, force_refresh))
        return "fake-token"

    monkeypatch.setattr(altiplano, "get_altiplano_nbi_target", lambda _k: ("10.0.0.1", "32443", "inp-altiplano-ac"))
    monkeypatch.setattr(altiplano, "get_altiplano_operator_credentials", fake_env_cred)
    monkeypatch.setattr(altiplano, "_obtener_token", fake_token)

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_ES01_01",
        lt="1",
        pon="1",
        ont="59",
        vno="1001",
        fiber_name="BA_OLTA_ES01_01-1-1",
        access_id="prueba",
        nbi_username="ui_u",
        nbi_password="ui_p",
    )
    assert out["ok"] is True
    assert env_calls == []
    assert tok_calls and tok_calls[0][0] == "ui_u" and tok_calls[0][1] == "ui_p"


def test_crear_ont_connection_intent_uses_nbi_environment_not_operator(monkeypatch):
    import altiplano

    calls = {}

    def fake_target(key):
        calls["key"] = key
        return ("10.0.0.9", "32443", "inp-altiplano-ac")

    monkeypatch.setattr(altiplano, "get_altiplano_nbi_target", fake_target)
    monkeypatch.setattr(altiplano, "get_altiplano_operator_credentials", lambda _op: ("u", "p"))
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_ES01_01",
        lt="1",
        pon="1",
        ont="59",
        vno="1001",
        fiber_name="BA_OLTA_ES01_01-1-1",
        access_id="prueba",
    )
    assert out["ok"] is True
    assert calls["key"] == "INP"
