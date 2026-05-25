"""Fechas y día de referencia — estadísticas inventario."""
from datetime import date

from services import inventario_fechas as fechas


def test_parse_inventario_date():
    assert fechas.parse_inventario_date("2026-05-22 10:00:00") == date(2026, 5, 22)
    assert fechas.parse_inventario_date("05-22-2026") == date(2026, 5, 22)
    assert fechas.parse_inventario_date("") is None


def test_parse_reference_date_param():
    assert fechas.parse_reference_date_param("2026-05-21") == date(2026, 5, 21)
    assert fechas.parse_reference_date_param("invalid") is None
    assert fechas.parse_reference_date_param("") is None


def test_reference_date_from_data_uses_latest_activity():
    altas = {date(2026, 5, 22): 99}
    ref = fechas.inventario_reference_date_from_data(altas, {}, calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 22)


def test_reference_date_from_data_lag_when_no_altas_today():
    altas = {date(2026, 5, 21): 259}
    bajas = {date(2026, 5, 22): 157, date(2026, 5, 21): 323}
    ref = fechas.inventario_reference_date_from_data(
        altas, bajas, calendar_today=date(2026, 5, 22)
    )
    assert ref == date(2026, 5, 21)


def test_reference_date_yesterday_when_no_data():
    ref = fechas.inventario_reference_date_from_data({}, {}, calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_data_date_bounds_max_is_calendar_today():
    altas = {date(2026, 5, 20): 1}
    bajas = {}
    min_d, max_d = fechas.inventario_data_date_bounds(
        altas, bajas, calendar_today=date(2026, 5, 24)
    )
    assert max_d == date(2026, 5, 24)
    assert min_d == date(2026, 5, 20)


def test_resolve_reference_date_clamps_future_to_today():
    altas = {date(2026, 5, 20): 1, date(2026, 5, 22): 5}
    bajas = {date(2026, 5, 21): 2}
    ref = fechas.resolve_reference_date(
        altas,
        bajas,
        date(2026, 6, 1),
        calendar_today=date(2026, 5, 24),
    )
    assert ref == date(2026, 5, 24)


def test_clamp_days():
    assert fechas.clamp_days(1) == 7
    assert fechas.clamp_days(9999) == 365
    assert fechas.clamp_days("90") == 90
