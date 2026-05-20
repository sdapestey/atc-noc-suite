def test_obtener_potencias_ont_fallback_ema_si_restconf_falla(monkeypatch):
    import altiplano

    calls = []

    def fake_http(url, auth_url, **kwargs):
        calls.append(url)
        label = kwargs.get("log_label", "")

        class R:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {}

        if "RESTCONF" in label:

            class R404:
                status_code = 404
                text = ""

            return None if fake_http.restconf_fail else _diag_body()

        if "EMA" in label:
            return {
                "extraAttributes": {
                    "tx-signal-level": "21",
                    "rx-signal-level-ont": "-203",
                }
            }

        return None

    def _diag_body():
        return {
            "bbf-hardware-transceivers-mounted:diagnostics": {
                "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": -180,
                "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -250,
            }
        }

    fake_http.restconf_fail = True
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *_a, **_k: "tk")
    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)

    out = altiplano.obtener_potencias_ont(
        "1058443222",
        "BA_OLTA_SF01_04:1-1-7-1-5",
        1001,
        ne="BA_OLTA_SF01_04.LT7",
    )
    assert out == (2.1, -20.3)
    assert len(calls) >= 2
    assert any("restconf/data" in u for u in calls)
    assert any("/rest/ema/entity/" in u for u in calls)


def test_obtener_potencias_ont_usa_restconf_sin_ema_si_ok(monkeypatch):
    import altiplano

    calls = []

    def fake_http(url, auth_url, **kwargs):
        calls.append(kwargs.get("log_label", ""))
        return {
            "bbf-hardware-transceivers-mounted:diagnostics": {
                "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": -180,
                "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -250,
            }
        }

    monkeypatch.setattr(altiplano, "_obtener_token", lambda *_a, **_k: "tk")
    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)

    out = altiplano.obtener_potencias_ont(
        "1",
        "BA_OLTA_X:1-1-1-1-100",
        1001,
        ne="BA_OLTA_X.LT1",
    )
    assert out == (-18.0, -25.0)
    assert any("RESTCONF" in c for c in calls)
