def test_crear_ont_connection_intent_ok_201(monkeypatch):
    import altiplano

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
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    captured = {}

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers

        class R:
            status_code = 201

            @staticmethod
            def json():
                return {"ok": True}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
        pir=1000,
        cir=35,
    )
    assert out["ok"] is True
    assert out["status_code"] == 201
    assert out["target"] == "BA_OLTA_VL01_01-1-2-66#1001#gpon"
    assert "rest/restconf/data/ibn:ibn" in captured["url"]
    payload = captured["json"]["ibn:intent"]
    assert payload["intent-type"] == "ont-connection"
    assert payload["intent-specific-data"]["ont-connection:ont-connection"]["access-id"] == "1051234567"


def test_crear_ont_connection_intent_login_fail(monkeypatch):
    import altiplano

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
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: None)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
    )
    assert out["ok"] is False
    assert "autenticar" in out["message"].lower()


def test_crear_ont_connection_intent_api_fail(monkeypatch):
    import altiplano

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
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    def fake_post(_url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 500

            @staticmethod
            def json():
                return {"error-message": "boom"}

            text = "boom"

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_VL01_01",
        lt="1",
        pon="2",
        ont="66",
        vno="1001",
        fiber_name="FIBRA-1",
        access_id="1051234567",
    )
    assert out["ok"] is False
    assert "rechaz" in out["message"].lower() or "http" in out["message"].lower()


def test_crear_ont_connection_intent_usa_bearer_sin_login(monkeypatch):
    import altiplano

    monkeypatch.setattr(
        altiplano,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "inp-altiplano-ac"),
    )
    monkeypatch.setattr(
        altiplano,
        "_obtener_token",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no debería llamar login")),
    )

    captured = {}

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        captured["auth"] = (headers or {}).get("Authorization", "")
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_X",
        lt="1",
        pon="1",
        ont="1",
        vno="1001",
        fiber_name="BA_OLTA_X-1-1",
        access_id="1",
        nbi_bearer_token="tok-ui",
    )
    assert out["ok"] is True
    assert "Bearer tok-ui" in captured["auth"]


def test_crear_ont_connection_intent_prefiere_credenciales_ui(monkeypatch):
    import altiplano

    env_calls = []

    def fake_env_cred(_op):
        env_calls.append(_op)
        return ("env_u", "env_p")

    tok_calls = []

    def fake_token(auth_url, username=None, password=None, force_refresh=False):
        tok_calls.append((username, password, force_refresh))
        return "fake-token"

    monkeypatch.setattr(altiplano, "get_altiplano_nbi_target", lambda _k: ("10.0.0.1", "32443", "inp-altiplano-ac"))
    monkeypatch.setattr(altiplano, "get_altiplano_operator_credentials", fake_env_cred)
    monkeypatch.setattr(altiplano, "_obtener_token", fake_token)

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_ES01_01",
        lt="1",
        pon="1",
        ont="59",
        vno="1001",
        fiber_name="BA_OLTA_ES01_01-1-1",
        access_id="prueba",
        nbi_username="ui_u",
        nbi_password="ui_p",
    )
    assert out["ok"] is True
    assert env_calls == []
    assert tok_calls and tok_calls[0][0] == "ui_u" and tok_calls[0][1] == "ui_p"


def test_crear_ont_connection_intent_uses_nbi_environment_not_operator(monkeypatch):
    import altiplano

    calls = {}

    def fake_target(key):
        calls["key"] = key
        return ("10.0.0.9", "32443", "inp-altiplano-ac")

    monkeypatch.setattr(altiplano, "get_altiplano_nbi_target", fake_target)
    monkeypatch.setattr(altiplano, "get_altiplano_operator_credentials", lambda _op: ("u", "p"))
    monkeypatch.setattr(altiplano, "_obtener_token", lambda *a, **k: "fake-token")

    def fake_post(url, json=None, headers=None, verify=False, timeout=None):
        class R:
            status_code = 201

            @staticmethod
            def json():
                return {}

            text = ""

        return R()

    monkeypatch.setattr(altiplano.requests, "post", fake_post)

    out = altiplano.crear_ont_connection_intent(
        operador="TASA",
        entorno_nbi="INP",
        device_name="BA_OLTA_ES01_01",
        lt="1",
        pon="1",
        ont="59",
        vno="1001",
        fiber_name="BA_OLTA_ES01_01-1-1",
        access_id="prueba",
    )
    assert out["ok"] is True
    assert calls["key"] == "INP"


def test_match_entry_includes_network_and_alignment_labels():
    import altiplano as ap

    entry = {
        "target": "BA_OLTA_X-1-1-1#1001#gpon",
        "intent-type": "ont-connection",
        "required-network-state": "active",
        "alignment-state": "aligned",
        "intent-specific-data": {
            "ont-connection:ont-connection": {"access-id": "1052337586"},
        },
    }
    out = ap._match_entry_to_result_dict(entry)
    assert out["network_state"] == "Active"
    assert out["alignment_state"] == "Aligned"
    assert out["rn_edit_allowed"] is False
    assert out["access_id"] == "1052337586"
    assert out["target"] == "BA_OLTA_X-1-1-1#1001#gpon"
    assert out["location_slice_pon"] == "BA_OLTA_X-1-1-1#1001#gpon"


