def test_ne_from_object_name_ba_olta_con_guiones_en_nombre():
    import altiplano

    assert (
        altiplano._ne_from_object_name_raw("BA_OLTA_ES01_01-1-1-4")
        == "BA_OLTA_ES01_01.LT1"
    )
    assert (
        altiplano._ne_from_object_name_raw("BA_OLTA_ES01_01:1-1-1-4")
        == "BA_OLTA_ES01_01.LT1"
    )


def test_build_alarmas_activas_search_query_incluye_interface_y_onu():
    import altiplano

    q = altiplano._build_alarmas_activas_search_query(
        "BA_OLTA_SF01_04.LT7", "BA_OLTA_SF01_04:1-1-7-1-5"
    )
    assert q is not None
    must = q["query"]["bool"]["must"]
    should_paths = must[1]["bool"]["should"]
    raw_paths = [
        s["match"]["alarmResource.raw"]
        for s in should_paths
        if "match" in s and "alarmResource.raw" in s["match"]
    ]
    assert any("interface=v1~BA_OLTA_SF01_04-7-1-5_GPON" in p for p in raw_paths)
    assert any("onus/onu=v1~BA_OLTA_SF01_04-7-1-5_GPON" in p for p in raw_paths)
    assert any("component=CHASSIS" in p for p in raw_paths)
    assert must[0]["bool"]["should"][0]["term"]["alarmStatus"] == "Active"
    should_all = must[1]["bool"]["should"]
    assert any("wildcard" in s for s in should_all)


def test_build_alarmas_activas_search_query_incluye_variantes_v2():
    import altiplano

    q = altiplano._build_alarmas_activas_search_query(
        "BA_OLTA_SF01_01.LT8", "BA_OLTA_SF01_01-8-12-1"
    )
    assert q is not None
    should_paths = q["query"]["bool"]["must"][1]["bool"]["should"]
    wild_raw = [
        s["wildcard"]["alarmResource.raw"]
        for s in should_paths
        if "wildcard" in s and "alarmResource.raw" in s["wildcard"]
    ]
    assert any("v1~BA_OLTA_SF01_01-8-12-1_GPON" in p for p in wild_raw)
    assert any("v2~BA_OLTA_SF01_01-8-12-1_GPON" in p for p in wild_raw)
    assert any("v7~BA_OLTA_SF01_01-8-12-1_GPON" in p for p in wild_raw)
    assert any(p == "*BA_OLTA_SF01_01-8-12-1*" for p in wild_raw)


def test_build_alarmas_activas_search_query_incluye_v7_gpon():
    import altiplano

    suffixes = altiplano._ont_gpon_interface_suffixes("BA_OLTA_TG02_02-10-6-22")
    assert "v7~BA_OLTA_TG02_02-10-6-22_GPON" in suffixes


def test_parse_alarmas_activas_search_body():
    import altiplano

    body = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "alarmStatus": "Active",
                        "alarmSeverity": "major",
                        "alarmType": "absence-of-phy",
                        "raisedTime": "2026-05-19T00:40:18.000Z",
                        "alarmResourceUiName": "interface:BA_OLTA_SF01_04.LT7:v1~BA_OLTA_SF01_04-7-1-5_GPON",
                        "alarmText": "Serial-Number=ASKY00866827",
                        "mainDeviceRefId": "BA_OLTA_SF01_04",
                        "proposedRepairAction": "Check physical connectivity between ONU and OLT.",
                        "serviceAffecting": "SA_SERVICE_AFFECTING",
                    }
                },
                {
                    "_source": {
                        "alarmStatus": "Cleared",
                        "alarmType": "ignored",
                    }
                },
            ]
        }
    }
    out = altiplano._parse_alarmas_activas_search_body(body)
    assert len(out) == 1
    assert out[0]["type"] == "absence-of-phy"
    assert out[0]["severity"] == "major"
    assert out[0]["main_device"] == "BA_OLTA_SF01_04"
    assert "connectivity" in out[0]["repair"]
    assert out[0]["cleared"] == ""


def test_obtener_alarmas_ont_activas_post_inp(monkeypatch):
    import altiplano

    captured = {}

    def fake_post(url, auth_url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        return {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "alarmStatus": "Active",
                            "alarmSeverity": "major",
                            "alarmType": "absence-of-phy",
                            "raisedTime": "2026-05-19T00:40:18.000Z",
                            "alarmResourceUiName": "interface:BA_OLTA_SF01_04.LT7:v1~X_GPON",
                            "alarmText": "",
                        }
                    }
                ]
            }
        }

    monkeypatch.setattr(altiplano, "_http_post_altiplano_json", fake_post)
    monkeypatch.setattr(
        altiplano,
        "_inp_alarm_search_url",
        lambda: (
            "https://10.200.3.100:32443/inp-altiplano-ac/rest/alarm/alarms/search?index=alarms-active",
            "https://10.200.3.100:32443/inp-altiplano-ac/rest/auth/login",
            "u",
            "p",
        ),
    )

    out = altiplano.obtener_alarmas_ont_activas(
        "1058443222", "BA_OLTA_SF01_04:1-1-7-1-5", 1001, ne="BA_OLTA_SF01_04.LT7"
    )
    assert len(out) == 1
    assert "alarms/search" in captured["url"]
    assert captured["payload"]["query"]["bool"]["must"]


