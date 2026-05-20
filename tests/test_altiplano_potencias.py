def test_obtener_potencias_por_cto_soporta_operadores_nuevos(monkeypatch):
    import altiplano

    onts = [
        ("100", "BA_OLTA_X:1-1-1-1-100", 1001),  # TASA
        ("200", "BA_OLTA_X:1-1-1-1-200", 3001),  # DIRECTV
        ("300", "BA_OLTA_X:1-1-1-1-300", 4000),  # METROTEL
        ("400", "BA_OLTA_X:1-1-1-1-400", 4010),  # METROTEL
        ("500", "BA_OLTA_X:1-1-1-1-500", 3950),  # IPLAN
        ("600", "BA_OLTA_X:1-1-1-1-600", 2800),  # ATC
        ("999", "BA_OLTA_X:1-1-1-1-999", 9999),  # no soportado
    ]

    called_urls = []

    def fake_http(url, auth_url, **kwargs):
        called_urls.append(url)
        return {
            "bbf-hardware-transceivers-mounted:diagnostics": {
                "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": -180,
                "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -250,
            }
        }

    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)

    out = altiplano.obtener_potencias_por_cto("BA_OLTA_X", onts)

    assert set(out.keys()) == {"100", "200", "300", "400", "500", "600"}
    for _aid, pair in out.items():
        assert pair == (-18.0, -25.0)

    assert any("/tasa-altiplano-ac/" in u for u in called_urls)
    assert any("/dtv-altiplano-ac/" in u for u in called_urls)
    assert any("/metro-altiplano-ac/" in u for u in called_urls)
    assert any("/iplan-altiplano-ac/" in u for u in called_urls)
    assert any("/atc-altiplano-ac/" in u for u in called_urls)
    assert all("999" not in u for u in called_urls)


def test_obtener_potencias_por_cto_fallback_ema_si_restconf_vacio(monkeypatch):
    """Si RESTCONF no devuelve diagnostics, se consulta la API EMA (como la GUI)."""
    import altiplano

    onts = [("100", "BA_OLTA_X:1-1-1-1-100", 1001)]

    http_calls = []

    def fake_http(url, auth_url, **kwargs):
        http_calls.append(kwargs.get("log_label", ""))
        if "RESTCONF" in kwargs.get("log_label", ""):
            return None
        return {
            "extraAttributes": {
                "tx-signal-level": "21",
                "rx-signal-level-ont": "-203",
            }
        }

    monkeypatch.setattr(altiplano, "_http_get_altiplano_json", fake_http)

    out = altiplano.obtener_potencias_por_cto("BA_OLTA_X", onts)

    assert out == {"100": (2.1, -20.3)}
    assert len(http_calls) >= 2
    assert any("RESTCONF" in c for c in http_calls)
    assert any("EMA" in c for c in http_calls)


def test_obtener_potencias_por_cto_operador_no_soportado_se_omite(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano.requests,
        "get",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("No debería llamar requests.get")),
    )

    out = altiplano.obtener_potencias_por_cto(
        "BA_OLTA_X",
        [("999", "BA_OLTA_X:1-1-1-1-999", 5555)],
    )
    assert out == {}