def test_match_entry_network_delete_maps_to_not_present():
    import altiplano as ap

    entry = {
        "target": "BA_OLTA_X#3001#gpon",
        "intent-type": "ont-connection",
        "required-network-state": "delete",
    }
    out = ap._match_entry_to_result_dict(entry)
    assert out["network_state"] == "Not present"
    assert out["rn_edit_allowed"] is True


def test_deep_find_alignment_accepts_camel_case_intent_alignment_state():
    import altiplano as ap

    payload = {
        "ibn:intent": {
            "target": "BA_OLTA_ES01_01-10-10-17#3001#gpon",
            "intent-type": "ont-connection",
            "intentAlignmentState": "misaligned",
        }
    }
    assert ap._deep_find_alignment_leaf(payload) == "misaligned"


def test_match_entry_alignment_from_camel_case_field():
    import altiplano as ap

    entry = {
        "target": "BA_OLTA_X#3001#gpon",
        "intent-type": "ont-connection",
        "intentAlignmentState": "misaligned",
        "intent-specific-data": {
            "ont-connection:ont-connection": {"access-id": "122338315"},
        },
    }
    out = ap._match_entry_to_result_dict(entry)
    assert out["alignment_state"] == "Misaligned"


def test_alignment_absorbed_from_ietf_restconf_data_wrapper():
    """Simula GET real: estado fuera del bloque ont-connection, dentro de `ietf-restconf:data`."""
    import altiplano as ap

    raw = {
        "ietf-restconf:data": {
            "ont-connection:ont-connection": {"access-id": "122338315"},
            "intentAlignmentState": "misaligned",
        }
    }
    entry = ap._coerce_ont_connection_get_payload_to_intent(raw, "BA_OLTA_X#3001#gpon")
    entry = ap._absorb_intent_metadata(entry, raw)
    out = ap._match_entry_to_result_dict(entry)
    assert out["alignment_state"] == "Misaligned"


def test_alignment_absorbed_from_nested_ont_connection_state_block():
    """Muchos AC exponen ``alignment-state`` solo bajo ``ont-connection:ont-connection-state``."""
    import altiplano as ap

    raw = {
        "ietf-restconf:data": {
            "ont-connection:ont-connection": {
                "access-id": "122338315",
                "ont-connection:ont-connection-state": {
                    "alignment-state": "aligned",
                    "required-network-state": "active",
                },
            },
        }
    }
    entry = ap._coerce_ont_connection_get_payload_to_intent(raw, "BA_OLTA_X#3001#gpon")
    entry = ap._absorb_intent_metadata(entry, raw)
    out = ap._match_entry_to_result_dict(entry)
    assert out["alignment_state"] == "Aligned"
    assert out["network_state"] == "Active"


def test_search_intents_operation_url_from_restconf_data_base():
    import altiplano as ap

    base = "https://10.200.3.100:32443/inp-altiplano-ac/rest/restconf/data"
    assert ap._inp_search_intents_operation_url(base) == (
        "https://10.200.3.100:32443/inp-altiplano-ac/rest/restconf/operations/ibn:search-intents"
        "?history=false"
    )


def test_intent_alignment_raw_from_ibn_search_intents_aligned_strings():
    import altiplano as ap

    assert ap._intent_alignment_state_raw({"aligned": "true"}) == "aligned"
    assert ap._intent_alignment_state_raw({"aligned": "false"}) == "misaligned"
    assert ap._intent_alignment_state_raw({"aligned": True}) == "aligned"


def test_match_entry_from_ibn_search_intents_rpc_response_shape():
    """Misma forma que la GUI INP (``aligned`` string, no ``alignment-state``)."""
    import altiplano as ap

    body = {
        "ibn:output": {
            "intents": {
                "intent": [
                    {
                        "intent-type": "ont-connection",
                        "target": "BA_OLTA_ES01_01-1-1-1#1001#gpon",
                        "aligned": "true",
                        "required-network-state": "active",
                    }
                ]
            }
        }
    }
    rows = ap._extract_intent_list_from_search_intents_response(body)
    entry = {"target": "BA_OLTA_ES01_01-1-1-1#1001#gpon", "intent-type": "ont-connection"}
    hit = ap._pick_search_intents_row_for_entry(rows, entry, prefer_target="BA_OLTA_ES01_01-1-1-1#1001#gpon")
    assert hit is not None
    entry = ap._merge_search_intents_row_into_entry(entry, hit)
    out = ap._match_entry_to_result_dict(entry)
    assert out["alignment_state"] == "Aligned"
    assert out["network_state"] == "Active"


def test_extract_intent_list_search_intents_ietf_data_wrapper():
    import altiplano as ap

    body = {
        "ietf-restconf:data": {
            "ibn:output": {
                "intents": {
                    "intent": [
                        {"intent-type": "ont-connection", "target": "BA_OLTA_W#1001#gpon", "aligned": "true"}
                    ]
                }
            }
        }
    }
    rows = ap._extract_intent_list_from_search_intents_response(body)
    assert len(rows) == 1
    assert rows[0]["target"] == "BA_OLTA_W#1001#gpon"


def test_extract_intent_list_search_intents_intents_array():
    import altiplano as ap

    body = {
        "ibn:output": {
            "intents": [
                {"intent-type": "ont-connection", "target": "BA_OLTA_U#1001#gpon", "aligned": "false"},
            ]
        }
    }
    rows = ap._extract_intent_list_from_search_intents_response(body)
    assert len(rows) == 1
    assert rows[0]["target"] == "BA_OLTA_U#1001#gpon"