def test_consultar_access_id_potencias_sin_lectura_incluye_alarmas(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {
            "AID": "1058443222",
            "Status": "IN SERVICE",
            "CTO": "SF01-FATC-8-203376",
        },
    )
    monkeypatch.setattr(
        inv,
        "_resolver_object_name_operator_potencias",
        lambda *_a, **_k: ("BA_OLTA_SF01_04:1-1-7-1-5", 1001),
    )
    monkeypatch.setattr(
        inv,
        "obtener_telemetry_ont",
        lambda *_a, **_k: {
            "tx": None,
            "rx": None,
            "sn": "ASKY00866826",
            "oper": "DOWN",
            "admin": "UNLOCKED",
            "health": "Faulty",
            "health_ts": "2026-05-19T00:40:00Z",
        },
    )
    monkeypatch.setattr(
        inv,
        "obtener_alarmas_ont_activas",
        lambda *_a, **_k: [
            {
                "severity": "major",
                "type": "absence-of-phy",
                "raised": "2026-05-19T00:40:18.000Z",
                "resource": "interface:BA_OLTA_SF01_04.LT7:v1~BA_OLTA_SF01_04-7-1-5_GPON",
                    "text": "Serial-Number=ASKY00866826",
            }
        ],
    )

    out = inv.consultar_access_id_potencias("1058443222")
    assert out["TX"] is None
    assert len(out["ALARMAS"]) == 1
    assert out["alarmas_label"] is None
    assert out["NV_STATUS"]["oper"] == "DOWN"
    assert out["NV_STATUS"]["alarms_active"] == 1

    alarm_calls = []

    def _track_alarmas(*_a, **_k):
        alarm_calls.append(1)
        return []

    monkeypatch.setattr(
        inv,
        "obtener_telemetry_ont",
        lambda *_a, **_k: {
            "tx": 2.1,
            "rx": -20.5,
            "sn": "ASKY00866826",
            "oper": "UP",
            "admin": "UNLOCKED",
            "health": "Healthy",
            "health_ts": None,
        },
    )
    monkeypatch.setattr(inv, "obtener_alarmas_ont_activas", _track_alarmas)
    out_ok = inv.consultar_access_id_potencias("1058443222")
    assert len(alarm_calls) == 1
    assert out_ok["alarmas_label"] == "Sin Alarmas"
    assert out_ok["ALARMAS"] == []


def test_build_alarmas_ultima_ont_search_query_incluye_todas_y_sort():
    import altiplano

    q = altiplano._build_alarmas_ultima_ont_search_query(
        "BA_OLTA_SF01_04.LT7", "BA_OLTA_SF01_04:1-1-7-1-5"
    )
    assert q is not None
    assert q["size"] == 20
    assert q["sort"] == [{"raisedTime": {"order": "desc"}}]
    must = q["query"]["bool"]["must"]
    status_terms = {
        t["term"]["alarmStatus"]
        for t in must[0]["bool"]["should"]
        if "term" in t
    }
    assert status_terms == {"Active", "active", "Cleared", "cleared"}


def test_onu_last_down_from_ema():
    import altiplano

    body = {
        "extraAttributes": {
            "onu-last-down-reason": "dgi",
            "onu-state-last-change": "2026-06-16T13:11:37-03:00",
        }
    }
    out = altiplano._onu_last_down_from_ema(body)
    assert out == {"reason": "onu-dying-gasp", "ts": "2026-06-16T13:11:37-03:00"}


def test_ultima_alarma_ont_payload_ema_prioriza_sobre_fm():
    import altiplano

    fm = [
        {
            "type": "lan-los",
            "raised": "2026-06-18T14:44:30.000Z",
            "cleared": "2026-06-18T14:44:43.000Z",
            "status": "Cleared",
            "text": "LAN-LOS (No carrier at the Ethernet UNI)",
        },
        {
            "type": "onu-dying-gasp",
            "raised": "2026-06-18T12:24:04.000Z",
            "cleared": "2026-06-18T14:43:25.000Z",
            "status": "Cleared",
            "text": "Serial-Number=ASKY0036B888",
            "repair": "Restore power to ONU. Dying gasp indication is due to loss of power input to ONU.",
        },
    ]
    out = altiplano.ultima_alarma_ont_payload(
        fm,
        live_sn="ASKY0036B888",
        onu_last_down_reason="onu-dying-gasp",
        onu_last_down_ts="2026-06-18T14:45:25-03:00",
    )
    assert out["type"] == "onu-dying-gasp"
    assert out["source"] == "ema"

    out_fm = altiplano.ultima_alarma_ont_payload(
        fm, live_sn="ASKY0036B888"
    )
    assert out_fm["type"] == "onu-dying-gasp"
    assert out_fm["source"] == "fm"
    assert out_fm["raised"] == "2026-06-18T14:43:25.000Z"


