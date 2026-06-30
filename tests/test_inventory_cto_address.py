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


def test_consultar_cto_tag_nfc_desde_inventario(monkeypatch):
    import services.inventory as inv

    monkeypatch.setattr(
        inv,
        "db_cursor",
        _fake_db_cursor_with_row(("04A5E2A22C5E80",)),
    )

    out = inv.consultar_cto_tag_nfc("SF01-FATC-8-102397")
    assert out == "04A5E2A22C5E80"


def test_consultar_cto_tag_nfc_vacio_si_sin_registro(monkeypatch):
    import services.inventory as inv

    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_with_row(None))

    assert inv.consultar_cto_tag_nfc("SF01-FATC-8-102397") is None
    assert inv.consultar_cto_tag_nfc("") is None
