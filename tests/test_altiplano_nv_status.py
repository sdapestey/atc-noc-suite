def test_ont_connection_full_target_from_inventory_object():
    import altiplano

    assert (
        altiplano._ont_connection_full_target("BA_OLTA_SF01_04:1-1-7-1-5", 1001)
        == "BA_OLTA_SF01_04-7-1-5#1001#gpon"
    )


def test_ema_top_level_state():
    import altiplano

    body = {"operationState": "DOWN", "adminStatus": "UNLOCKED"}
    assert altiplano._ema_top_level_state(body, "operationState") == "DOWN"
    assert altiplano._ema_top_level_state(body, "adminStatus") == "UNLOCKED"


def test_ema_onu_gpon_name_candidates_v7_before_v1():
    import altiplano

    names = altiplano._ema_onu_gpon_name_candidates("BA_OLTA_SF01_01-2-1-35")
    assert names[0] == "v7~BA_OLTA_SF01_01-2-1-35_GPON"
    assert names[1] == "v1~BA_OLTA_SF01_01-2-1-35_GPON"


def test_ema_state_from_body_nested():
    import altiplano

    body = {
        "extraAttributes": {"tx-signal-level": 26},
        "device": {"operationState": "UP", "adminStatus": "LOCKED"},
    }
    assert altiplano._ema_state_from_body(body, "operationState") == "UP"
    assert altiplano._ema_state_from_body(body, "adminStatus") == "LOCKED"


def test_fetch_ont_telemetry_fills_oper_admin_via_inp_ema(monkeypatch):
    """Si el AC del VNO no devuelve oper/admin, se consulta EMA INP (p. ej. DIRECTV)."""
    import altiplano

    inp_calls = []

    def fake_get(url, auth_url, **kwargs):
        if "inp-altiplano-ac/rest/ema/entity" in url:
            inp_calls.append(url)
            if "v1~" in url:
                return None
            if "fetchDeviceAttributes=false" in url and "isOne=false" in url:
                return {"adminStatus": "UNLOCKED"}
            if "fetchDeviceAttributes=true" in url and "isOne=true" in url:
                return {"operationState": "UP"}
        if "dtv-altiplano-ac" in url and "ema/entity" in url:
            return {"extraAttributes": {"tx-signal-level": 26, "rx-signal-level-ont": -164}}
        return None

    monkeypatch.setattr(
        altiplano,
        "_power_auth_contexts",
        lambda _op: [
            ("dtv", "https://10.200.7.107:32443/dtv-altiplano-ac/rest/auth/login", "u", "p"),
        ],
    )
    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_get)
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda op: ("10.200.3.100", "32443", "inp-altiplano-ac")
        if op == "INP"
        else ("10.200.7.107", "32443", "dtv-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "_inp_ema_credentials",
        lambda _op: ("inp_user", "inp_pwd"),
    )
    monkeypatch.setattr(altiplano, "_fetch_intent_health_inp", lambda *a, **k: {})

    out = altiplano._fetch_ont_telemetry_live(
        "126696694", "BA_OLTA_SF01_01-2-1-35", 3001, "BA_OLTA_SF01_01.LT2"
    )
    assert out["tx"] is not None
    assert out["rx"] is not None
    assert out["oper"] == "UP"
    assert out["admin"] == "UNLOCKED"
    assert any("inp-altiplano-ac/rest/ema/entity" in u for u in inp_calls)
    assert any("v7~BA_OLTA_SF01_01-2-1-35_GPON" in u for u in inp_calls)


def test_nv_health_display_timestamp_prefers_onu_detected_when_newer():
    import altiplano

    ts = altiplano._nv_health_display_timestamp(
        "2026-05-19T02:00:00+00:00",
        "2026-05-19T08:29:04-03:00",
        oper="UP",
        health="healthy",
    )
    assert ts == "2026-05-19T08:29:04-03:00"


def test_nv_health_display_timestamp_oper_up_sin_health_usa_onu_detected():
    import altiplano

    ts = altiplano._nv_health_display_timestamp(
        "2026-05-06T10:00:00+00:00",
        "2026-05-19T08:29:04-03:00",
        oper="UP",
        health=None,
    )
    assert ts == "2026-05-19T08:29:04-03:00"