def test_ultima_alarma_ont_payload_fm_y_fallback_ema():
    import altiplano

    fm = [
        {
            "type": "absence-of-phy",
            "raised": "2026-06-12T13:54:48.000Z",
            "cleared": "2026-06-13T10:00:00.000Z",
            "status": "Cleared",
            "text": "Serial-Number=MSTC8CCCA45A",
        }
    ]
    out = altiplano.ultima_alarma_ont_payload(
        fm, live_sn="MSTC8CCCA45A"
    )
    assert out["type"] == "absence-of-phy"
    assert out["source"] == "fm"

    out_ema = altiplano.ultima_alarma_ont_payload(
        [],
        onu_last_down_reason="dgi",
        onu_last_down_ts="2026-06-16T13:11:37-03:00",
    )
    assert out_ema["type"] == "onu-dying-gasp"
    assert out_ema["source"] == "ema"


def test_resolve_onu_last_down_onu_not_present_desde_ema_vacio():
    import altiplano

    body = {
        "extraAttributes": {
            "onu-last-down-reason": "-",
            "serialNumber": "-",
            "operation-state": "-",
            "tx-signal-level": "-",
            "rx-signal-level-ont": "-",
        }
    }
    assert altiplano._ema_indica_onu_ausente_en_pon(body) is True
    out = altiplano._resolve_onu_last_down_from_ema(
        body, fallback_ts="2026-06-19T03:30:00+00:00"
    )
    assert out == {"reason": "onu-not-present", "ts": "2026-06-19T03:30:00+00:00"}

    out_fm = altiplano.ultima_alarma_ont_payload(
        [],
        onu_last_down_reason="onu-not-present",
        onu_last_down_ts="2026-06-19T03:30:00+00:00",
    )
    assert out_fm["type"] == "onu-not-present"
    assert out_fm["source"] == "ema"

    out_infer = altiplano.ultima_alarma_ont_payload(
        [],
        ema_onu_ausente_en_pon=True,
        onu_last_down_ts="2026-06-19T03:30:00+00:00",
    )
    assert out_infer["type"] == "onu-not-present"
    assert out_infer["source"] == "ema"


def test_ultima_alarma_fm_loss_of_phy_prioriza_sobre_onu_ausente_inferido():
    import altiplano

    fm = [
        {
            "type": "onu-loss-of-phy-layer",
            "raised": "2026-06-18T15:50:37.000Z",
            "cleared": "",
            "status": "Active",
            "text": "Event=loss of PHY connectivity with ONU due to missing bursts (LOFi/LOSi or LOBi), Serial-Number=ASKY004395F8",
            "repair": "Check physical connectivity between ONU and OLT.",
        }
    ]
    out = altiplano.ultima_alarma_ont_payload(
        fm,
        live_sn="ASKY004395F8",
        ema_onu_ausente_en_pon=True,
        onu_last_down_ts="2026-06-18T16:00:00+00:00",
    )
    assert out["type"] == "loss-of-signal"
    assert out["raised"] == "2026-06-18T15:50:37.000Z"
    assert out["source"] == "fm"


def test_consultar_access_id_potencias_incluye_ultima_alarma(monkeypatch):
    from services import inventory as inv

    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {
            "AID": "1059668406",
            "Status": "IN SERVICE",
            "CTO": "TG02-FATC-8-106602",
        },
    )
    monkeypatch.setattr(
        inv,
        "_resolver_object_name_operator_potencias",
        lambda *_a, **_k: ("BA_OLTA_TG02_03-2-12-9", 1001),
    )
    monkeypatch.setattr(
        inv,
        "obtener_telemetry_ont",
        lambda *_a, **_k: {
            "tx": 2.6,
            "rx": -22.6,
            "sn": "MSTC8CCCA45A",
            "onu_last_down_reason": "onu-dying-gasp",
            "onu_last_down_ts": "2026-06-16T13:11:37-03:00",
        },
    )
    monkeypatch.setattr(inv, "obtener_alarmas_ont_activas", lambda *_a, **_k: [])
    monkeypatch.setattr(inv, "obtener_ultima_alarma_ont", lambda *_a, **_k: [])

    out = inv.consultar_access_id_potencias("1059668406")
    assert out["ULTIMA_ALARMA"]["type"] == "onu-dying-gasp"
    assert out["ULTIMA_ALARMA"]["raised"] == "2026-06-16T13:11:37-03:00"
