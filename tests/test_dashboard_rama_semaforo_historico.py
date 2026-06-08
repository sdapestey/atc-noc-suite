"""Semáforos RAMA en dashboard RAMA/CTO desde histórico Postgres."""
from datetime import datetime


def test_semaforo_historico_por_ramas_clasifica(monkeypatch):
    import services.historico_potencias as historico

    ramas = ["SF01-RATC-G-000001", "SF01-RATC-G-000002"]
    monkeypatch.setattr(
        historico,
        "_batch_pon_desde_ramas",
        lambda _ramas: {
            "SF01-RATC-G-000001": "BA_OLTA_SF01_01-1-1",
            "SF01-RATC-G-000002": "BA_OLTA_SF01_01-1-2",
        },
    )
    monkeypatch.setattr(
        historico,
        "_batch_ont_keys_por_ramas",
        lambda _ramas: {
            "SF01-RATC-G-000001": {"19", "16"},
            "SF01-RATC-G-000002": {"6"},
        },
    )

    rows = [
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_SF01_01-1-1-19", -28.0),
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_SF01_01-1-1-16", -26.0),
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_SF01_01-1-1-99", -22.0),
        (datetime(2026, 6, 6, 20, 31, 13), "v1__t_BA_OLTA_SF01_01-1-2-6", -22.5),
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

    payload = historico.semaforo_historico_por_ramas(ramas)
    assert payload["ok"] is True
    r1 = payload["ramas"]["SF01-RATC-G-000001"]
    assert r1["ONT_CON_RX"] == 2
    assert r1["ROJAS"] == 1
    assert r1["AMARILLAS"] == 1
    assert r1["VERDES"] == 0
    r2 = payload["ramas"]["SF01-RATC-G-000002"]
    assert r2["ONT_CON_RX"] == 1
    assert r2["VERDES"] == 1


def test_api_dash_rama_semaforo_historico(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "semaforo_historico_por_ramas",
        lambda ramas: {
            "ok": True,
            "mode": "ultima_guardada",
            "source": "historico",
            "ramas": {
                ramas[0]: {
                    "ROJAS": 1,
                    "AMARILLAS": 2,
                    "VERDES": 10,
                    "ONT_CON_RX": 13,
                }
            },
        },
    )

    r = client.post(
        "/dashboard/rama/semaforo-historico",
        data={"ramas": "SF01-RATC-G-000001"},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ramas"]["SF01-RATC-G-000001"]["VERDES"] == 10


def test_merge_semaforo_historico_chunk_keeps_nonempty():
    import services.historico_potencias as historico

    merged = {
        "A": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "ONT_CON_RX": 0},
    }
    historico._merge_semaforo_historico_chunk(merged, {
        "A": {"ROJAS": 1, "AMARILLAS": 0, "VERDES": 2, "ONT_CON_RX": 3},
        "B": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "ONT_CON_RX": 0},
    })
    assert merged["A"]["VERDES"] == 2
    historico._merge_semaforo_historico_chunk(merged, {
        "A": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "ONT_CON_RX": 0},
    })
    assert merged["A"]["VERDES"] == 2


def test_semaforo_historico_por_ramas_all_moreno_includes_000200(monkeypatch):
    import services.historico_potencias as historico

    ramas = [f"MR01-RATC-0-{i:06d}" for i in range(200, 260)]
    ramas += [f"MR01-RATC-0-{i:06d}" for i in range(300, 360)]

    def _fake_uncached(requested):
        out = {
            r: {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "ONT_CON_RX": 0}
            for r in requested
        }
        if "MR01-RATC-0-000200" in requested:
            out["MR01-RATC-0-000200"] = {
                "ROJAS": 0, "AMARILLAS": 1, "VERDES": 12, "ONT_CON_RX": 13,
            }
        return {"ok": True, "mode": "ultima_guardada", "source": "historico", "ramas": out}

    monkeypatch.setattr(historico, "_semaforo_historico_por_ramas_uncached", _fake_uncached)
    monkeypatch.setattr(historico, "get_cached_historico_potencias", lambda _ttl, _key, factory: factory())

    payload = historico.semaforo_historico_por_ramas(ramas)
    assert payload["ramas"]["MR01-RATC-0-000200"]["ONT_CON_RX"] == 13


def test_api_dash_rama_semaforo_historico_requires_ramas(client):
    r = client.post("/dashboard/rama/semaforo-historico", data={})
    assert r.status_code == 400
