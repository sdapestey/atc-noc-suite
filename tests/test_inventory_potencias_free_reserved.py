"""Potencias: FREE/RESERVED no consultan Altiplano."""

from contextlib import contextmanager

from services import inventory as inv


def test_potencias_filas_omite_altiplano_free_y_reserved(monkeypatch):
    calls = []

    def capture(ne, onts):
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
        lambda _aid: {"AID": "99", "CTO": "C1", "Status": "IN SERVICE"},
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
    assert out == {
        "AID": "99",
        "TX": None,
        "RX": None,
        "SN": None,
        "ALARMAS": [],
        "alarmas_label": None,
        "NV_STATUS": None,
    }
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

    out = inv.consultar_access_id_potencias("fes_a5_23")
    assert out == {
        "AID": "FES_A5_23",
        "TX": 2.5,
        "RX": -19.3,
        "SN": "ALCLF00DBEEF",
        "ALARMAS": [],
        "alarmas_label": "Sin Alarmas",
        "OPERADOR": "ATC",
        "NV_STATUS": {
            "health": "Healthy",
            "health_ts": None,
            "oper": "UP",
            "admin": "UNLOCKED",
            "pon_admin": None,
            "pon_index": "3",
            "channel_partition": "BA_OLTA_SM01_05-10-3_CPART_GPON",
            "alarms_active": 0,
        },
    }


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
