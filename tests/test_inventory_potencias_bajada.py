"""Potencias para AID solo en aux.bajada_inventario."""

from contextlib import contextmanager

from services import inventory as inv


def _mock_sin_inp(monkeypatch):
    import altiplano as ap

    monkeypatch.setattr(ap, "resolver_ont_connection_inp_por_access_id", lambda *_a: None)
    monkeypatch.setattr(inv, "obtener_alarmas_ont_activas", lambda *_a, **_k: [])


def test_access_id_potencias_fallback_bajada_si_object_name_null_en_inventario(monkeypatch):
    _mock_sin_inp(monkeypatch)
    monkeypatch.setattr(
        inv,
        "consultar_access_id_estructura",
        lambda _aid: {
            "AID": "1058443222",
            "CTO": "SF01-FATC-8-203376",
            "Status": "IN SERVICE",
        },
    )

    inv_row = (
        "1058443222",
        "IN SERVICE",
        "SF01-FATC-8-203376",
        "SF01-RATC-0-001342",
        None,
        "",
        None,
        1001,
    )
    bajada_row = (
        "1058443222",
        1001,
        None,
        None,
        "SF01-FATC-8-203376",
        "SF01-FATC-8-203376",
        "BA_OLTA_SF01_04:1-1-7-1-5",
        "SF01-RATC-0-001342",
        "IN SERVICE",
        None,
        "BA_OLTA_SF01_04:1-1-7-1-5",
        1001,
    )

    @contextmanager
    def fake_cursor():
        class FakeCur:
            def execute(self, sql, params):
                self._sql = sql

            def fetchall(self):
                if "onts_por_cto" in self._sql:
                    return [inv_row]
                return []

            def fetchone(self):
                if "aux.bajada_inventario" in self._sql:
                    return bajada_row
                return None

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_cursor)

    def fake_telem(aid, obj, op_id, *, ne=None):
        assert obj == "BA_OLTA_SF01_04:1-1-7-1-5"
        return {
            "tx": 2.1,
            "rx": -20.3,
            "sn": "ASKY00866826",
            "oper": "UP",
            "admin": "UNLOCKED",
            "health": "Healthy",
            "health_ts": None,
        }

    monkeypatch.setattr(inv, "obtener_telemetry_ont", fake_telem)

    out = inv.consultar_access_id_potencias("1058443222")
    assert out["AID"] == "1058443222"
    assert out["TX"] == 2.1
    assert out["ONT_POSTGRES"] == "BA_OLTA_SF01_04-7-1-5"
    assert out["ONT_ALTIPLANO"] is None
    assert out["ONT_MATCH"] is False


def test_access_id_potencias_fallback_bajada_inventario(monkeypatch):
    _mock_sin_inp(monkeypatch)
    monkeypatch.setattr(inv, "consultar_access_id_estructura", lambda _aid: None)

    row = (
        "1058443222",
        1001,
        None,
        None,
        "SF01-FATC-8-203376",
        "SF01-FATC-8-203376",
        "BA_OLTA_SF01_04:1-1-7-1-5",
        "SF01-RATC-0-001342",
        "IN SERVICE",
        None,
        "BA_OLTA_SF01_04:1-1-7-1-5",
        1001,
    )

    @contextmanager
    def fake_cursor():
        class FakeCur:
            def execute(self, sql, params):
                self._sql = sql
                self._params = params

            def fetchone(self):
                if "aux.bajada_inventario" in self._sql:
                    return row
                return None

        yield FakeCur()

    monkeypatch.setattr(inv, "db_cursor", fake_cursor)

    def fake_telem(aid, obj, op_id, *, ne=None):
        assert aid == "1058443222"
        assert "BA_OLTA_SF01_04" in obj
        assert op_id == 1001
        return {
            "tx": 2.1,
            "rx": -20.3,
            "sn": "ASKY00866826",
            "oper": "UP",
            "admin": "UNLOCKED",
            "health": "Healthy",
            "health_ts": None,
        }

    monkeypatch.setattr(inv, "obtener_telemetry_ont", fake_telem)

    out = inv.consultar_access_id_potencias("1058443222")
    assert out["AID"] == "1058443222"
    assert out["TX"] == 2.1
    assert out["ONT_POSTGRES"] == "BA_OLTA_SF01_04-7-1-5"
    assert out["ONT_ALTIPLANO"] is None
