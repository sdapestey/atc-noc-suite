from contextlib import contextmanager


class _FakeCursor:
    def __init__(self, scripts):
        self._scripts = scripts
        self._idx = -1
        self._rows = []

    def execute(self, _query, _params=None):
        self._idx += 1
        self._rows = self._scripts[self._idx]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]


def _fake_db_cursor_factory(scripts):
    @contextmanager
    def _ctx():
        yield _FakeCursor(scripts)

    return _ctx


def test_access_id_uses_serial_number_for_sn(monkeypatch):
    from services import inventory as inv

    scripts = [
        [
            (
                "105", "IN SERVICE", "TG01-FATC-8-100987", "TG01-RATC-0-000308",
                "BA_OLTA_TG01_02:1-1-2-15-8", "BA_OLTA_TG01_02-2-15-8",
                "ALCLF00DBEEF", 1001,
            )
        ]
    ]
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_factory(scripts))

    out = inv.consultar_access_id_estructura("105")
    assert out is not None
    assert out["SN"] == "ALCLF00DBEEF"
    assert out["ONT"] == "BA_OLTA_TG01_02-2-15-8"


def test_access_id_sn_fallback_to_object_name_ui(monkeypatch):
    from services import inventory as inv

    scripts = [
        [
            (
                "105", "IN SERVICE", "TG01-FATC-8-100987", "TG01-RATC-0-000308",
                "BA_OLTA_TG01_02:1-1-2-15-8", "BA_OLTA_TG01_02-2-15-8",
                None, 1001,
            )
        ]
    ]
    monkeypatch.setattr(inv, "db_cursor", _fake_db_cursor_factory(scripts))

    out = inv.consultar_access_id_estructura("105")
    assert out is not None
    assert out["SN"] == "BA_OLTA_TG01_02-2-15-8"
