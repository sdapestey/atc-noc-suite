"""POST /potencias/batch para consulta masiva."""

import config


def test_potencias_batch_parallel_tokens(client, monkeypatch):
    calls = []

    def fake_rama(rama, *, carga_masiva=False):
        calls.append(rama)
        return [{"AID": rama, "TX": 1.0, "RX": -20.0}]

    monkeypatch.setattr("web.routes.consultar_rama_potencias", fake_rama)

    r = client.post(
        "/potencias/batch",
        json={"values": ["SI03-RATC-0-000405", "SI03-RATC-0-000406"]},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "items" in data
    assert len(data["items"]) == 2
    assert data["items"]["SI03-RATC-0-000405"][0]["AID"] == "SI03-RATC-0-000405"
    assert set(calls) == {"SI03-RATC-0-000405", "SI03-RATC-0-000406"}


def test_potencias_batch_requires_values(client):
    r = client.post("/potencias/batch", json={"values": []})
    assert r.status_code == 400


def test_potencias_batch_caps_workers_to_db_pool(client, monkeypatch):
    """Evita PoolError cuando CONSULTA_POTENCIAS_BATCH_WORKERS > DB_POOL_MAX."""
    import web.routes as routes

    monkeypatch.setattr(config.Config, "DB_POOL_MAX", 3)
    monkeypatch.setattr(routes, "get_consulta_potencias_batch_workers", lambda: 16)

    seen_workers = []

    class FakeExecutor:
        def __init__(self, max_workers=None):
            seen_workers.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, fn, iterable):
            return [fn(x) for x in iterable]

    monkeypatch.setattr(routes, "ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(
        routes,
        "consultar_rama_potencias",
        lambda tok: [{"AID": tok, "TX": 1.0, "RX": -20.0}],
    )

    r = client.post(
        "/potencias/batch",
        json={"values": ["A-RATC-1", "B-RATC-2", "C-RATC-3", "D-RATC-4"]},
    )
    assert r.status_code == 200
    assert seen_workers == [1]  # min(4 tokens, 16 cfg, 3 pool - 2 reserve)


def test_potencias_batch_uses_carga_masiva_throttle(client, monkeypatch):
    import web.routes as routes

    seen = []

    def fake_rama(rama, *, carga_masiva=False):
        seen.append(carga_masiva)
        return [{"AID": rama, "TX": 1.0, "RX": -20.0}]

    monkeypatch.setattr(routes, "consultar_rama_potencias", fake_rama)

    r = client.post(
        "/potencias/batch",
        json={"values": ["ES01-RATC-0-000388", "ES01-RATC-0-000389"]},
    )
    assert r.status_code == 200
    assert seen == [True, True]


def test_potencias_batch_partial_failure_still_200(client, monkeypatch):
    import web.routes as routes

    def fake_rama(tok, *, carga_masiva=False):
        if tok.endswith("-FAIL"):
            raise RuntimeError("simulated")
        return [{"AID": tok, "TX": 1.0, "RX": -21.0}]

    monkeypatch.setattr(routes, "consultar_rama_potencias", fake_rama)

    r = client.post(
        "/potencias/batch",
        json={"values": ["OK-RATC-1", "BAD-RATC-FAIL"]},
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["items"]["OK-RATC-1"][0]["RX"] == -21.0
    assert data["items"]["BAD-RATC-FAIL"] == []
