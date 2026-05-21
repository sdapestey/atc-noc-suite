from contextlib import contextmanager


def _fake_db_cursor_with_row(row):
    class FakeCur:
        def execute(self, _sql, _params=None):
            self._row = row

        def fetchone(self):
            return self._row

    @contextmanager
    def ctx():
        yield FakeCur()

    return ctx


def test_consultar_cto_direccion_postal_normalizes_zone_code(monkeypatch):
    import services.inventory as inv

    monkeypatch.setattr(
        inv,
        "db_cursor",
        _fake_db_cursor_with_row(("Alvear, 2464", "BA SAFE", 0)),
    )

    out = inv.consultar_cto_direccion_postal("SF01-FATC-8-100189")
    assert out == "Alvear 2464 (BA San Fernando)"


def test_consultar_cto_direccion_postal_maps_escobar_code(monkeypatch):
    import services.inventory as inv

    monkeypatch.setattr(
        inv,
        "db_cursor",
        _fake_db_cursor_with_row(("Mitre 1200", "BA ESCO", 0)),
    )

    out = inv.consultar_cto_direccion_postal("XX01-FATC-8-1")
    assert out == "Mitre 1200 (BA Escobar)"