def test_extract_intent_list_search_intents_intent_top_level_list():
    import altiplano as ap

    body = {
        "ibn:output": {
            "intent": [{"intent-type": "ont-connection", "target": "BA_OLTA_V#3001#gpon"}],
        }
    }
    rows = ap._extract_intent_list_from_search_intents_response(body)
    assert len(rows) == 1
    assert rows[0]["target"] == "BA_OLTA_V#3001#gpon"


def test_access_id_match_mode_for_inp_consult():
    import altiplano as ap

    assert ap._access_id_match_mode_for_inp_consult("127240110") == "exact"
    assert ap._access_id_match_mode_for_inp_consult("BORRAR") == "prefix"
    assert ap._access_id_match_mode_for_inp_consult("RES_IP_8") == "prefix"
    assert ap._access_id_match_mode_for_inp_consult("BORRAR_003") == "exact"


def test_intent_access_id_matches_prefix_and_exact():
    import altiplano as ap

    assert ap._intent_access_id_matches("BORRAR", "BORRAR", "exact") is True
    assert ap._intent_access_id_matches("BORRAR_003", "BORRAR", "exact") is False
    assert ap._intent_access_id_matches("BORRAR_003", "BORRAR", "prefix") is True
    assert ap._intent_access_id_matches("127240110", "127240110", "exact") is True
    assert ap._intent_access_id_matches("1272401101", "127240110", "exact") is False


def test_intent_matches_filters_access_id_prefix():
    import altiplano as ap

    entry = {
        "target": "BA_OLTA_A#1001#gpon",
        "intent-specific-data": {"ont-connection:ont-connection": {"access-id": "BORRAR_003"}},
    }
    assert ap._intent_matches_filters(
        entry,
        device_prefix=None,
        access_id="BORRAR",
        intent_uuid=None,
        access_id_match_mode="prefix",
    )
    assert not ap._intent_matches_filters(
        entry,
        device_prefix=None,
        access_id="BORRAR",
        intent_uuid=None,
        access_id_match_mode="exact",
    )


def test_alignment_from_ibn_intent_list_and_yang_leaf_list():
    import altiplano as ap

    raw = {
        "ietf-restconf:data": {
            "ibn:intent": [
                {
                    "intent-type": "ont-connection",
                    "target": "BA_OLTA_X#3001#gpon",
                    "alignment-state": [{"value": "misaligned"}],
                    "intent-specific-data": {
                        "ont-connection:ont-connection": {"access-id": "122338315"},
                    },
                }
            ]
        }
    }
    entry = ap._coerce_ont_connection_get_payload_to_intent(raw, "BA_OLTA_X#3001#gpon")
    entry = ap._absorb_intent_metadata(entry, raw)
    out = ap._match_entry_to_result_dict(entry)
    assert out["alignment_state"] == "Misaligned"


def test_scalar_alignment_value_yang_style_list():
    import altiplano as ap

    assert ap._scalar_alignment_value([{"value": "misaligned"}]) == "misaligned"


def test_maybe_enrich_alignment_uses_restconf_content_boost():
    """Sin ``content``, el NBI puede omitir ``alignment-state``; el boost lo solicita explícitamente."""
    import altiplano as ap

    calls = []

    def fake_get(url, params):
        calls.append(dict(params or {}))

        class R:
            status_code = 200

            def json(self):
                return {"ibn:intent": {"alignment-state": "aligned"}}

        return R()

    entry = {"target": "X#1001#gpon", "intent-type": "ont-connection"}
    out = ap._maybe_enrich_alignment_from_restconf_get(
        "https://ac/rest/restconf/data", "X#1001#gpon", entry, fake_get
    )
    assert ap._intent_alignment_state_raw(out) == "aligned"
    assert any(c.get("content") == "all" for c in calls)


def test_scalar_from_yang_identity_like_dict_uses_qualified_key_tail():
    import altiplano as ap

    d = {"some-module:aligned": [None]}
    assert ap._scalar_from_yang_identity_like_dict(d) == "aligned"


def test_scalar_alignment_value_identityref_dict():
    import altiplano as ap

    assert ap._scalar_alignment_value({"nokia:aligned": []}) == "aligned"


def test_try_alignment_leaf_subresource_when_boost_has_no_alignment():
    import altiplano as ap

    def fake_get(url, params):
        class R:
            def __init__(self, payload):
                self.status_code = 200
                self._payload = payload

            def json(self):
                return self._payload

        if url.endswith("/alignment-state"):
            return R({"ietf-restconf:data": {"alignment-state": "misaligned"}})
        return R(
            {
                "ietf-restconf:data": {
                    "ibn:intent": {
                        "target": "X#1001#gpon",
                        "intent-type": "ont-connection",
                        "required-network-state": "active",
                    }
                }
            }
        )

    entry = {"target": "X#1001#gpon", "intent-type": "ont-connection"}
    out = ap._try_alignment_leaf_subresources(
        "https://ac/rest/restconf/data", "X#1001#gpon", entry, fake_get
    )
    assert ap._intent_alignment_state_raw(out) == "misaligned"


