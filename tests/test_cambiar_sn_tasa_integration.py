"""Verifica que cambiar_sn_ont normaliza SN TASA antes del PATCH (sin red real)."""


def test_cambiar_sn_ont_applies_tasa_hex_normalization(monkeypatch):
    import altiplano

    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")
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

    captured = {}

    def fake_patch(url, json=None, headers=None, verify=False, timeout=None):
        captured["url"] = url
        captured["json"] = json

        class R:
            status_code = 200

        return R()

    monkeypatch.setattr(altiplano.requests, "patch", fake_patch)

    out = altiplano.cambiar_sn_ont(
        access_id="105",
        operador="TASA",
        ont_target="BA_OLTA_TG01_02-2-15-8",
        new_sn="41534B5900435645",
    )
    assert out["ok"] is True
    assert out["sn"] == "ASKY00435645"
    assert (
        captured["json"]["ibn:intent"]["intent-specific-data"]["ont:ont"][
            "expected-serial-number"
        ]
        == "ASKY00435645"
    )


def test_cambiar_sn_ont_non_tasa_no_hex_normalization(monkeypatch):
    import altiplano

    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.2", "32443", "dtv-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "get_altiplano_operator_credentials",
        lambda _op: ("u", "p"),
    )

    captured = {}

    def fake_patch(url, json=None, headers=None, verify=False, timeout=None):
        captured["json"] = json

        class R:
            status_code = 200

        return R()

    monkeypatch.setattr(altiplano.requests, "patch", fake_patch)

    out = altiplano.cambiar_sn_ont(
        access_id="105",
        operador="DIRECTV",
        ont_target="X-1-1-1",
        new_sn="53444D435C73B3AF",
    )
    assert out["ok"] is True
    assert out["sn"] == "SDMC5C73B3AF"
    assert (
        captured["json"]["ibn:intent"]["intent-specific-data"]["ont:ont"][
            "expected-serial-number"
        ]
        == "SDMC5C73B3AF"
    )
