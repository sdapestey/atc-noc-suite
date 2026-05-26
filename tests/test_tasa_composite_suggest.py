def test_suggest_request_body_from_target():
    from altiplano import _tasa_composite_suggest_request_body

    body = _tasa_composite_suggest_request_body(
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        {
            "c_vlan_id": 1133,
            "downstream_profile": "TASA_SH300MB_DN",
            "upstream_profile": "TASA_BW300MB_UP",
        },
        "100",
    )
    assert body is not None
    assert body["searchQuery"] == "100"
    tgt = body["inputValues"]["target"]
    assert tgt["ont-name"] == "BA_OLTA_SF01_01-2-1-9"
    assert tgt["hsi-name"] == "HSI-1501"
    hsi = body["inputValues"]["arguments"]["intent-specific-data"]["hsi"][0]
    assert hsi["downstream-profile"] == "TASA_SH300MB_DN"
    assert hsi["upstream-profile"] == "TASA_BW300MB_UP"


def test_profile_names_from_suggest_response():
    from altiplano import _profile_names_from_tasa_suggest_response

    names = _profile_names_from_tasa_suggest_response(
        {"TASA_BW100MB_UP": "TASA_BW100MB_UP", "TASA_BW300MB_UP": "TASA_BW300MB_UP"}
    )
    assert "TASA_BW100MB_UP" in names
    assert names == sorted(names, key=str.lower)


def test_tasa_composite_profile_suggestions_nbi(monkeypatch):
    import altiplano as ap

    class FakeRes:
        status_code = 200
        text = ')]}\',\n{"TASA_BW100MB_UP":"TASA_BW100MB_UP"}'

    monkeypatch.setattr(ap, "_nbi_bearer_token_for_entorno", lambda _op: ("tok", None))
    monkeypatch.setattr(
        ap,
        "get_altiplano_nbi_target",
        lambda _op: ("10.200.4.101", "32443", "tasa-altiplano-ac"),
    )
    monkeypatch.setattr(ap.requests, "post", lambda *_a, **_kw: FakeRes())

    out = ap.tasa_composite_profile_suggestions_nbi(
        "TASA",
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        "upstream",
        tasa_hsi={"c_vlan_id": 1133, "downstream_profile": "TASA_SH300MB_DN"},
        search_query="",
    )
    assert out["ok"] is True
    assert "TASA_BW100MB_UP" in out["profiles"]
