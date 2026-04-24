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


def test_estructura_dashboard_lt_includes_pon_from_aux(monkeypatch):
    from services import dashboard_olt as mod

    rows_lt = [
        ("TG01-RATC-0-000308", "TG01-FATC-8-100987", 105, "BA_OLTA_TG01_02-2-15-8", 1001),
    ]
    scripts = [
        rows_lt,                 # query inventario LT
        [("pon",)],             # columns in aux.bajada_inventario
        [("105", "15")],        # explicit PON by access_id
    ]
    monkeypatch.setattr(mod, "db_cursor", _fake_db_cursor_factory(scripts))

    out = mod.estructura_dashboard_lt("BA_OLTA_TG01_02.LT2")
    assert "PONES" in out
    assert "PON 15" in out["PONES"]
    assert "TG01-RATC-0-000308" in out["PONES"]["PON 15"]["RAMAS"]
    assert out["RESUMEN_LT"]["PON_COUNT"] == 1
    assert out["PONES"]["PON 15"]["RESUMEN"]["RAMAS"] == 1
    assert out["PONES"]["PON 15"]["RESUMEN"]["CTO_COUNT"] == 1
    assert out["PONES"]["PON 15"]["RESUMEN"]["ONT_COUNT"] == 1
    ont_row = out["PONES"]["PON 15"]["RAMAS"]["TG01-RATC-0-000308"]["CTOS"]["TG01-FATC-8-100987"][0]
    assert ont_row["ONT"] == "BA_OLTA_TG01_02-2-15-8"


def test_estructura_dashboard_lt_pon_fallback_from_object_name(monkeypatch):
    from services import dashboard_olt as mod

    rows_lt = [
        ("TG01-RATC-0-000308", "TG01-FATC-8-100987", 105, "BA_OLTA_TG01_02-2-15-8", 1001),
    ]
    scripts = [
        rows_lt,                 # query inventario LT
        [],                      # aux.bajada_inventario columns missing/empty
    ]
    monkeypatch.setattr(mod, "db_cursor", _fake_db_cursor_factory(scripts))

    out = mod.estructura_dashboard_lt("BA_OLTA_TG01_02.LT2")
    assert "PONES" in out
    assert "PON 15" in out["PONES"]
    rama = out["PONES"]["PON 15"]["RAMAS"]["TG01-RATC-0-000308"]
    assert "TG01-FATC-8-100987" in rama["CTOS"]
    assert out["RESUMEN_LT"]["PON_COUNT"] == 1