def test_try_alignment_ont_connection_state_resource_suffix():
    """GUI Altiplano suele pedir ``ont-connection:ont-connection-state`` aparte del intent de config."""
    import altiplano as ap

    def fake_get(url, params):
        class R404:
            status_code = 404

        class R200:
            status_code = 200

            def json(self):
                return {
                    "ietf-restconf:data": {
                        "ont-connection:ont-connection-state": {
                            "required-network-state": "active",
                            "alignment-state": "aligned",
                        }
                    }
                }

        if url.endswith("ont-connection:ont-connection-state"):
            return R200()
        return R404()

    entry = {"target": "X#1001#gpon", "intent-type": "ont-connection"}
    out = ap._try_alignment_leaf_subresources(
        "https://ac/rest/restconf/data", "X#1001#gpon", entry, fake_get
    )
    assert ap._intent_alignment_state_raw(out) == "aligned"


def test_ibn_yang_api_root_from_restconf_base():
    import altiplano as ap

    base = "https://10.200.3.100:32443/inp-altiplano-ac/rest/restconf/data"
    assert ap._inp_ibn_yang_api_root_from_restconf_data_base(base) == (
        "https://10.200.3.100:32443/inp-altiplano-ac/rest/ibn/yang"
    )


def test_json_loads_strips_angular_xssi_prefix():
    import altiplano as ap

    class R:
        text = ")]}',\n{\"alignment-state\": \"aligned\"}"

        def json(self):
            raise ValueError()

    assert ap._json_loads_altiplano_http_response(R()) == {"alignment-state": "aligned"}


def test_looks_like_ibn_yang_schema_metadata_document():
    import altiplano as ap

    body = {
        "onu-management": {"node": "leaf", "type": "enumeration", "validValues": ["A"]},
        "_yang-properties_": {
            "namespace": "http://example/ns",
            "module-name": "ont-connection",
            "container-name": "ont-connection-state",
        },
    }
    assert ap._looks_like_ibn_yang_field_metadata_document(body) is True


def test_ibn_yang_metadata_root_from_restconf_base():
    import altiplano as ap

    base = "https://10.200.3.100:32443/inp-altiplano-ac/rest/restconf/data"
    assert ap._inp_ibn_yang_metadata_root_from_restconf_data_base(base) == (
        "https://10.200.3.100:32443/inp-altiplano-ac/rest/ibn/yang/metadata"
    )


def test_ibn_yang_metadata_api_gets_alignment_from_state_resource():
    import altiplano as ap

    def fake_get(url, params):
        class R404:
            status_code = 404

        class R200:
            status_code = 200

            def json(self):
                return {
                    "ont-connection:ont-connection-state": {
                        "alignment-state": "misaligned",
                        "required-network-state": "active",
                    }
                }

            @property
            def text(self):
                import json as _json

                return _json.dumps(self.json())

        if ("yang/metadata" in url or "yang/runtime" in url) and "ont-connection-state" in url:
            return R200()
        return R404()

    base = "https://10.200.3.100:32443/inp-altiplano-ac/rest/restconf/data"
    entry = {"target": "X#1001#gpon", "intent-type": "ont-connection"}
    out = ap._try_alignment_from_ibn_yang_metadata_api(base, "X#1001#gpon", entry, fake_get)
    assert ap._intent_alignment_state_raw(out) == "misaligned"


def test_pull_alignment_from_metadata_nested_ont_connection_state_key():
    import altiplano as ap

    extra = {
        "ont-connection:ont-connection-state": {
            "alignment-state": "aligned",
            "required-network-state": "active",
        }
    }
    assert ap._pull_alignment_leaves_from_metadata_tree(extra)["alignment-state"] == "aligned"


def test_alignment_from_restconf_payload_for_target_picks_matching_intent_only():
    import altiplano as ap

    payload = {
        "ibn:intent": [
            {
                "intent-type": "ont-connection",
                "target": "OLT-A#1001#gpon",
                "alignment-state": "aligned",
            },
            {
                "intent-type": "ont-connection",
                "target": "OLT-B#1001#gpon",
                "alignment-state": "misaligned",
            },
        ]
    }
    assert ap._alignment_from_restconf_payload_for_target(payload, "OLT-B#1001#gpon") == "misaligned"
    assert ap._alignment_from_restconf_payload_for_target(payload, "OLT-A#1001#gpon") == "aligned"


def test_alignment_from_payload_loose_string_under_intent_subtree():
    import altiplano as ap

    payload = {
        "ibn:intent": {
            "intent-type": "ont-connection",
            "target": "Z#1001#gpon",
            "intent-specific-data": {"meta": {"note": "in-sync"}},
        }
    }
    assert ap._alignment_from_restconf_payload_for_target(payload, "Z#1001#gpon") == "in-sync"


def test_harvest_hinted_alignment_match_token_under_audit_key():
    import altiplano as ap

    tree = {
        "intent-type": "ont-connection",
        "target": "Z#1001#gpon",
        "intent-audit-status": "MATCH",
    }
    assert ap._harvest_hinted_alignment_from_tree(tree) == "aligned"


def test_harvest_hinted_alignment_no_match_generic_status():
    import altiplano as ap

    tree = {"status": "NO_MATCH"}
    assert ap._harvest_hinted_alignment_from_tree(tree) == "misaligned"


def test_build_consulta_create_prefill_from_inventory():
    import altiplano as ap

    prefill = ap.build_consulta_create_prefill(
        access_id="1058485103",
        inventory_resolution={
            "device_location_prefix": "BA_OLTA_ES01_01-9-4-18",
            "suggested_target": "BA_OLTA_ES01_01-9-4-18#1001#gpon",
            "invocator_system": 1001,
        },
    )
    assert prefill["access_id"] == "1058485103"
    assert prefill["sitio"] == "ES01_01"
    assert prefill["ont"] == "18"
    assert prefill["vno"] == "1001"


