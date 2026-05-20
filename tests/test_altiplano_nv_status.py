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
