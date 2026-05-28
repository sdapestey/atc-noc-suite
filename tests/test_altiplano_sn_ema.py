def test_sn_from_ema_entity_body_rechaza_placeholder_undefined():
    import altiplano

    body = {
        "extraAttributes": {
            "expected-serial-number": {"className": "Undefined"},
            "detected-serial-number": "ASKY00866826",
        }
    }
    assert altiplano._sn_from_ema_entity_body(body) == "ASKY00866826"


def test_sn_expected_from_ema_entity_body_solo_expected():
    import altiplano

    body = {
        "extraAttributes": {
            "expected-serial-number": {"className": "Undefined"},
            "detected-serial-number": "ASKY00866826",
        }
    }
    assert altiplano._sn_expected_from_ema_entity_body(body) is None
    assert altiplano._sn_from_ema_entity_body(body) == "ASKY00866826"


def test_sn_expected_from_ont_intent_body():
    import altiplano

    body = {
        "ibn:intent": {
            "intent-specific-data": {
                "ont:ont": {
                    "expected-serial-number": "ASKY008DEDE9",
                    "ont-state": {"detected-serial-number": "ASKY00866826"},
                }
            }
        }
    }
    assert altiplano._sn_expected_from_ont_intent_body(body) == "ASKY008DEDE9"


def test_fetch_ont_telemetry_usa_intent_cuando_ema_expected_undefined(monkeypatch):
    import altiplano

    def fake_http(url, auth_url, **kwargs):
        label = kwargs.get("log_label", "")
        if "ONT intent expected SN" in label:
            return {
                "ibn:intent": {
                    "intent-specific-data": {
                        "ont:ont": {"expected-serial-number": "ASKY008DEDE9"}
                    }
                }
            }
        if "RESTCONF" in label:
            return {
                "bbf-hardware-transceivers-mounted:diagnostics": {
                    "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": 25,
                    "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -181,
                }
            }
        return {
            "extraAttributes": {
                "expected-serial-number": {"className": "Undefined"},
                "detected-serial-number": "ALCL00101001",
            }
        }

    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)
    monkeypatch.setattr(altiplano, "_http_get_ema_entity_try_versions", lambda *a, **k: fake_http("", "", log_label=k.get("log_label", "")))
    monkeypatch.setattr(altiplano, "_fetch_intent_health_inp", lambda *a, **k: {})
    monkeypatch.setattr(altiplano, "_fetch_ema_oper_admin_inp", lambda *a, **k: {})
    monkeypatch.setattr(altiplano, "_fetch_channel_partition_admin_inp", lambda *a, **k: {})

    out = altiplano.obtener_telemetry_ont(
        "1059381064",
        "BA_OLTA_TG01_03-1-1-1",
        1001,
        ne="BA_OLTA_TG01_03.LT1",
    )
    assert out["sn"] == "ASKY008DEDE9"


def test_sn_from_ema_entity_body_prioriza_expected_serial_number():
    import altiplano

    body = {
        "extraAttributes": {
            "detected-serial-number": "ASKY00866826",
            "expected-serial-number": "ASKY00866827",
            "serialNumber": "legacy",
        }
    }
    assert altiplano._sn_from_ema_entity_body(body) == "ASKY00866827"


def test_obtener_telemetry_ont_incluye_sn_desde_ema(monkeypatch):
    import altiplano

    calls = []

    def fake_http(url, auth_url, **kwargs):
        calls.append(kwargs.get("log_label", ""))
        if "RESTCONF" in kwargs.get("log_label", ""):
            return {
                "bbf-hardware-transceivers-mounted:diagnostics": {
                    "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": 22,
                    "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -205,
                }
            }
        return {
            "extraAttributes": {
                "expected-serial-number": "ASKY00866827",
                "detected-serial-number": "ASKY00866826",
                "tx-signal-level": "22",
                "rx-signal-level-ont": "-205",
            }
        }

    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)

    out = altiplano.obtener_telemetry_ont(
        "1058443222",
        "BA_OLTA_SF01_04:1-1-7-1-5",
        1001,
        ne="BA_OLTA_SF01_04.LT7",
    )
    assert out["tx"] == 2.2
    assert out["rx"] == -20.5
    assert out["sn"] == "ASKY00866827"
    assert any("EMA" in c for c in calls)