def test_buscar_access_id_empty_gui_returns_no_match_message(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    monkeypatch.setattr(ap, "buscar_ont_connection_inp_via_gui_access_id_search", lambda *_a, **_kw: [])
    out = ap.buscar_intents_ont_connection_inp("tok", access_id="9999999999")
    assert out["ok"] is True
    assert not out["matches"]
    assert out.get("no_match") is True
    assert out["message"] == "No existe ese Access ID en Altiplano"
    assert out.get("consulta_criterion") == "access_id"


def test_parse_ba_olta_device_prefix_for_form():
    import altiplano as ap

    assert ap.parse_ba_olta_device_prefix_for_form("BA_OLTA_ES01_01-1-1-100") == {
        "sitio": "ES01_01",
        "lt": "1",
        "pon": "1",
        "ont": "100",
    }
    assert ap.parse_ba_olta_device_prefix_for_form("BA_OLTA_ES01_01-1-1-100#1001#gpon") == {
        "sitio": "ES01_01",
        "lt": "1",
        "pon": "1",
        "ont": "100",
    }
    assert ap.parse_ba_olta_device_prefix_for_form("otro") is None


def test_inp_postman_ont_connection_instance_path_matches_nbi_collection():
    """Clave compuesta Postman INP - NBI (intent=<target>,ont-connection con # como %23)."""
    import altiplano as ap

    p = ap._inp_rel_path_ont_connection_instance("BA_OLTA_ES01_01-1-1-7#1001#gpon")
    assert p == "ibn:ibn/intent=BA_OLTA_ES01_01-1-1-7%231001%23gpon,ont-connection"


def test_expand_ont_connection_targets_full_vs_prefix():
    import altiplano as ap

    full = "BA_OLTA_X#1001#gpon"
    assert ap._expand_ont_connection_targets_for_instance_get(full) == [full]
    pref = ap._expand_ont_connection_targets_for_instance_get("BA_OLTA_Y-1-1-7")
    assert len(pref) == len(ap._INP_ONT_CONNECTION_VNO_IDS)
    assert pref[0].endswith("#1001#gpon")


def test_buscar_intents_llama_get_instancia_postman(monkeypatch):
    """La búsqueda por device name debe usar GET por instancia antes del listado global."""
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "get_altiplano_nbi_target",
        lambda _op: ("10.0.0.1", "32443", "inp-altiplano-ac"),
    )
    captured_urls = []

    def fake_get(url, headers=None, params=None, verify=False, timeout=None):
        captured_urls.append(url)

        class R:
            status_code = 404
            text = ""

        return R()

    monkeypatch.setattr(ap.requests, "get", fake_get)

    ap.buscar_intents_ont_connection_inp("tok", device_prefix="BA_OLTA_Z-1-1-7", access_id=None)
    assert captured_urls
    assert "intent=BA_OLTA_Z-1-1-7%231001%23gpon,ont-connection" in captured_urls[0]


def test_borrar_intent_ont_connection_delete_204(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [
                {
                    "target": "BA_OLTA_Z-1-1-7#1001#gpon",
                    "access_id": "1051999888",
                    "intent_uuid": "550e8400-e29b-41d4-a716-446655440000",
                }
            ],
        },
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))

    captured = []

    class R204:
        status_code = 204
        text = ""

    def fake_delete(url, headers=None, params=None, verify=False, timeout=None):
        captured.append((url, params))
        return R204()

    monkeypatch.setattr(ap.requests, "delete", fake_delete)

    out = ap.borrar_intent_ont_connection_inp("tok", device_prefix="BA_OLTA_Z-1-1-7")
    assert out["ok"] is True
    assert out["target"] == "BA_OLTA_Z-1-1-7#1001#gpon"
    assert captured
    assert "intent=BA_OLTA_Z-1-1-7%231001%23gpon,ont-connection" in captured[0][0]


def test_borrar_intent_ont_connection_ambiguous(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [
                {"target": "A#1001#gpon", "access_id": "1"},
                {"target": "A#3001#gpon", "access_id": "2"},
            ],
        },
    )

    out = ap.borrar_intent_ont_connection_inp("tok", device_prefix="A")
    assert out["ok"] is False
    assert "2 intents" in out["message"] or "Se encontraron" in out["message"]
    assert len(out.get("matches") or []) == 2


def test_borrar_intent_buscar_falla(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {"ok": False, "message": "Sin red", "matches": []},
    )

    out = ap.borrar_intent_ont_connection_inp("tok", device_prefix="X")
    assert out["ok"] is False
    assert "Sin red" in out["message"]


def test_normalize_required_network_state_yang_value():
    import altiplano as ap

    assert ap._normalize_required_network_state_yang_value("Active") == "active"
    assert ap._normalize_required_network_state_yang_value("Suspended") == "suspend"
    assert ap._normalize_required_network_state_yang_value("not present") == "delete"
    assert ap._normalize_required_network_state_yang_value("foo") is None


def test_inp_gui_search_intents_filter_body_suspended_uses_suspend():
    import altiplano as ap

    body = ap._inp_gui_search_intents_filter_body(
        filter_required_network_state=["suspended"],
    )
    flt = body["ibn:search-intents"]["filter"]
    assert flt["required-network-state"] == ["suspend"]


