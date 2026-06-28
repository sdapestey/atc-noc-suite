from contextlib import contextmanager
from pathlib import Path


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _query, _params=None):
        pass

    def fetchall(self):
        return list(self._rows)


def test_dashboard_olt_totales_agrega_operadores(monkeypatch):
    from services import dashboard_olt as mod

    monkeypatch.setattr(
        mod,
        "dashboard_rama_totales",
        lambda: {"RAMAS": 10, "CTO": 20, "ONT": 30},
    )

    @contextmanager
    def _ctx():
        yield _FakeCursor([(1001, 5), (3001, 3), (9999, 99)])

    monkeypatch.setattr(mod, "db_cursor", _ctx)
    monkeypatch.setattr(mod, "get_cached_olt_totales", lambda _ttl, factory: factory())

    out = mod.dashboard_olt_totales()
    assert out["RAMAS"] == 10
    assert out["CTO"] == 20
    assert out["ONT"] == 30
    assert out["ont_por_operador"] == [("TASA", 5), ("DIRECTV", 3)]


def test_dashboard_olt_template_grand_totals_row():
    tpl = Path("templates/dashboard_olt.html").read_text(encoding="utf-8")
    assert 'id="olt-grand-totals-row"' in tpl
    assert "olt_totales.RAMAS" in tpl
    assert "olt_totales.ont_por_operador" in tpl
    assert 'id="pon-selection-summary" hidden' in tpl
    assert 'olt-selection-operadores-label">Operador:</span>' not in tpl
    assert "olt-metric-pill olt-metric-pill--ramas" in tpl
