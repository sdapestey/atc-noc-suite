"""Fechas y día de referencia — estadísticas inventario."""
from datetime import date

from services import inventario_fechas as fechas


def test_parse_inventario_date():
    assert fechas.parse_inventario_date("2026-05-22 10:00:00") == date(2026, 5, 22)
    assert fechas.parse_inventario_date("05-22-2026") == date(2026, 5, 22)
    assert fechas.parse_inventario_date("") is None


def test_parse_snapshot_date():
    assert fechas.parse_snapshot_date("20260521") == date(2026, 5, 21)
    assert fechas.parse_snapshot_date("2026-05-21") == date(2026, 5, 21)


def test_inventario_reference_date_prefers_sftp():
    altas = {date(2026, 5, 22): 99}
    ref = fechas.inventario_reference_date(altas, {}, "20260521", calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_inventario_reference_date_yesterday_when_no_sftp():
    ref = fechas.inventario_reference_date({}, {}, None, calendar_today=date(2026, 5, 22))
    assert ref == date(2026, 5, 21)


def test_clamp_days():
    assert fechas.clamp_days(1) == 7
    assert fechas.clamp_days(9999) == 365
    assert fechas.clamp_days("90") == 90
