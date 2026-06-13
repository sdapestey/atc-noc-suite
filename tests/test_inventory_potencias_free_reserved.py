"""Potencias: FREE no consulta Altiplano; RESERVED sí (consultas puntuales)."""

from contextlib import contextmanager

from services import inventory as inv


def test_potencias_filas_omite_altiplano_free_y_reserved(monkeypatch):
    calls = []

    def capture(ne, onts, carga_masiva=False):
        calls.append((ne, list(onts)))
        return {"11": (1.0, -16.0)}

    monkeypatch.setattr(inv, "obtener_potencias_por_cto", capture)

    rows = [
        # access_id, status, cto, rama, object_raw, object_ui, serial, invocator
        (10, "FREE", "C", "R", None, "", None, None),
        (
            11,
            "IN SERVICE",
            "C",
            "R",
            "BA_OLTA_ES01_01-1-1-1",
            "BA_OLTA_ES01_01-1-1-1",
            "SN1",
            1,
        ),
        (12, "RESERVED", "C", "R", None, "", None, None),
    ]
    out = inv._potencias_desde_filas_ont_cto(rows)
    assert out[0]["AID"] == "10" and out[0]["TX"] is None and out[0]["RX"] is None
    assert out[1]["AID"] == "11" and out[1]["TX"] == 1.0 and out[1]["RX"] == -16.0
    assert out[2]["AID"] == "12" and out[2]["TX"] is None and out[2]["RX"] is None
    assert len(calls) == 1
    _ne, onts = calls[0]
    assert onts == [("11", "BA_OLTA_ES01_01-1-1-1", 1)]


def test_access_id_potencias_retorna_none_si_status_free(monkeypatch):
    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {"AID": "99", "CTO": "C1", "Status": "FREE"},
    )

    @contextmanager
    def fake_cursor():
        class FakeCur:
            def execute(self, *_):
                pass

            def fetchall(self):
                return [
                    (99, "FREE", "C1", "R1", None, "", None, None),
                ]

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_cursor)

    calls = []

    def boom(*_a, **_k):
        calls.append(1)

    monkeypatch.setattr(inv, "obtener_potencias_por_cto", boom)

    out = inv.consultar_access_id_potencias("99")
    assert out["AID"] == "99"
    assert out["TX"] is None
    assert out["ONT_MATCH"] is False
    assert calls == []


def test_access_id_potencias_usa_aid_canonico_para_lookup(monkeypatch):
    """El dict de Altiplano usa el access_id tal como viene en inventario; el input puede ir en minúsculas."""
    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {
            "AID": "FES_A5_23",
            "CTO": "SM01-FATC-8-101444",
            "Status": "IN SERVICE",
        },
    )

    @contextmanager
    def fake_cursor():
        class FakeCur:
            def execute(self, *_):
                pass

            def fetchall(self):
                return [
                    (
                        "FES_A5_23",
                        "IN SERVICE",
                        "SM01-FATC-8-101444",
                        "SM01-RATC-0-001592",
                        "BA_OLTA_SM01_05-10-3-21:1-1",
                        "BA_OLTA_SM01_05-10-3-21",
                        "SN1",
                        2800,
                    ),
                ]

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_cursor)

    def fake_telem(aid, obj, op_id, *, ne=None):
        assert aid == "FES_A5_23"
        assert "BA_OLTA_SM01_05" in obj
        assert op_id == 2800
        return {
            "tx": 2.5,
            "rx": -19.3,
            "sn": "ALCLF00DBEEF",
            "oper": "UP",
            "admin": "UNLOCKED",
            "health": "Healthy",
            "health_ts": None,
        }

    monkeypatch.setattr(inv, "obtener_telemetry_ont", fake_telem)
    monkeypatch.setattr(inv, "obtener_alarmas_ont_activas", lambda *_a, **_k: [])

    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "resolver_ont_connection_inp_por_access_id",
        lambda _aid: {
            "object_name": "BA_OLTA_SM01_05-10-3-21",
            "object_name_ui": "BA_OLTA_SM01_05-10-3-21",
            "operator_id": 2800,
        },
    )

    out = inv.consultar_access_id_potencias("fes_a5_23")
    assert out["AID"] == "FES_A5_23"
    assert out["TX"] == 2.5
    assert out["ONT_POSTGRES"] == "BA_OLTA_SM01_05-10-3-21"
    assert out["ONT_ALTIPLANO"] == "BA_OLTA_SM01_05-10-3-21"
    assert out["ONT_MATCH"] is True
    assert out["ONT"] == "BA_OLTA_SM01_05-10-3-21"


