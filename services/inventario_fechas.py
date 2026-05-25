"""Parseo de fechas y día de referencia para estadísticas de inventario."""
from __future__ import annotations

from datetime import date, datetime, timedelta


def parse_inventario_date(raw) -> date | None:
    """Convierte texto de columnas inventario (provided_date, cancellation_date, etc.)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt, size in (
        ("%Y-%m-%d %H:%M:%S.%f", 26),
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d", 10),
        ("%m-%d-%Y", 10),
    ):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def fecha_alta(provided, reserved) -> date | None:
    return parse_inventario_date(provided) or parse_inventario_date(reserved)


def fecha_baja(cancel, reserved, provided) -> date | None:
    for raw in (cancel, reserved, provided):
        parsed = parse_inventario_date(raw)
        if parsed:
            return parsed
    return None


def parse_reference_date_param(value: str | None) -> date | None:
    """Fecha ISO ``YYYY-MM-DD`` desde query string del dashboard."""
    if value is None:
        return None
    text = str(value).strip()[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def inventario_reference_date_from_data(
    altas: dict[date, int],
    bajas: dict[date, int],
    *,
    calendar_today: date | None = None,
) -> date:
    """
    Último día con actividad en Postgres, con regla de rezago de altas:
    si hoy no hay altas pero ayer sí, se usa ayer.
    """
    today = calendar_today or date.today()
    yesterday = today - timedelta(days=1)
    active = {
        d
        for d in set(altas) | set(bajas)
        if int(altas.get(d, 0)) + int(bajas.get(d, 0)) > 0
    }
    if not active:
        return yesterday
    max_d = min(max(active), today)
    if max_d == today and not int(altas.get(today, 0)) and int(altas.get(yesterday, 0)):
        return yesterday
    return max_d


def inventario_data_date_bounds(
    altas: dict[date, int],
    bajas: dict[date, int],
    *,
    calendar_today: date | None = None,
    window_days: int = 365,
) -> tuple[date, date]:
    """Rango [min, max] para el selector de fecha (ventana de consulta en Postgres)."""
    today = calendar_today or date.today()
    window_start = today - timedelta(days=window_days - 1)
    active = {
        d
        for d in set(altas) | set(bajas)
        if int(altas.get(d, 0)) + int(bajas.get(d, 0)) > 0 and window_start <= d <= today
    }
    min_bound = min(active) if active else window_start
    return min_bound, today


def resolve_reference_date(
    altas: dict[date, int],
    bajas: dict[date, int],
    selected: date | None = None,
    *,
    calendar_today: date | None = None,
    window_days: int = 365,
) -> date:
    """Día de referencia efectivo: selección del usuario acotada al rango disponible."""
    auto = inventario_reference_date_from_data(altas, bajas, calendar_today=calendar_today)
    min_d, max_d = inventario_data_date_bounds(
        altas, bajas, calendar_today=calendar_today, window_days=window_days
    )
    if selected is None:
        return auto
    if selected < min_d:
        return min_d
    if selected > max_d:
        return max_d
    return selected


def clamp_days(value, default: int = 90, *, min_days: int = 7, max_days: int = 365) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_days, min(max_days, n))
