"""Borrado INP con cascada VNO TASA."""

from services.inp_borrado_cascade import (
    parse_olt_location_target,
    resolve_borrado_cascade_context,
)


def test_parse_olt_location_target_prefix():
    p = parse_olt_location_target("BA_OLTA_ES01_01-1-1-99")
    assert p is not None
    assert p["device_name"] == "BA_OLTA_ES01_01"
    assert p["lt"] == "1"
    assert p["pon"] == "1"
    assert p["ont"] == "99"


def test_parse_olt_location_target_full():
    p = parse_olt_location_target("BA_OLTA_ES01_01-10-6-99#1001#gpon")
    assert p is not None
    assert p["vno"] == 1001
    assert p["lt"] == "10"
    assert p["pon"] == "6"
    assert p["ont"] == "99"


def test_svlans_from_composite_targets():
    from services.inp_borrado_cascade import _svlans_from_tasa_composite_intents

    intents = [
        {"intent-type": "tasa-composite", "target": "BA_OLTA_ES01_01-1-1-2#HSI-100"},
        {"intent-type": "tasa-composite", "target": "BA_OLTA_ES01_01-1-1-2#HSI-200"},
        {"intent-type": "ont", "target": "BA_OLTA_ES01_01-1-1-2"},
    ]
    assert _svlans_from_tasa_composite_intents(intents, "BA_OLTA_ES01_01-1-1-2") == ["100", "200"]


def test_discover_svlans_from_gui_search_response(monkeypatch):
    """Formato real capturado en HAR TASA (ibn:search-intents + filter ES)."""
    from services import inp_borrado_cascade as cascade

    payload = {
        "ibn:output": {
            "intents": {
                "intent": [
                    {
                        "intent-type": "tasa-composite",
                        "intent-type-version": 3,
                        "target": "BA_OLTA_ES01_01-1-1-2#HSI-1501",
                    }
                ]
            },
            "page-size": 1,
            "total-count": 1,
        }
    }

    class FakeResp:
        status_code = 200
        text = __import__("json").dumps(payload)

    posted: list[dict] = []

    def fake_post(url, **kwargs):
        posted.append(kwargs.get("json") or {})
        return FakeResp()

    monkeypatch.setattr(
        cascade,
        "_tasa_auth_headers",
        lambda: ({"Authorization": "Bearer x"}, "x"),
    )
    monkeypatch.setattr(
        cascade,
        "_tasa_rest_bases",
        lambda: ("https://h/p/rest/restconf/data", "https://h/p/rest/restconf/operations"),
    )
    monkeypatch.setattr(cascade.requests, "post", fake_post)
    monkeypatch.setattr(cascade.requests, "get", lambda *a, **k: FakeResp())

    svlans, err, _dbg = cascade.discover_tasa_hsi_svlans("BA_OLTA_ES01_01-1-1-2")
    assert err is None
    assert svlans == ["1501"]
    assert posted
    assert "ibn:search-intents" in posted[0]
    filt = posted[0]["ibn:search-intents"]["filter"]
    assert filt["target"] == "BA_OLTA_ES01_01-1-1-2"
    assert filt["predicate"] == "CONTAINS"


def test_discover_svlans_from_legacy_input_response(monkeypatch):
    from services import inp_borrado_cascade as cascade

    payload = {
        "ibn:output": {
            "intents": {
                "intent": [
                    {
                        "intent-type": "tasa-composite",
                        "target": "BA_OLTA_ES01_01-1-1-2#HSI-42",
                    }
                ]
            }
        }
    }

    class FakeResp:
        status_code = 200
        text = __import__("json").dumps(payload)

    call_n = {"n": 0}

    def fake_post(url, **kwargs):
        call_n["n"] += 1
        if call_n["n"] == 1:

            class _NotFound:
                status_code = 404
                text = ""

                @staticmethod
                def json():
                    raise ValueError("no body")

            return _NotFound()
        return FakeResp()

    monkeypatch.setattr(
        cascade,
        "_tasa_auth_headers",
        lambda: ({"Authorization": "Bearer x"}, "x"),
    )
    monkeypatch.setattr(
        cascade,
        "_tasa_rest_bases",
        lambda: ("https://h/p/rest/restconf/data", "https://h/p/rest/restconf/operations"),
    )
    monkeypatch.setattr(cascade.requests, "post", fake_post)
    monkeypatch.setattr(cascade.requests, "get", lambda *a, **k: FakeResp())

    svlans, err, _dbg = cascade.discover_tasa_hsi_svlans("BA_OLTA_ES01_01-1-1-2")
    assert err is None
    assert svlans == ["42"]