def test_access_id_potencias_prefiere_device_name_inp_sobre_postgres(monkeypatch):
    """Tras cambio de CTO, INP tiene el target actual; Postgres puede quedar desactualizado."""
    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {
            "AID": "1059164760",
            "CTO": "SM02-FATC-8-123",
            "Status": "IN SERVICE",
            "ONT": "BA_OLTA_SM02_05-3-1-6",
            "SN": "ALCL00000001",
        },
    )

    @contextmanager
    def fake_cursor():
        class FakeCur:
            def execute(self, *_):
                pass

            def fetchall(self):
                return [
                    (
                        "1059164760",
                        "IN SERVICE",
                        "SM02-FATC-8-123",
                        "SM02-RATC-0-000100",
                        "BA_OLTA_SM02_05:1-1-3-1-6",
                        "BA_OLTA_SM02_05-3-1-6",
                        "ALCL00000001",
                        1001,
                    ),
                ]

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_cursor)

    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "resolver_ont_connection_inp_por_access_id",
        lambda _aid: {
            "object_name": "BA_OLTA_SM02_05-5-3-12",
            "object_name_ui": "BA_OLTA_SM02_05-5-3-12",
            "operator_id": 1001,
            "target": "BA_OLTA_SM02_05-5-3-12#1001#gpon",
        },
    )
    monkeypatch.setattr(
        ap,
        "buscar_ont_connection_operador_por_target_exact",
        lambda *_a, **_k: {"ok": True, "matches": []},
    )

    seen = {}

    def fake_telem(aid, obj, op_id, *, ne=None):
        seen["obj"] = obj
        seen["op_id"] = op_id
        return {
            "tx": 2.0,
            "rx": -18.0,
            "sn": "ALCL00000001",
            "oper": "UP",
            "admin": "UNLOCKED",
            "health": "Healthy",
            "health_ts": None,
        }

    monkeypatch.setattr(inv, "obtener_telemetry_ont", fake_telem)
    monkeypatch.setattr(inv, "obtener_alarmas_ont_activas", lambda *_a, **_k: [])

    out = inv.consultar_access_id_potencias("1059164760")
    assert seen["obj"] == "BA_OLTA_SM02_05-5-3-12"
    assert seen["op_id"] == 1001
    assert out["ONT_POSTGRES"] == "BA_OLTA_SM02_05-3-1-6"
    assert out["ONT_ALTIPLANO"] == "BA_OLTA_SM02_05-5-3-12"
    assert out["ONT_MATCH"] is False
    assert out["ONT"] == "BA_OLTA_SM02_05-5-3-12"
    assert out["ALTIPLANO_VNO"] == "BA_OLTA_SM02_05-5-3-12#1001#gpon"
    assert out["ALTIPLANO_TASA_COMPOSITE"] is None
    assert out["RX"] == -18.0


def test_altiplano_vno_payload_desde_inp_hit():
    from services.inventory import _altiplano_vno_payload

    out = _altiplano_vno_payload(
        {
            "inp_device_name": "BA_OLTA_TG02_03-2-12-9",
            "target": "BA_OLTA_TG02_03-2-12-9#1001#gpon",
        },
        operator="DTV",
    )
    assert out["ALTIPLANO_VNO"] == "BA_OLTA_TG02_03-2-12-9#1001#gpon"
    assert out["ALTIPLANO_TASA_COMPOSITE"] is None