def test_match_entry_suspend_maps_to_suspended_ui():
    import altiplano as ap

    entry = {
        "target": "BA_OLTA_X#1001#gpon",
        "intent-type": "ont-connection",
        "required-network-state": "suspend",
    }
    out = ap._match_entry_to_result_dict(entry)
    assert out["network_state"] == "Suspended"
    assert out["required_network_state"] == "suspend"


def test_sincronizar_intent_post_ok(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [
                {
                    "target": "BA_OLTA_Z#1001#gpon",
                    "access_id": "1",
                    "alignment_state": "Aligned",
                    "intent_uuid": None,
                }
            ],
        },
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    monkeypatch.setattr(
        ap, "_inp_synchronize_intent_via_netconf_execute", lambda *_a, **_kw: (False, "")
    )

    def fake_post(url, headers=None, json=None, verify=False, timeout=None, **kwargs):
        class R:
            status_code = 200
            text = '{"ibn:output":{}}'

        return R()

    monkeypatch.setattr(ap.requests, "post", fake_post)
    out = ap.sincronizar_intent_ont_connection_inp("tok", device_prefix="BA_OLTA_Z#1001#gpon")
    assert out["ok"] is True
    assert out["target"] == "BA_OLTA_Z#1001#gpon"


def test_sincronizar_intent_post_fails_on_200_with_top_level_error_list(monkeypatch):
    """Altiplano puede responder 200 con ``error``: [ { ``error-message``: ... } ] (como la GUI)."""
    import json as json_mod
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [
                {
                    "target": "BA_OLTA_ES01_01-10-10-25#3001#gpon",
                    "access_id": "127240110",
                    "intent_uuid": None,
                }
            ],
        },
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    monkeypatch.setattr(
        ap, "_inp_synchronize_intent_via_netconf_execute", lambda *_a, **_kw: (False, "")
    )

    gui_like_msg = (
        "Sync failed for intent of type 'ont-connection' with target "
        "'BA_OLTA_ES01_01-10-10-25#3001#gpon'. Reason: ont-connection intent does not exist "
        "for 3001_BA_OLTA_ES01_01-10-10-17_GPON defined in L1 Scheduler"
    )

    def fake_post(url, headers=None, json=None, verify=False, timeout=None, **kwargs):
        payload = {"error": [{"error-message": gui_like_msg}]}

        class R:
            status_code = 200
            text = json_mod.dumps(payload)

            def json(self):
                return payload

        return R()

    monkeypatch.setattr(ap.requests, "post", fake_post)
    out = ap.sincronizar_intent_ont_connection_inp(
        "tok", device_prefix="BA_OLTA_ES01_01-10-10-25#3001#gpon"
    )
    assert out["ok"] is False
    assert gui_like_msg in out["message"]
    assert out.get("target") == "BA_OLTA_ES01_01-10-10-25#3001#gpon"
    assert "L1 Scheduler" in (out.get("error_detail") or "")


def test_extract_error_message_netconf_execute_har_format():
    import json as json_mod

    import altiplano as ap

    gui_msg = (
        "Sync failed for intent of type 'ont-connection' with target "
        "'BA_OLTA_ES01_01-9-4-18#1001#gpon'.\n Reason: ont-connection intent does not exist "
        "for 1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
    )
    body = {
        "error": True,
        "errorMessage": "RPC error",
        "requestType": "RPC",
        "response": (
            "<rpc-reply><rpc-error><error-message>"
            + gui_msg
            + "</error-message></rpc-error></rpc-reply>"
        ),
    }

    class R:
        status_code = 200
        text = ")]}',\n" + json_mod.dumps(body)

        def json(self):
            return body

    extracted = ap._extract_altiplano_error_message(R())
    assert gui_msg in extracted
    payload = ap._altiplano_error_payload_from_message(extracted)
    assert payload.get("error_detail") and "L1 Scheduler" in payload["error_detail"]


def test_buscar_ont_connection_gui_access_id_returns_multiple(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))

    rows = [
        {
            "intent-type": "ont-connection",
            "target": "BA_OLTA_ES01_01-9-4-11#1001#gpon",
            "required-network-state": "active",
            "aligned": "true",
            "intent-specific-data": {
                "ont-connection:ont-connection": {
                    "access-id": "1058485103",
                    "fiber-name": "BA_OLTA_ES01_01-9-4",
                }
            },
        },
        {
            "intent-type": "ont-connection",
            "target": "BA_OLTA_ES01_01-9-4-18#1001#gpon",
            "required-network-state": "active",
            "aligned": "true",
            "intent-specific-data": {
                "ont-connection:ont-connection": {
                    "access-id": "1058485103",
                    "fiber-name": "BA_OLTA_ES01_01-9-4",
                }
            },
        },
    ]

    def fake_gui(*_a, **_kw):
        return [ap._match_entry_to_result_dict(ap._search_intent_row_to_ont_connection_entry(r)) for r in rows]

    monkeypatch.setattr(ap, "buscar_ont_connection_inp_via_gui_access_id_search", fake_gui)

    out = ap.buscar_intents_ont_connection_inp("tok", access_id="1058485103")
    assert out["ok"] is True
    assert len(out["matches"]) == 2
    assert out.get("search_source") == "gui-search-intents"
    targets = {m["target"] for m in out["matches"]}
    assert "BA_OLTA_ES01_01-9-4-11#1001#gpon" in targets
    assert "BA_OLTA_ES01_01-9-4-18#1001#gpon" in targets


