"""Estadísticas de altas/bajas de inventario (backup SFTP / aux.bajada_inventario)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from config import (
    get_inventario_estadisticas_cache_seconds,
    get_inventario_sftp_config,
)
from psycopg2.errors import UndefinedTable

from db import db_cursor
from services.domain import (
    CALIDAD_OPERATORS,
    calidad_operator_label,
    canonical_calidad_operator_id,
)
from services.dashboard_cache import get_cached_inventario_estadisticas
from services.inventario_fechas import (
    clamp_days,
    fecha_alta,
    fecha_baja,
    inventario_reference_date,
    parse_inventario_date,
    parse_snapshot_date,
)

# Alias para tests existentes
_parse_fecha_text = parse_inventario_date
_parse_snapshot_date = parse_snapshot_date
_reference_date = inventario_reference_date
_norm_days = clamp_days

_BAJAS_AUX_TABLAS = ("bajas_de_inventario", "bajas_inventario")
_OPERATOR_IDS = frozenset(op["id"] for op in CALIDAD_OPERATORS)

_CSV_NAME_RE = re.compile(r"^inventario(\d{8})\.csv$", re.IGNORECASE)

_SQL_ALTAS_RAW = """
SELECT btrim(access_id::text), btrim(operatorid::text), provided_date, reserved_date
FROM aux.bajada_inventario
WHERE btrim(COALESCE(access_id::text, '')) <> ''
"""


def _operators_meta() -> list[dict]:
    return [{"id": "", "label": "Todos"}] + [
        {"id": op["id"], "label": op["label"]} for op in CALIDAD_OPERATORS
    ]


def _norm_operador(value: str | None) -> str:
    v = (value or "").strip()
    return v if v in _OPERATOR_IDS else ""


def _operator_label(op_id: str) -> str:
    return calidad_operator_label(op_id)


def _norm_op_id(raw) -> str:
    oid = canonical_calidad_operator_id(raw)
    return oid if oid in _OPERATOR_IDS else ""


def _empty_op_buckets() -> tuple[dict[date, set[str]], dict[str, dict[date, set[str]]]]:
    return defaultdict(set), {op["id"]: defaultdict(set) for op in CALIDAD_OPERATORS}


def _ingest_alta(
    altas_all: dict[date, set[str]],
    altas_by_op: dict[str, dict[date, set[str]]],
    aid: str,
    op_raw,
    provided,
    reserved,
    start: date,
    end: date,
) -> None:
    d = fecha_alta(provided, reserved)
    if not d or d < start or d > end or not aid:
        return
    altas_all[d].add(aid)
    op_id = _norm_op_id(op_raw)
    if op_id:
        altas_by_op[op_id][d].add(aid)


def _ingest_baja(
    bajas_all: dict[date, set[str]],
    bajas_by_op: dict[str, dict[date, set[str]]],
    aid: str,
    op_raw,
    cancel,
    reserved,
    provided,
    start: date,
    end: date,
) -> None:
    d = fecha_baja(cancel, reserved, provided)
    if not d or d < start or d > end or not aid:
        return
    bajas_all[d].add(aid)
    op_id = _norm_op_id(op_raw)
    if op_id:
        bajas_by_op[op_id][d].add(aid)


def _counts_from_sets(day_sets: dict[date, set[str]]) -> dict[date, int]:
    return {d: len(aids) for d, aids in day_sets.items()}


def _series_from_counts(
    altas: dict[date, int],
    bajas: dict[date, int],
    start: date,
    end: date,
) -> list[dict]:
    points = []
    cur = start
    while cur <= end:
        points.append({
            "fecha": cur.isoformat(),
            "altas": int(altas.get(cur, 0)),
            "bajas": int(bajas.get(cur, 0)),
        })
        cur += timedelta(days=1)
    return points


def _aggregate_period(points: list[dict], granularity: str) -> list[dict]:
    if granularity == "day":
        return points
    buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"altas": 0, "bajas": 0})
    for p in points:
        d = date.fromisoformat(p["fecha"])
        if granularity == "month":
            key = f"{d.year:04d}-{d.month:02d}"
        else:
            key = f"{d.year:04d}"
        buckets[key]["altas"] += int(p["altas"])
        buckets[key]["bajas"] += int(p["bajas"])
    return [
        {"periodo": k, "altas": v["altas"], "bajas": v["bajas"]}
        for k, v in sorted(buckets.items())
    ]


def _cards_from_daily(altas: dict[date, int], bajas: dict[date, int], ref: date) -> dict:
    def _sum_range(start: date, end: date) -> dict[str, int]:
        a = b = 0
        cur = start
        while cur <= end:
            a += altas.get(cur, 0)
            b += bajas.get(cur, 0)
            cur += timedelta(days=1)
        return {"altas": a, "bajas": b}

    month_start = ref.replace(day=1)
    year_start = ref.replace(month=1, day=1)
    week_start = ref - timedelta(days=6)
    yesterday = ref - timedelta(days=1)

    return {
        "hoy": {"altas": altas.get(ref, 0), "bajas": bajas.get(ref, 0)},
        "ayer": {"altas": altas.get(yesterday, 0), "bajas": bajas.get(yesterday, 0)},
        "ultimos_7_dias": _sum_range(week_start, ref),
        "mes_actual": _sum_range(month_start, ref),
        "anio_actual": _sum_range(year_start, ref),
    }


def _pick_counts(
    operador: str,
    all_counts: dict[date, int],
    by_op_sets: dict[str, dict[date, set[str]]],
) -> dict[date, int]:
    if not operador:
        return all_counts
    return _counts_from_sets(by_op_sets.get(operador, {}))


def _sql_bajas_tabla(tabla: str) -> str:
    if tabla not in _BAJAS_AUX_TABLAS:
        raise ValueError(f"tabla aux no permitida: {tabla}")
    return f"""
