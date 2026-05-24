import services.dashboard_calidad_inventario as calidad


def test_conciliacion_operators_shape():
    assert len(calidad.OPERATORS) == 6
    atc = next(o for o in calidad.OPERATORS if o["id"] == "2800")
    assert atc["label"] == "ATC"
    assert "2805" in calidad.operator_member_ids(atc)
    for op in calidad.OPERATORS:
        assert "vno" in op
        assert op["id"] == op["vno"] or op["label"] == "SION"


def test_conciliacion_response_keys(monkeypatch):
    class _Cur:
        def __init__(self):
            self._step = 0

        def execute(self, *_a, **_k):
            self._step += 1

        def fetchall(self):
            if self._step == 1:
                return [
                    ("1001", 10, 1),
                    ("3001", 20, 2),
                    ("3950", 3, 0),
                    ("4000", 4, 0),
                    ("2800", 6, 1),
                    ("2805", 4, 0),
                    ("962", 5, 0),
                ]
            if self._step == 2:
                return [("1001", 11), ("3001", 21), ("2800", 3), ("2805", 2)]
            return []

        def fetchone(self):
            if self._step == 3:
                return (100,)
            if self._step == 4:
                return (90,)
            return (0,)

    from contextlib import contextmanager

    @contextmanager
    def _fake_db():
        yield _Cur()

    monkeypatch.setattr(calidad, "db_cursor", _fake_db)
    payload = calidad.dashboard_calidad_inventario_conciliacion()
    assert payload["totals"]["connect_master_in_service"] == 90
    assert payload["totals"]["altiplano_activos"] == 100
    tasa = next(o for o in payload["operators"] if o["id"] == "1001")
    assert tasa["connect_master"] == 10
    assert tasa["altiplano"] == 11
    assert tasa["reserved"] == 1
    atc = next(o for o in payload["operators"] if o["id"] == "2800")
    assert atc["connect_master"] == 10
    assert atc["altiplano"] == 5
    assert atc["reserved"] == 1
