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


def parse_snapshot_date(snap: str | None) -> date | None:
    """Fecha desde nombre CSV ``inventarioYYYYMMDD`` o ISO."""
    if not snap:
        return None
    text = str(snap).strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def fecha_alta(provided, reserved) -> date | None:
    return parse_inventario_date(provided) or parse_inventario_date(reserved)


def fecha_baja(cancel, reserved, provided) -> date | None:
    for raw in (cancel, reserved, provided):
        parsed = parse_inventario_date(raw)
        if parsed:
            return parsed
    return None


def inventario_reference_date(
    altas: dict[date, int],
    bajas: dict[date, int],
    sftp_snapshot: str | None = None,
    *,
    calendar_today: date | None = None,
) -> date:
    """
    Día de referencia para la tarjeta «Hoy» (backup diario suele ir un día atrás).
    """
    today = calendar_today or date.today()
    yesterday = today - timedelta(days=1)
    from_sftp = parse_snapshot_date(sftp_snapshot)
    if from_sftp and from_sftp <= today:
        ref = from_sftp
        if ref == today and not int(altas.get(today, 0)) and int(altas.get(yesterday, 0)):
            return yesterday
        return ref
    return yesterday


def clamp_days(value, default: int = 90, *, min_days: int = 7, max_days: int = 365) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_days, min(max_days, n))