SELECT btrim(access_id::text), btrim(operatorid::text),
       cancellation_date, reserved_date, provided_date
FROM aux.{tabla}
WHERE btrim(COALESCE(access_id::text, '')) <> ''
"""


def _bajas_source_label(tablas_usadas: list[str]) -> str:
    parts = ["aux.bajada_inventario"] + [f"aux.{t}" for t in tablas_usadas]
    return " / ".join(parts) + " (réplica operativa del backup CSV)"


def _stats_from_postgres(
    days: int,
    operador: str = "",
    sftp_snapshot: str | None = None,
) -> dict:
    today = date.today()
    start = today - timedelta(days=days - 1)
    altas_all_sets, altas_by_op_sets = _empty_op_buckets()
    bajas_all_sets, bajas_by_op_sets = _empty_op_buckets()
    bajas_tablas: list[str] = []
    seen_baja_global: set[tuple[date, str]] = set()

    with db_cursor() as cur:
        cur.execute(_SQL_ALTAS_RAW)
        seen_alta: set[tuple[date, str]] = set()
        for aid, op_raw, provided, reserved in cur.fetchall():
            d = fecha_alta(provided, reserved)
            if not d or d < start or d > today:
                continue
            key = (d, aid)
            if key in seen_alta:
                continue
            seen_alta.add(key)
            _ingest_alta(altas_all_sets, altas_by_op_sets, aid, op_raw, provided, reserved, start, today)

        for tabla in _BAJAS_AUX_TABLAS:
            try:
                cur.execute(_sql_bajas_tabla(tabla))
                bajas_tablas.append(tabla)
                batch = cur.fetchall()
            except UndefinedTable:
                cur.connection.rollback()
                continue
            except Exception as exc:
                if "does not exist" in str(exc).lower():
                    cur.connection.rollback()
                    continue
                raise
            for aid, op_raw, cancel, reserved, provided in batch:
                d = fecha_baja(cancel, reserved, provided)
                if not d or d < start or d > today:
                    continue
                key = (d, aid)
                if key in seen_baja_global:
                    continue
                seen_baja_global.add(key)
                _ingest_baja(
                    bajas_all_sets,
                    bajas_by_op_sets,
                    aid,
                    op_raw,
                    cancel,
                    reserved,
                    provided,
                    start,
                    today,
                )

    altas_all = _counts_from_sets(altas_all_sets)
    bajas_all = _counts_from_sets(bajas_all_sets)
    altas_view = _pick_counts(operador, altas_all, altas_by_op_sets)
    bajas_view = _pick_counts(operador, bajas_all, bajas_by_op_sets)
    ref = _reference_date(altas_view, bajas_view, sftp_snapshot, calendar_today=today)
    daily = _series_from_counts(altas_view, bajas_view, start, today)

    by_operator = []
    if not operador:
        for op in CALIDAD_OPERATORS:
            oid = op["id"]
            a = _counts_from_sets(altas_by_op_sets[oid])
            b = _counts_from_sets(bajas_by_op_sets[oid])
            by_operator.append({
                "id": oid,
                "label": op["label"],
                "cards": _cards_from_daily(a, b, ref),
            })

    return {
        "source": "postgres",
        "source_label": _bajas_source_label(bajas_tablas),
        "days": days,
        "latest_snapshot": ref.isoformat(),
        "reference_date": ref.isoformat(),
        "reference_date_is_today": ref == today,
        "operators": _operators_meta(),
        "filter": {
            "operador": operador,
            "operador_label": _operator_label(operador),
        },
        "cards": _cards_from_daily(altas_view, bajas_view, ref),
        "daily": daily,
        "by_operator": by_operator,
    }


def _sftp_latest_snapshot_date() -> str | None:
    cfg = get_inventario_sftp_config()
    if not cfg.get("enabled"):
        return None
    try:
        import paramiko

        from services.ppk_private_key import load_paramiko_pkey

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = load_paramiko_pkey(cfg["key_path"])
        client.connect(
            cfg["host"],
            port=cfg["port"],
            username=cfg["user"],
            pkey=pkey,
            timeout=cfg.get("timeout", 30),
            allow_agent=False,
            look_for_keys=False,
        )
        sftp = client.open_sftp()
        remote = cfg["remote_dir"].rstrip("/")
        names = sftp.listdir(remote)
        sftp.close()
        client.close()
        dates = []
        for name in names:
            m = _CSV_NAME_RE.match(name)
            if m:
                dates.append(m.group(1))
        return max(dates) if dates else None
    except Exception:
        return None


def _norm_granularity(value: str | None) -> str:
    g = (value or "day").strip().lower()
    return g if g in ("day", "month", "year") else "day"


def _days_for_granularity(granularity: str) -> int:
    """Ventana de datos según vista (solo afecta el gráfico; tarjetas usan calendario fijo)."""
    if granularity == "month":
        return 365
    if granularity == "year":
        return 365 * 3
    return 90


def _compute_estadisticas(granularity: str) -> dict:
    gran = _norm_granularity(granularity)
    days_chart = _days_for_granularity(gran)
    today = date.today()
    snap = _sftp_latest_snapshot_date()
    base = _stats_from_postgres(365, operador="", sftp_snapshot=snap)
    ref = date.fromisoformat(base["reference_date"])
    if snap:
        parsed = _parse_snapshot_date(snap)
        if parsed:
            base["sftp_backup_latest"] = parsed.isoformat()
        else:
            base["sftp_backup_latest"] = snap
    daily_full = base.pop("daily")
    start_chart = ref - timedelta(days=days_chart - 1)
    altas_d: dict[date, int] = {}
    bajas_d: dict[date, int] = {}
    for p in daily_full:
        d = date.fromisoformat(p["fecha"])
        if d < start_chart or d > ref:
            continue
        altas_d[d] = int(p["altas"])
        bajas_d[d] = int(p["bajas"])
    base["granularity"] = gran
    base["series"] = _aggregate_period(
        _series_from_counts(altas_d, bajas_d, start_chart, ref),
        gran,
    )
    base["chart_days"] = days_chart
    base["filter"] = {"operador": "", "operador_label": "Todos"}
    return base


def dashboard_calidad_inventario_estadisticas(
    days: int | None = None,
    granularity: str = "day",
    operador: str | None = None,
) -> dict:
    """Altas/bajas agregadas para el tablero Estadísticas."""
    gran = _norm_granularity(granularity)
    cache_secs = get_inventario_estadisticas_cache_seconds()

    def _factory():
        return _compute_estadisticas(gran)

    return get_cached_inventario_estadisticas(cache_secs, gran, _factory)