def test_extract_hsi_svlans_from_restconf_map_keys():
    from services.inp_borrado_cascade import extract_hsi_svlans_deep

    payload = {
        "ibn:ibn": {
            "intent": {
                "BA_OLTA_ES01_01-1-1-2#HSI-100,tasa-composite": {
                    "required-network-state": "active",
                },
                "BA_OLTA_ES01_01-1-1-2#HSI-200,tasa-composite": {},
            }
        }
    }
    assert extract_hsi_svlans_deep(payload, "BA_OLTA_ES01_01-1-1-2") == ["100", "200"]


def test_resolve_context_from_device_with_vno_suffix():
    ctx = resolve_borrado_cascade_context("BA_OLTA_ES01_01-1-1-99#1001#gpon", "")
    assert ctx["ok"] is True
    assert ctx["operator"] == "TASA"
    assert ctx["vno_code"] == 1001
    assert ctx["vno_variables"]["Device Name"] == "BA_OLTA_ES01_01"


def test_resolve_context_vno_from_inp(monkeypatch):
    from services import inp_borrado_cascade as cascade

    monkeypatch.setattr(
        cascade,
        "buscar_intents_ont_connection_inp",
        lambda _tok, **kw: {
            "ok": True,
            "matches": [{"target": "BA_OLTA_ES01_01-1-1-2#3001#gpon"}],
        },
    )
    ctx = cascade.resolve_borrado_cascade_context(
        "BA_OLTA_ES01_01-1-1-2",
        "",
        sess_token="tok",
    )
    assert ctx["ok"] is True
    assert ctx["operator"] == "DIRECTV"
    assert ctx["vno_code"] == 3001


def test_borrar_cascade_tasa_then_inp(monkeypatch):
    from services import inp_borrado_cascade as cascade

    calls: list[str] = []

    def fake_exec(api_id, variables, **kwargs):
        calls.append((api_id, variables.get("SVLAN")))
        return {"ok": True, "message": "ok", "status_code": 200}

    def fake_inp(token, **kw):
        return {"ok": True, "message": "INP ok", "target": "BA_OLTA_X#1001#gpon"}

    monkeypatch.setattr(cascade, "execute_tasa_postman_api", fake_exec)
    monkeypatch.setattr(cascade, "borrar_intent_ont_connection_inp", fake_inp)
    monkeypatch.setattr(
        cascade,
        "discover_tasa_hsi_svlans",
        lambda _p, **kw: (["100"], None, {}),
    )

    out = cascade.borrar_inp_con_cascada_vno(
        "tok",
        "BA_OLTA_ES01_01-1-1-99#1001#gpon",
        "",
    )
    assert out["ok"] is True
    assert calls == [
        ("unconfigure-delete-services", "100"),
        ("unconfigure-delete-ont", None),
    ]
    assert len(out["vno_steps"]) == 5
    assert out["vno_steps"][0]["label"] == "Detectar VNO"


def test_borrar_cascade_stops_on_vno_failure(monkeypatch):
    from services import inp_borrado_cascade as cascade

    def fake_exec(api_id, variables, **kwargs):
        if api_id == "unconfigure-delete-ont":
            return {"ok": False, "message": "falló ont"}
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(cascade, "execute_tasa_postman_api", fake_exec)
    monkeypatch.setattr(
        cascade,
        "borrar_intent_ont_connection_inp",
        lambda *_a, **_k: {"ok": True},
    )

    out = cascade.borrar_inp_con_cascada_vno("tok", "BA_OLTA_ES01_01-1-1-99#1001#gpon", "")
    assert out["ok"] is False
    assert any(s.get("label") == "Delete ONT" and not s.get("ok") for s in out.get("vno_steps") or [])