def test_parse_l1_scheduler_missing_ont_connection():
    import altiplano as ap

    detail = (
        "ont-connection intent does not exist for "
        "1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
    )
    parsed = ap.parse_l1_scheduler_missing_ont_connection(detail)
    assert parsed is not None
    assert parsed["device_name"] == "BA_OLTA_ES01_01"
    assert parsed["lt"] == "9"
    assert parsed["pon"] == "4"
    assert parsed["ont"] == "11"
    assert parsed["vno"] == 1001
    assert parsed["target"] == "BA_OLTA_ES01_01-9-4-11#1001#gpon"
    assert parsed["fiber_name"] == "BA_OLTA_ES01_01-9-4"


def test_sincronizar_intent_fail_includes_can_create_missing(monkeypatch):
    import json as json_mod
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [
                {
                    "target": "BA_OLTA_ES01_01-9-4-18#1001#gpon",
                    "access_id": "1058485103",
                    "intent_uuid": None,
                }
            ],
        },
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    monkeypatch.setattr(
        ap, "_inp_synchronize_intent_via_netconf_execute", lambda *_a, **_kw: (False, "")
    )

    gui_like_msg = (
        "Sync failed for intent of type 'ont-connection' with target "
        "'BA_OLTA_ES01_01-9-4-18#1001#gpon'. Reason: ont-connection intent does not exist "
        "for 1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
    )

    def fake_post(url, headers=None, json=None, verify=False, timeout=None, **kwargs):
        payload = {"error": [{"error-message": gui_like_msg}]}

        class R:
            status_code = 200
            text = json_mod.dumps(payload)

            def json(self):
                return payload

        return R()

    monkeypatch.setattr(ap.requests, "post", fake_post)
    out = ap.sincronizar_intent_ont_connection_inp(
        "tok", device_prefix="BA_OLTA_ES01_01-9-4-18#1001#gpon"
    )
    assert out["ok"] is False
    assert out.get("can_create_missing_ont_connection") is True
    assert out["missing_ont_connection"]["ont"] == "11"
    assert out["missing_ont_connection"]["access_id"] == "1058485103"


def test_sincronizar_intent_prefers_netconf_execute(monkeypatch):
    import altiplano as ap

    aligned_match = {
        "target": "BA_OLTA_Z#1001#gpon",
        "access_id": "1",
        "alignment_state": "Aligned",
        "intent_uuid": None,
    }
    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {"ok": True, "matches": [aligned_match]},
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    calls = {"nc": 0, "post": 0}

    def fake_nc(*_a, **_kw):
        calls["nc"] += 1
        return True, ""

    def fake_post(*_a, **_kw):
        calls["post"] += 1
        raise AssertionError("RESTCONF no debe usarse si NETCONF execute OK")

    monkeypatch.setattr(ap, "_inp_synchronize_intent_via_netconf_execute", fake_nc)
    monkeypatch.setattr(ap.requests, "post", fake_post)
    out = ap.sincronizar_intent_ont_connection_inp("tok", device_prefix="BA_OLTA_Z#1001#gpon")
    assert out["ok"] is True
    assert calls["nc"] == 1
    assert calls["post"] == 0


def test_actualizar_required_network_state_patch_ok(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {
            "ok": True,
            "matches": [{"target": "BA_OLTA_Z#1001#gpon", "access_id": "1", "intent_uuid": None}],
        },
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))

    def fake_patch(url, headers=None, params=None, json=None, verify=False, timeout=None):
        class R:
            status_code = 204
            text = ""

        return R()

    monkeypatch.setattr(ap.requests, "patch", fake_patch)
    out = ap.actualizar_required_network_state_ont_connection_inp(
        "tok", "active", device_prefix="BA_OLTA_Z#1001#gpon"
    )
    assert out["ok"] is True
    assert out["required_network_state"] == "active"


def test_netconf_execute_response_ok_rejects_sync_failed_in_xml():
    import json as json_mod

    import altiplano as ap

    xml = (
        "<rpc-reply><error-message>Sync failed for intent. "
        "Reason: ont-connection intent does not exist for "
        "1001_BA_OLTA_SF01_04-7-1-6_GPON defined in L1 Scheduler</error-message></rpc-reply>"
    )
    body = json_mod.dumps({"error": False, "response": xml})

    class R:
        status_code = 200
        text = body

    assert ap._inp_netconf_execute_response_ok(R()) is False


def test_sincronizar_intent_netconf_ok_but_still_misaligned(monkeypatch):
    import altiplano as ap

    misaligned = {
        "target": "BA_OLTA_ES01_01-9-4-18#1001#gpon",
        "access_id": "1058485103",
        "alignment_state": "Misaligned",
        "error_detail": (
            "ont-connection intent does not exist for "
            "1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
        ),
        "can_create_missing_ont_connection": True,
        "missing_ont_connection": {"ont": "11", "target": "BA_OLTA_ES01_01-9-4-11#1001#gpon"},
    }
    monkeypatch.setattr(
        ap,
        "buscar_intents_ont_connection_inp",
        lambda token, **kw: {"ok": True, "matches": [misaligned]},
    )
    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))
    monkeypatch.setattr(
        ap, "_inp_synchronize_intent_via_netconf_execute", lambda *_a, **_kw: (True, "")
    )

    out = ap.sincronizar_intent_ont_connection_inp(
        "tok", device_prefix="BA_OLTA_ES01_01-9-4-18#1001#gpon"
    )
    assert out["ok"] is False
    assert out.get("can_create_missing_ont_connection") is True
    assert out["missing_ont_connection"]["ont"] == "11"


