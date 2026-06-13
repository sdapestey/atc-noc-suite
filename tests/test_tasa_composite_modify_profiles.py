def test_tasa_composite_modify_profiles_variables():
    from altiplano import tasa_composite_modify_profiles_variables

    v = tasa_composite_modify_profiles_variables(
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        downstream_profile="TASA_SH100MB_DN",
        upstream_profile="TASA_BW100MB_UP",
    )
    assert v is not None
    assert v["Downstream Profile"] == "TASA_SH100MB_DN"
    assert v["Upstream Profile"] == "TASA_BW100MB_UP"
    assert v["SVLAN"] == "1501"


def test_actualizar_tasa_composite_profiles_nbi(monkeypatch):
    import altiplano as ap
    from services.tasa_postman_catalog import TASA_MODIFY_PROFILES_API_ID

    calls = []

    monkeypatch.setattr(
        "services.tasa_postman_execute.execute_tasa_postman_api",
        lambda api_id, variables, **_kw: calls.append((api_id, variables))
        or {"ok": True, "message": "patched"},
    )

    out = ap.actualizar_tasa_composite_profiles_nbi(
        "TASA",
        "BA_OLTA_SF01_01-2-1-9#HSI-1501",
        downstream_profile="TASA_SH100MB_DN",
        upstream_profile="TASA_BW100MB_UP",
    )
    assert out["ok"] is True
    assert calls[0][0] == TASA_MODIFY_PROFILES_API_ID
    assert calls[0][1]["Device Name"] == "BA_OLTA_SF01_01"
    assert out["tasa_hsi"]["upstream_profile"] == "TASA_BW100MB_UP"
