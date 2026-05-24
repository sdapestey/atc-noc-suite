"""Batch de coordenadas CTO (dashboard RAMA map)."""


def test_consultar_cto_coordenadas_batch_empty():
    from services.inventory import consultar_cto_coordenadas_batch

    assert consultar_cto_coordenadas_batch([]) == {}
    assert consultar_cto_coordenadas_batch(["", "  "]) == {}


def test_consultar_cto_coordenadas_batch_dedupes(monkeypatch):
    from services import inventory

    seen = []

    class FakeCur:
        def execute(self, sql, params):
            seen.append(list(params[0]))

        def fetchall(self):
            return [("A-FATC-1", -34.6, -58.4)]

    class FakeCtx:
        def __enter__(self):
            return FakeCur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(inventory, "db_cursor", lambda: FakeCtx())
    out = inventory.consultar_cto_coordenadas_batch(["A-FATC-1", "A-FATC-1", ""])
    assert out == {"A-FATC-1": {"lat": -34.6, "lon": -58.4}}
    assert seen[0] == ["A-FATC-1"]