def test_altiplano_tasa_composite_desde_operador(monkeypatch):
    from services.inventory import _fetch_tasa_composite_detail

    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_ont_connection_operador_por_target_exact",
        lambda op, head, access_id=None: {
            "ok": True,
            "matches": [
                {
                    "intent_type": "tasa-composite",
                    "target": "BA_OLTA_TG02_03-2-12-9#HSI-1501",
                    "intent-specific-data": {
                        "tasa-composite:hsi": {
                            "downstream-profile": "TASA_SH300MB_DN",
                            "upstream-profile": "TASA_BW300MB_UP",
                        }
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        ap,
        "_hsi_from_ibn_row",
        lambda row: {
            "downstream_profile": "TASA_SH300MB_DN",
            "upstream_profile": "TASA_BW300MB_UP",
        },
    )
    detail = _fetch_tasa_composite_detail(
        "TASA",
        "BA_OLTA_TG02_03-2-12-9",
        access_id="1059164760",
    )
    assert detail["target"] == "BA_OLTA_TG02_03-2-12-9#HSI-1501"
    assert detail["tasa_hsi"]["downstream_profile"] == "TASA_SH300MB_DN"


def test_altiplano_tasa_composite_hsi_desde_tasa_hsi_key(monkeypatch):
    from services.inventory import _fetch_tasa_composite_detail

    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_ont_connection_operador_por_target_exact",
        lambda op, head, access_id=None: {
            "ok": True,
            "matches": [
                {
                    "intent_type": "tasa-composite",
                    "target": "BA_OLTA_TG02_03-2-12-9#HSI-1501",
                    "tasa_hsi": {
                        "downstream_profile": "TASA_SH10MB_DN",
                        "upstream_profile": "TASA_BW10MB_UP",
                    },
                }
            ],
        },
    )
    detail = _fetch_tasa_composite_detail(
        "TASA",
        "BA_OLTA_TG02_03-2-12-9",
        access_id="1059164760",
    )
    assert detail["target"] == "BA_OLTA_TG02_03-2-12-9#HSI-1501"
    assert detail["tasa_hsi"]["upstream_profile"] == "TASA_BW10MB_UP"


def test_altiplano_tasa_composite_hsi_restconf_fallback(monkeypatch):
    from services.inventory import _fetch_tasa_composite_detail

    import altiplano as ap

    monkeypatch.setattr(
        ap,
        "buscar_ont_connection_operador_por_target_exact",
        lambda op, head, access_id=None: {
            "ok": True,
            "matches": [
                {
                    "intent_type": "tasa-composite",
                    "target": "BA_OLTA_TG02_03-2-12-9#HSI-1501",
                }
            ],
        },
    )
    monkeypatch.setattr(
        ap,
        "fetch_tasa_composite_hsi_nbi",
        lambda op, tgt: {
            "downstream_profile": "TASA_SH100MB_DN",
            "upstream_profile": "TASA_BW100MB_UP",
        },
    )
    detail = _fetch_tasa_composite_detail("TASA", "BA_OLTA_TG02_03-2-12-9")
    assert detail["tasa_hsi"]["downstream_profile"] == "TASA_SH100MB_DN"


def test_ont_compare_payload_match():
    assert inv._ont_compare_payload(
        "BA_OLTA_X:1-1-2-3-4", "BA_OLTA_X-2-3-4"
    )["ONT_MATCH"] is True
    assert inv._ont_compare_payload("BA_OLTA_SM01_05-10-3-21:1-1", "BA_OLTA_SM01_05-10-3-21")[
        "ONT_MATCH"
    ] is True
    assert inv._ont_compare_payload("BA_A-1-1", "")["ONT_MATCH"] is False
    assert inv._ont_compare_payload("", "")["ONT_POSTGRES"] is None


def test_altiplano_por_ont_varias_ctos_en_paralelo(monkeypatch):
    """Histórico Consultar RX: varias CTO en la misma RAMA → un Altiplano por CTO en paralelo."""
    calls = []

    def capture(ne, onts):
        calls.append((ne, len(onts)))
        if not onts:
            return {}
        return {str(onts[0][0]): (-20.0, -19.0)}

    monkeypatch.setattr(inv, "obtener_potencias_por_cto", capture)

    obj_a = "BA_OLTA_ES01_01:1-1-2-1-1"
    obj_b = "BA_OLTA_ES01_01:1-1-2-1-2"
    rows = [
        (100, "IN SERVICE", "CTO-A", "R", obj_a, obj_a, None, 1),
        (101, "IN SERVICE", "CTO-B", "R", obj_b, obj_b, None, 1),
    ]
    out = inv._altiplano_potencias_grupos_cto_paralelo(rows)
    assert len(calls) == 2
    assert len(out) == 2
    assert out[0]["rx_dbm"] == -19.0
    assert out[1]["rx_dbm"] == -19.0