def test_fetch_intent_health_inp_por_access_id_sin_target_exacto(monkeypatch):
    """Si el target inventario difiere del intent, igual tomar health por Access ID (GUI)."""
    import altiplano

    search_payload = {
        "ibn:output": {
            "intents": [
                {
                    "intent-type": "ont-connection",
                    "target": "BA_OLTA_ES01_01-1-1-2#1001#gpon",
                    "health": "healthy",
                    "health-last-updated-timestamp": "2026-05-19T08:23:00+00:00",
                    "intent-specific-data": {
                        "ont-connection:ont-connection": {
                            "access-id": "1056380708",
                        }
                    },
                }
            ]
        }
    }

    import json as _json

    class FakeSearchRes:
        status_code = 200
        text = _json.dumps(search_payload)

        @staticmethod
        def json():
            return search_payload

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("h", "1", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "tok")
    monkeypatch.setattr(altiplano.requests, "post", lambda *a, **k: FakeSearchRes())
    monkeypatch.setattr(
        altiplano,
        "_http_get_altiplano_json",
        lambda *a, **k: None,
    )

    out = altiplano._fetch_intent_health_inp(
        "1056380708",
        "BA_OLTA_ES01_01-9-9-9#9999#gpon",
        username="u",
        password="p",
    )
    assert out["health"] == "healthy"
    assert "2026-05-19T08:23:00" in (out["health_ts"] or "")


def test_normalize_altiplano_iso8601_for_js():
    import altiplano

    assert (
        altiplano._normalize_altiplano_iso8601_for_js("2026-05-19T02:00:00+0000")
        == "2026-05-19T02:00:00+00:00"
    )


def test_deep_find_intent_health_fields():
    import altiplano

    body = {
        "ibn:intent": {
            "intent-health": "Faulty",
            "intent-health-last-updated-timestamp": "2026-05-19T00:40:00.000Z",
        }
    }
    found = altiplano._deep_find_intent_health_fields(body)
    assert found["health"] == "Faulty"
    assert "2026-05-19" in found["health_ts"]


def test_fetch_ont_telemetry_includes_oper_admin(monkeypatch):
    import altiplano

    calls = []

    def fake_get(url, auth_url, **kwargs):
        calls.append(url)
        if "fetchDeviceAttributes=false" in url and "isOne=false" in url:
            return {"adminStatus": "UNLOCKED"}
        if "search-intents" in url:
            return None
        if "ema/entity" in url:
            return {
                "operationState": "UP",
                "extraAttributes": {
                    "tx-signal-level": 21,
                    "rx-signal-level-ont": -205,
                    "expected-serial-number": "ASKY00866826",
                    "onu-detected-datetime": "2026-05-19T08:29:04-03:00",
                },
            }
        if "restconf/data/ibn:ibn/intent=" in url:
            return {
                "ibn:intent": {
                    "intent-health": "Faulty",
                    "intent-health-last-updated-timestamp": "2026-05-19T00:40:00Z",
                }
            }
        return None

    monkeypatch.setattr(
        altiplano,
        "_power_auth_contexts",
        lambda _op: [("inp", "https://h:1/inp-altiplano-ac/rest/auth/login", "u", "p")],
    )
    search_payload = {
        "ibn:output": {
            "intents": [
                {
                    "intent-type": "ont-connection",
                    "target": "BA_OLTA_SF01_04-7-1-5#1001#gpon",
                    "health": "healthy",
                    "health-last-updated-timestamp": "2026-05-19T02:00:00+00:00",
                    "intent-specific-data": {
                        "ont-connection:ont-connection": {
                            "access-id": "1058443222",
                        }
                    },
                }
            ]
        }
    }

    class FakeSearchRes:
        status_code = 200
        text = __import__("json").dumps(search_payload)

        @staticmethod
        def json():
            return search_payload

    def fake_requests_post(url, **kwargs):
        if "search-intents" in url:
            return FakeSearchRes()
        return FakeSearchRes()

    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_get)
    monkeypatch.setattr(altiplano.requests, "post", fake_requests_post)
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("h", "1", "inp-altiplano-ac"),
    )

    out = altiplano._fetch_ont_telemetry_live(
        "1058443222", "BA_OLTA_SF01_04:1-1-7-1-5", 1001, "BA_OLTA_SF01_04.LT7"
    )
    assert out["oper"] == "UP"
    assert out["admin"] == "UNLOCKED"
    assert out["health"] == "healthy"
    assert out["health_ts"] == "2026-05-19T08:29:04-03:00"
    assert out["sn"] == "ASKY00866826"