def test_corregir_dependencias_l1_creates_then_syncs(monkeypatch):
    import altiplano as ap

    row_mis = {
        "target": "BA_OLTA_ES01_01-9-4-18#1001#gpon",
        "access_id": "1058485103",
        "alignment_state": "Misaligned",
        "error_detail": (
            "ont-connection intent does not exist for "
            "1001_BA_OLTA_ES01_01-9-4-11_GPON defined in L1 Scheduler"
        ),
    }
    row_ok = dict(row_mis)
    row_ok["alignment_state"] = "Aligned"
    row_ok["error_detail"] = None

    state = {"aligned": False}

    def fake_buscar(token, **kw):
        if state["aligned"]:
            return {"ok": True, "matches": [row_ok]}
        return {"ok": True, "matches": [row_mis]}

    monkeypatch.setattr(ap, "buscar_intents_ont_connection_inp", fake_buscar)

    def fake_create(**kw):
        return {"ok": True, "target": "BA_OLTA_ES01_01-9-4-11#1001#gpon"}

    def fake_sync(token, **kw):
        state["aligned"] = True
        return {"ok": True, "message": "sync ok", "matches": [row_ok]}

    monkeypatch.setattr(ap, "crear_ont_connection_intent", lambda **kw: fake_create(**kw))
    monkeypatch.setattr(ap, "sincronizar_intent_ont_connection_inp", fake_sync)

    out = ap.corregir_dependencias_l1_y_alinear_intent_inp(
        "tok",
        access_id="1058485103",
        device_prefix="BA_OLTA_ES01_01-9-4-18#1001#gpon",
        error_detail=row_mis["error_detail"],
    )
    assert out["ok"] is True
    assert any(s.get("action") == "create" for s in out.get("steps") or [])
    assert any(s.get("action") == "sync" for s in out.get("steps") or [])


def test_advanced_rn_filter_not_present_matches_delete_yang():
    import altiplano as ap

    m = {
        "required_network_state": "delete",
        "network_state": "Not present",
        "alignment_state": "Misaligned",
    }
    assert ap._advanced_rn_filter_matches(m, ["not-present"])
    assert ap._advanced_al_filter_matches(m, ["misaligned"])


def test_filter_matches_advanced_states_and_logic():
    import altiplano as ap

    rows = [
        {
            "target": "BA_OLTA_A#1001#gpon",
            "network_state": "Active",
            "alignment_state": "Aligned",
            "required_network_state": "active",
        },
        {
            "target": "BA_OLTA_B#1001#gpon",
            "network_state": "Not present",
            "alignment_state": "Misaligned",
            "required_network_state": "not-present",
        },
    ]
    out = ap._filter_matches_advanced_states(
        rows,
        filter_required_network_state=["not-present"],
        filter_alignment_state=["misaligned"],
    )
    assert len(out) == 1
    assert out[0]["target"] == "BA_OLTA_B#1001#gpon"


def test_inp_advanced_filters_active_aligned_blocked():
    import altiplano as ap

    assert ap.inp_advanced_filters_active_aligned_blocked(["active"], ["aligned"])
    assert not ap.inp_advanced_filters_active_aligned_blocked(["active"], ["misaligned"])
    assert not ap.inp_advanced_filters_active_aligned_blocked(["suspended"], ["aligned"])
    assert not ap.inp_advanced_filters_active_aligned_blocked([], ["aligned"])


def test_inp_gui_search_intents_filter_body_active_misaligned():
    import altiplano as ap

    body = ap._inp_gui_search_intents_filter_body(
        filter_required_network_state=["active"],
        filter_alignment_state=["misaligned"],
    )
    flt = body["ibn:search-intents"]["filter"]
    assert flt["required-network-state"] == ["active"]
    assert flt["health"] == []
    assert flt["aligned"] == "false"


def test_inp_gui_search_intents_filter_body_both_alignments_omits_aligned():
    import altiplano as ap

    body = ap._inp_gui_search_intents_filter_body(
        filter_alignment_state=["aligned", "misaligned"],
    )
    flt = body["ibn:search-intents"]["filter"]
    assert flt["health"] == []
    assert "aligned" not in flt


def test_buscar_intents_advanced_filters_only(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(ap, "get_altiplano_nbi_target", lambda _op: ("10.0.0.1", "32443", "inp-ac"))

    fake_rows = [
        {
            "intent-type": "ont-connection",
            "target": "BA_OLTA_X#1001#gpon",
            "aligned": "false",
            "required-network-state": "not-present",
            "intent-specific-data": {
                "ont-connection:ont-connection": {"access-id": "aid1"}
            },
        }
    ]

    def fake_gui(*_a, **_kw):
        matches = [
            ap._match_entry_to_result_dict(ap._search_intent_row_to_ont_connection_entry(r))
            for r in fake_rows
        ]
        return matches, False

    monkeypatch.setattr(ap, "buscar_ont_connection_inp_via_gui_filter_search", fake_gui)

    out = ap.buscar_intents_ont_connection_inp(
        "tok",
        filter_required_network_state=["not-present"],
        filter_alignment_state=["misaligned"],
    )
    assert out["ok"] is True
    assert len(out["matches"]) == 1
    assert out.get("search_source") == "gui-search-intents-advanced"
