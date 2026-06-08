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
