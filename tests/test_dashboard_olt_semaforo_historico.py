"""Semáforos LT en dashboard OLT desde histórico Postgres."""
from datetime import datetime


def test_semaforo_historico_por_lts_clasifica_y_peor(monkeypatch):
    import services.historico_potencias as historico

    rows = [
        (datetime(2026, 6, 1, 10, 0), "BA_OLTA_ES01_01:1-1-1-1-1", -28.0),
        (datetime(2026, 6, 1, 11, 0), "BA_OLTA_ES01_01:1-1-1-1-2", -26.0),
        (datetime(2026, 6, 1, 12, 0), "BA_OLTA_ES01_01:1-1-1-1-3", -22.0),
        (datetime(2026, 6, 1, 13, 0), "BA_OLTA_ES01_01:1-1-2-1-1", -30.0),
        (datetime(2026, 6, 1, 14, 0), "BA_OLTA_ES01_01:1-1-2-1-1", -100.0),
    ]

    class _Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return rows

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(historico, "db_cursor", lambda: _Ctx())
    monkeypatch.setattr(historico, "get_cached_historico_potencias", lambda _ttl, _key, factory: factory())

    payload = historico.semaforo_historico_por_lts(
        ["BA_OLTA_ES01_01.LT1", "BA_OLTA_ES01_01.LT2"],
    )
    assert payload["ok"] is True
    assert payload["mode"] == "ultima_guardada"
    lt1 = payload["lts"]["BA_OLTA_ES01_01.LT1"]
    assert lt1["ROJAS"] == 1
    assert lt1["AMARILLAS"] == 1
    assert lt1["VERDES"] == 1
    assert lt1["PEOR_RX"] == -28.0
    assert lt1["ONT_CON_RX"] == 3
    lt2 = payload["lts"]["BA_OLTA_ES01_01.LT2"]
    assert lt2["ROJAS"] == 1
    assert lt2["PEOR_RX"] == -30.0


def test_api_dash_olt_semaforo_historico(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "semaforo_historico_por_lts",
        lambda lts, days=None: {
            "ok": True,
            "mode": "ultima_guardada",
            "source": "historico",
            "lts": {
                lts[0]: {
                    "ROJAS": 2,
                    "AMARILLAS": 0,
                    "VERDES": 5,
                    "PEOR_RX": -29.5,
                    "ONT_CON_RX": 7,
                }
            },
        },
    )

    r = client.post(
        "/dashboard/olt/semaforo-historico",
        data={"lts": "BA_OLTA_ES01_01.LT1"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["lts"]["BA_OLTA_ES01_01.LT1"]["VERDES"] == 5


def test_api_dash_olt_semaforo_historico_requires_lts(client):
    r = client.post("/dashboard/olt/semaforo-historico", data={})
    assert r.status_code == 400


def test_lt_key_from_potencias_objectname_colon_format():
    import services.historico_potencias as historico

    assert historico._lt_key_from_potencias_objectname("BA_OLTA_ES01_01:1-1-2-1-4") == "BA_OLTA_ES01_01.LT2"
    assert historico._lt_key_from_potencias_objectname("BA_OLTA_ES01_01-2-1-6") == "BA_OLTA_ES01_01.LT2"
    assert historico._lt_key_from_potencias_objectname("BA_OLTA_ES01_01-1-4-2-3:1-1") == "BA_OLTA_ES01_01.LT1"
    assert historico._lt_key_from_potencias_objectname("v1__t_BA_OLTA_MR01_01-1-10-19") == "BA_OLTA_MR01_01.LT1"


def test_semaforo_historico_handles_v1_telemetry_prefix(monkeypatch):
    from datetime import datetime

    import services.historico_potencias as historico

    rows = [
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_MR01_01-1-10-19", -18.9),
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_MR01_01-1-10-16", -27.7),
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_MR01_01-2-3-6", -22.5),
    ]

    class _Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return rows

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(historico, "db_cursor", lambda: _Ctx())
    monkeypatch.setattr(historico, "get_cached_historico_potencias", lambda _ttl, _key, factory: factory())

    payload = historico.semaforo_historico_por_lts(["BA_OLTA_MR01_01.LT1", "BA_OLTA_MR01_01.LT2"])
    lt1 = payload["lts"]["BA_OLTA_MR01_01.LT1"]
    assert lt1["ONT_CON_RX"] == 2
    assert lt1["ROJAS"] == 1
    assert lt1["VERDES"] == 1
    assert lt1["PEOR_RX"] == -27.7
    assert payload["lts"]["BA_OLTA_MR01_01.LT2"]["ONT_CON_RX"] == 1


def test_historico_ultima_rx_query_matches_both_objectname_formats():
    from queries import QUERIES

    sql = QUERIES["historico_ultima_rx_por_olt"]
    assert "DISTINCT ON" in sql
    assert "objectname LIKE %s OR objectname LIKE %s" in sql
    assert "regexp_replace(objectname, '^v[0-9]+__t_', '')" in sql
    assert "make_interval" not in sql
