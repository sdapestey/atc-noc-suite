"""Estadísticas altas/bajas de inventario."""
from datetime import date

import services.inventario_estadisticas as est


def test_norm_days_clamped():
    assert est._norm_days(1) == 7
    assert est._norm_days(9999) == 365
    assert est._norm_days("90") == 90


def test_parse_fecha_text():
    assert est._parse_fecha_text("2026-05-22 10:00:00") == date(2026, 5, 22)
    assert est._parse_fecha_text("05-22-2026") == date(2026, 5, 22)
    assert est._parse_fecha_text("") is None


def test_cards_from_daily():
    altas = {date(2026, 5, 22): 3, date(2026, 5, 21): 1}
    bajas = {date(2026, 5, 22): 2}
    cards = est._cards_from_daily(altas, bajas, date(2026, 5, 22))
    assert cards["hoy"]["altas"] == 3
    assert cards["hoy"]["bajas"] == 2
    assert cards["ayer"]["altas"] == 1


def test_reference_date_prefers_sftp_snapshot():
    altas = {date(2026, 5, 22): 99}
    bajas = {}
    ref = est._reference_date(altas, bajas, "20260521", calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_reference_date_falls_back_to_yesterday_not_max_active():
    """Bajas en calendario hoy no deben empujar «Hoy» si las altas van un día atrás."""
    altas = {date(2026, 5, 21): 259}
    bajas = {date(2026, 5, 22): 157, date(2026, 5, 21): 323}
    ref = est._reference_date(altas, bajas, None, calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_reference_date_yesterday_when_no_data():
    ref = est._reference_date({}, {}, None, calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_reference_date_sftp_today_without_altas_uses_yesterday():
    altas = {date(2026, 5, 21): 259}
    bajas = {date(2026, 5, 22): 157}
    ref = est._reference_date(altas, bajas, "20260522", calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_aggregate_period_month():
    points = [
        {"fecha": "2026-05-20", "altas": 1, "bajas": 0},
        {"fecha": "2026-05-21", "altas": 2, "bajas": 1},
        {"fecha": "2026-06-01", "altas": 5, "bajas": 3},
    ]
    monthly = est._aggregate_period(points, "month")
    assert monthly == [
        {"periodo": "2026-05", "altas": 3, "bajas": 1},
        {"periodo": "2026-06", "altas": 5, "bajas": 3},
    ]


def test_stats_from_postgres_mock(monkeypatch):
    class _Cur:
        def __init__(self):
            self._step = 0
            self._sql = ""

        def execute(self, sql, *_a, **_k):
            self._step += 1
            self._sql = sql or ""

        def fetchall(self):
            if "bajada_inventario" in self._sql and "operatorid" in self._sql:
                return [
                    ("aid1", "1001", "2026-05-20", None),
                    ("aid2", "3001", None, "2026-05-21"),
                ]
            if "bajas_de_inventario" in self._sql:
                return [("aid3", "1001", "2026-05-20", None, None)]
            if "bajas_inventario" in self._sql:
                from psycopg2.errors import UndefinedTable

                raise UndefinedTable("missing")
            return []

        @property
        def connection(self):
            return self

        def rollback(self):
            pass

    from contextlib import contextmanager

    @contextmanager
    def _fake_db():
        yield _Cur()

    monkeypatch.setattr(est, "db_cursor", _fake_db)
    monkeypatch.setattr(est, "_sftp_latest_snapshot_date", lambda: None)
    payload = est._compute_estadisticas("day")
    assert payload["source"] == "postgres"
    assert len(payload["series"]) >= 1
    assert payload["cards"]["hoy"]["altas"] >= 0
    assert len(payload.get("by_operator", [])) == 6

    payload_year = est._compute_estadisticas("year")
    assert payload_year["granularity"] == "year"


def test_norm_operador():
    assert est._norm_operador("1001") == "1001"
    assert est._norm_operador("TASA") == ""
    assert est._norm_operador(None) == ""


def test_norm_op_id_maps_atc_vnos():
    assert est._norm_op_id("2805") == "2800"
    assert est._norm_op_id("2806") == "2800"
    assert est._norm_op_id("2800") == "2800"


def test_dashboard_estadisticas_granularity_normalized(monkeypatch):
    captured = {}

    def _fake_compute(granularity):
        captured["granularity"] = granularity
        return {
            "cards": {},
            "daily": [{"fecha": "2026-01-01", "altas": 0, "bajas": 0}],
            "granularity": granularity,
        }

    monkeypatch.setattr(est, "_compute_estadisticas", _fake_compute)
    monkeypatch.setattr(est, "get_inventario_estadisticas_cache_seconds", lambda: 0)
    out = est.dashboard_calidad_inventario_estadisticas(granularity="invalid")
    assert captured["granularity"] == "day"
    assert out["granularity"] == "day"
