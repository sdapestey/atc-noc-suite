def test_tasa_composite_device_search_target():
    from altiplano import _tasa_composite_device_search_target, _tasa_composite_row_matches_target

    assert (
        _tasa_composite_device_search_target("BA_OLTA_SF01_01-2-1-9#HSI-1501")
        == "BA_OLTA_SF01_01-2-1-9"
    )
    assert _tasa_composite_row_matches_target(
        {"target": "BA_OLTA_SF01_01-2-1-9#HSI-1501"},
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
    )


def test_wait_tasa_composite_uses_device_prefix_and_v3(monkeypatch):
    import altiplano as ap

    calls = []

    def fake_buscar(_base, _hdr, target, **kw):
        calls.append((target, kw.get("intent_type_version")))
        return [{"target": "BA_OLTA_SF01_01-2-1-9#HSI-1501", "intent_type": "tasa-composite"}]

    monkeypatch.setattr(ap, "buscar_intents_via_gui_target_search", fake_buscar)
    monkeypatch.setattr(
        ap,
        "_operator_nbi_search_session",
        lambda _op: ({"base_rest": "https://x/rest/restconf/data", "headers": {}}, None),
    )

    found, msg, _elapsed = ap._wait_tasa_composite_visible(
        "TASA",
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        timeout_s=8,
        interval_s=0.01,
    )
    assert found is True
    assert calls[0][0] == "BA_OLTA_SF01_01-2-1-9"
    assert calls[0][1] == "3"
    assert "visible" in msg


def test_parse_tasa_composite_target():
    from altiplano import parse_tasa_composite_target, tasa_composite_postman_variables

    p = parse_tasa_composite_target("BA_OLTA_SF01_01-2-1-9#HSI-1501")
    assert p is not None
    assert p["device_name"] == "BA_OLTA_SF01_01"
    assert p["lt"] == "2"
    assert p["svlan"] == "1501"

    vars_map = tasa_composite_postman_variables(
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        {
            "downstream_profile": "TASA_SH940MB_DN",
            "upstream_profile": "TASA_BW940MB_UP",
            "c_vlan_id": 101,
        },
    )
    assert vars_map["Device Name"] == "BA_OLTA_SF01_01"
    assert vars_map["SVLAN"] == "1501"
    assert vars_map["Downstream Profile"] == "TASA_SH940MB_DN"


def test_hsi_from_ibn_row_en_match():
    from altiplano import _match_entry_to_result_dict

    row = {
        "target": "BA_OLTA_X-1-1-1#HSI-99",
        "intent-type": "tasa-composite",
        "required-network-state": "active",
        "aligned": "true",
        "intent-specific-data": {
            "tasa-composite:hsi": {
                "downstream-profile": "TASA_SH940MB_DN",
                "c-vlan-id": 101,
                "upstream-profile": "TASA_BW940MB_UP",
            }
        },
    }
    out = _match_entry_to_result_dict(row)
    assert out["intent_type"] == "tasa-composite"
    assert out["tasa_hsi"]["downstream_profile"] == "TASA_SH940MB_DN"
    assert out["tasa_hsi"]["c_vlan_id"] == 101


def test_reinyectar_tasa_composite_nbi(monkeypatch):
    import altiplano as ap
    from services.tasa_postman_catalog import TASA_SERVICES_API_ID

    calls = []

    monkeypatch.setattr(ap, "borrar_intent_nbi", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(
        "services.tasa_postman_execute.execute_tasa_postman_api",
        lambda api_id, variables: calls.append((api_id, variables))
        or {"ok": True, "message": "created"},
    )
    monkeypatch.setattr(
        ap,
        "_wait_tasa_composite_visible",
        lambda *_a, **_kw: (True, "intent visible en NBI", 2.0),
    )

    out = ap.reinyectar_tasa_composite_nbi(
        "TASA",
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        tasa_hsi={
            "downstream_profile": "TASA_SH940MB_DN",
            "upstream_profile": "TASA_BW940MB_UP",
            "c_vlan_id": 101,
        },
    )
    assert out["ok"] is True
    assert out["phase"] == "done"
    assert out.get("verify_elapsed_s") == 2.0
    assert calls[0][0] == TASA_SERVICES_API_ID
    assert calls[0][1]["SVLAN"] == "1501"


def test_reinyectar_verify_timeout(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(ap, "borrar_intent_nbi", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(
        "services.tasa_postman_execute.execute_tasa_postman_api",
        lambda *_a, **_kw: {"ok": True},
    )
    monkeypatch.setattr(
        ap,
        "_wait_tasa_composite_visible",
        lambda *_a, **_kw: (False, "sin confirmación tras 120s", 120.0),
    )

    out = ap.reinyectar_tasa_composite_nbi(
        "TASA",
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        verify_timeout_s=1.0,
    )
    assert out["ok"] is False
    assert out["phase"] == "verify_timeout"
