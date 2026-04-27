def test_obtener_potencias_por_cto_soporta_operadores_nuevos(monkeypatch):
    import altiplano

    onts = [
        ("100", "BA_OLTA_X:1-1-1-1-100", 1001),  # TASA
        ("200", "BA_OLTA_X:1-1-1-1-200", 3001),  # DIRECTV
        ("300", "BA_OLTA_X:1-1-1-1-300", 4000),  # METROTEL
        ("400", "BA_OLTA_X:1-1-1-1-400", 4010),  # METROTEL
        ("500", "BA_OLTA_X:1-1-1-1-500", 3950),  # IPLAN
        ("999", "BA_OLTA_X:1-1-1-1-999", 9999),  # no soportado
    ]

    monkeypatch.setattr(altiplano, "_obtener_token", lambda *_a, **_k: "tk")

    called_urls = []

    def fake_get(url, headers=None, verify=False, timeout=None):
        called_urls.append(url)

        class R:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "bbf-hardware-transceivers-mounted:diagnostics": {
                        "nokia-hardware-transceivers-dbm-mounted:tx-power-dbm": -180,
                        "nokia-hardware-transceivers-dbm-mounted:rx-power-dbm": -250,
                    }
                }

        return R()

    monkeypatch.setattr(altiplano.requests, "get", fake_get)

    out = altiplano.obtener_potencias_por_cto("BA_OLTA_X", onts)

    assert set(out.keys()) == {"100", "200", "300", "400", "500"}
    for _aid, pair in out.items():
        assert pair == (-18.0, -25.0)

    assert any("/tasa-altiplano-ac/" in u for u in called_urls)
    assert any("/dtv-altiplano-ac/" in u for u in called_urls)
    assert any("/metro-altiplano-ac/" in u for u in called_urls)
    assert any("/iplan-altiplano-ac/" in u for u in called_urls)
    assert all("999" not in u for u in called_urls)


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
