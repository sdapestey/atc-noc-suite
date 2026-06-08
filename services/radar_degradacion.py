"""Servicios para Radar Degradacion — ranking preventivo de ramas por tendencia Rx."""
from __future__ import annotations

import csv
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from io import StringIO
from statistics import median

from psycopg2.errors import QueryCanceled

from config import (
    get_dashboard_historico_cache_seconds,
    get_radar_degradacion_olt_workers,
    get_radar_degradacion_statement_timeout_ms,
)
from db import db_cursor
from queries import QUERIES

from .dashboard_cache import get_cached_historico_potencias
from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    clasificar_rx_dbm,
    region_desde_rama,
    resumen_semaforo_desde_rx_values,
)
from .historico_potencias import (
    _batch_ont_keys_por_ramas,
    _batch_pon_desde_ramas,
    _is_historico_rx_down_placeholder,
    _normalizar_potencias_objectname,
    _olt_desde_pon,
    _ont_key_from_object_name,
    _pon_prefix_from_normalized_objectname,
)

ALLOWED_RADAR_DAYS = (7, 14, 30)
_MIN_DIAS_TENDENCIA = 3
_RAMA_BATCH_SIZE = 500
_RADAR_MAX_ITEMS = 10000

logger = logging.getLogger(__name__)
# Recuperación intradía: pico del día vs última lectura (evita falsos positivos).
_EVENTO_TRANSITORIO_GAP_DB = 3.0


def _validar_radar_days(days: int | str | None) -> int | None:
    try:
        value = int(days if days is not None else 14)
    except (TypeError, ValueError):
        return None
    return value if value in ALLOWED_RADAR_DAYS else None


def _principal_desde_rama(rama: str) -> str:
    reg = region_desde_rama(rama)
    return SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)


def _dia_key(dia) -> str | None:
    if isinstance(dia, datetime):
        return dia.strftime("%Y-%m-%d")
    if isinstance(dia, date):
        return dia.strftime("%Y-%m-%d")
    if dia is None:
        return None
    return str(dia)[:10]


def _linear_slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _ultima_rx_por_ont_en_dia(samples: list[tuple]) -> float | None:
    """Última Rx válida del día por ONT (ordenada por timestamp)."""
    valid = [
        (ts, float(rx))
        for ts, rx in samples
        if not _is_historico_rx_down_placeholder(rx)
    ]
    if not valid:
        return None
    valid.sort(key=lambda pair: pair[0])
    return valid[-1][1]


def _peor_rx_por_ont_en_dia(samples: list[tuple]) -> float | None:
    valid = [
        float(rx)
        for _ts, rx in samples
        if not _is_historico_rx_down_placeholder(rx)
    ]
    if not valid:
        return None
    return min(valid)


def _dia_es_transitorio(peor_pico: float | None, ultima_peor: float | None) -> bool:
    if peor_pico is None or ultima_peor is None:
        return False
    gap = float(ultima_peor) - float(peor_pico)
    if gap < _EVENTO_TRANSITORIO_GAP_DB:
        return False
    return clasificar_rx_dbm(ultima_peor) != "rojo"


def _estado_timeline_codigo(ultima_peor_rx: float | None) -> str:
    """Código compacto G/A/R/N según última Rx del día (misma regla que el score)."""
    if ultima_peor_rx is None:
        return "N"
    cat = clasificar_rx_dbm(ultima_peor_rx)
    if cat == "rojo":
        return "R"
    if cat == "amarillo":
        return "A"
    return "G"


def _dias_en_ventana(days: int, hasta: date | None = None) -> list[str]:
    """Calendario completo de la ventana (misma extensión que el filtro SQL)."""
    end = hasta or date.today()
    start = end - timedelta(days=max(1, int(days)) - 1)
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _timeline_entry_desde_fila(row: dict) -> dict | None:
    dia = str(row.get("dia") or "").strip()
    if not dia:
        return None
    ultima = row.get("ultima_peor_rx")
    pico = row.get("peor_rx_pico")
    transitorio = bool(row.get("evento_transitorio_dia"))
    entry: dict = {
        "d": dia,
        "e": _estado_timeline_codigo(ultima),
    }
    if ultima is not None:
        entry["r"] = round(float(ultima), 2)
    if transitorio:
        entry["t"] = 1
        if pico is not None:
            entry["p"] = round(float(pico), 2)
    return entry


def _build_timeline_dias(
    daily_rows: list[dict],
    *,
    window_days: int | None = None,
    hasta: date | None = None,
) -> list[dict]:
    """Serie diaria para sparkline: última Rx del día + marca de pico transitorio."""
    by_dia: dict[str, dict] = {}
    for row in sorted(daily_rows, key=lambda r: str(r.get("dia") or "")):
        entry = _timeline_entry_desde_fila(row)
        if entry is not None:
            by_dia[entry["d"]] = entry

    if window_days is None:
        return [by_dia[d] for d in sorted(by_dia.keys())]

    timeline: list[dict] = []
    for dia in _dias_en_ventana(window_days, hasta=hasta):
        timeline.append(by_dia.get(dia, {"d": dia, "e": "N"}))
    return timeline


def _compute_rama_metrics(
    daily_rows: list[dict],
    ont_count: int,
    cto_count: int,
    *,
    window_days: int | None = None,
) -> dict | None:
    if not daily_rows:
        return None

    ordered = sorted(daily_rows, key=lambda r: r["dia"])
    ultima_series = [
        r["ultima_peor_rx"]
        for r in ordered
        if r.get("ultima_peor_rx") is not None
    ]
    if len(ultima_series) < _MIN_DIAS_TENDENCIA:
        return None

    dias_sostenidos = [
        r
        for r in ordered
        if r.get("ultima_peor_rx") is not None and not r.get("evento_transitorio_dia")
    ]
    trend_rows = dias_sostenidos if len(dias_sostenidos) >= _MIN_DIAS_TENDENCIA else ordered
    trend_series = [
        r["ultima_peor_rx"]
        for r in trend_rows
        if r.get("ultima_peor_rx") is not None
    ]

    xs = list(range(len(trend_series)))
    slope = _linear_slope([float(x) for x in xs], [float(y) for y in trend_series])

    half = max(1, len(trend_series) // 2)
    first_half = trend_series[:half]
    second_half = trend_series[-half:]
    delta_baseline = None
    avg_first = _avg([float(v) for v in first_half])
    avg_second = _avg([float(v) for v in second_half])
    if avg_first is not None and avg_second is not None:
        delta_baseline = round(avg_second - avg_first, 2)

    last = ordered[-1]
    first = ordered[0]
    ultima_peor_rx = last.get("ultima_peor_rx")
    ultima_mediana_rx = last.get("ultima_mediana_rx")
    peor_rx_pico = last.get("peor_rx_pico")
    onts_validas = int(last.get("onts_validas") or 0)
    onts_amarillo_rojo = int(last.get("onts_amarillo_rojo") or 0)
    onts_down = int(last.get("onts_down") or 0)
    pct_amarillo_rojo = (
        round(100.0 * onts_amarillo_rojo / onts_validas, 1) if onts_validas > 0 else 0.0
    )

    first_amarillo = int(first.get("onts_amarillo_rojo") or 0)
    delta_amarillo = onts_amarillo_rojo - first_amarillo
    first_down = int(first.get("onts_down") or 0)
    delta_down = onts_down - first_down

    evento_transitorio_ultimo = bool(last.get("evento_transitorio_dia"))
    dias_transitorios = sum(1 for r in ordered if r.get("evento_transitorio_dia"))
    ultima_recuperada = (
        ultima_peor_rx is not None
        and clasificar_rx_dbm(ultima_peor_rx) == "verde"
        and (
            evento_transitorio_ultimo
            or (
                peor_rx_pico is not None
                and float(peor_rx_pico) <= -27.0
                and float(ultima_peor_rx) > -27.0
            )
        )
    )

    dias_criticos_sostenidos = sum(
        1
        for r in ordered
        if r.get("ultima_peor_rx") is not None
        and float(r["ultima_peor_rx"]) <= -27.0
        and not r.get("evento_transitorio_dia")
    )

    senales: list[str] = []
    score = 0.0

    degradacion_sostenida = slope < -0.02 and dias_criticos_sostenidos >= 1
    if degradacion_sostenida:
        senales.append("degradacion_sostenida")
        score += min(35.0, abs(slope) * 700.0)
    if delta_baseline is not None and delta_baseline < -1.0 and not ultima_recuperada:
        senales.append("delta_rx")
        score += min(25.0, abs(delta_baseline) * 8.0)
    if pct_amarillo_rojo >= 10.0 and not ultima_recuperada:
        senales.append("semaforo_amarillo")
        score += min(20.0, pct_amarillo_rojo * 0.6)
    if delta_amarillo >= 2 and not ultima_recuperada:
        senales.append("mas_onts_amarillas")
        score += min(12.0, float(delta_amarillo) * 2.0)
    if delta_down >= 1:
        senales.append("onts_down")
        score += min(10.0, float(delta_down) * 4.0)
    if ultima_peor_rx is not None and float(ultima_peor_rx) <= -27.0:
        senales.append("ultima_rx_critica")
        score += 10.0
    if evento_transitorio_ultimo or dias_transitorios > 0:
        senales.append("evento_transitorio")
    if ultima_recuperada:
        senales.append("recuperacion")
        score *= 0.35

    score = round(min(100.0, score), 1)
    nivel = "ESTABLE"
    if score >= 55.0 and (
        degradacion_sostenida
        or dias_criticos_sostenidos >= 2
        or (
            ultima_peor_rx is not None
            and float(ultima_peor_rx) <= -27.0
            and not ultima_recuperada
        )
    ):
        nivel = "CRITICO"
    elif score >= 30.0 and not ultima_recuperada:
        nivel = "ATENCION"

    semaforo_rx = [
        float(v)
        for v in (ultima_peor_rx, ultima_mediana_rx)
        if v is not None
    ]
    semaforo = resumen_semaforo_desde_rx_values(semaforo_rx)
    if ultima_peor_rx is not None:
        cat = clasificar_rx_dbm(ultima_peor_rx)
        if cat == "rojo":
            semaforo = {"ROJAS": 1, "AMARILLAS": 0, "VERDES": 0}
        elif cat == "amarillo":
            semaforo = {"ROJAS": 0, "AMARILLAS": 1, "VERDES": 0}
        elif cat == "verde":
            semaforo = {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 1}

    return {
        "ULTIMA_PEOR_RX": None if ultima_peor_rx is None else round(float(ultima_peor_rx), 2),
        "ULTIMA_MEDIANA_RX": None if ultima_mediana_rx is None else round(float(ultima_mediana_rx), 2),
        "PEOR_RX_PICO": None if peor_rx_pico is None else round(float(peor_rx_pico), 2),
        "PEOR_RX": None if ultima_peor_rx is None else round(float(ultima_peor_rx), 2),
        "MEDIANA_RX": None if ultima_mediana_rx is None else round(float(ultima_mediana_rx), 2),
        "PENDIENTE_PEOR_RX": round(float(slope), 4),
        "DELTA_BASELINE_DB": delta_baseline,
        "PCT_AMARILLO_ROJO": pct_amarillo_rojo,
        "DELTA_AMARILLO": delta_amarillo,
        "DELTA_DOWN": delta_down,
        "DIAS_CON_MUESTRA": len(ordered),
        "DIAS_TRANSITORIOS": dias_transitorios,
        "ULTIMA_MUESTRA": last.get("dia"),
        "SCORE": score,
        "NIVEL": nivel,
        "SENALES": senales,
        "ROJAS": semaforo["ROJAS"],
        "AMARILLAS": semaforo["AMARILLAS"],
        "VERDES": semaforo["VERDES"],
        "ONT_COUNT": int(ont_count or 0),
        "CTO_COUNT": int(cto_count or 0),
        "ONT_CON_RX": onts_validas,
        "TIMELINE": _build_timeline_dias(ordered, window_days=window_days),
    }


def _procesar_filas_radar_por_olt(
    rows: list,
    ramas_by_pon: dict[str, set[str]],
    ont_keys_by_rama: dict[str, set[str]],
) -> dict[str, list[dict]]:
    """Agrega muestras diarias por RAMA (última Rx por ONT; pico solo como referencia)."""
    ont_day_samples: dict[tuple[str, str, str], list[tuple]] = defaultdict(list)
    ont_day_down: set[tuple[str, str, str]] = set()

    for row in rows:
        if len(row) >= 4:
            dia, ts, objectname, rx = row[0], row[1], row[2], row[3]
        else:
            dia, objectname, rx = row[0], row[1], row[2]
            ts = dia
        if not isinstance(dia, datetime) and not isinstance(dia, date):
            continue
        dia_key = _dia_key(dia)
        if not dia_key:
            continue
        if rx is None:
            continue
        if not isinstance(ts, datetime):
            ts = dia if isinstance(dia, datetime) else datetime.min
        rx_val = float(rx)
        norm = _normalizar_potencias_objectname(str(objectname or ""))
        pon = _pon_prefix_from_normalized_objectname(norm)
        if not pon or pon not in ramas_by_pon:
            continue
        ont_key = _ont_key_from_object_name(objectname)
        if not ont_key:
            continue
        for rama in ramas_by_pon[pon]:
            if ont_key not in ont_keys_by_rama.get(rama, set()):
                continue
            key = (rama, dia_key, f"{pon}-{ont_key}")
            if _is_historico_rx_down_placeholder(rx_val):
                ont_day_down.add(key)
            else:
                ont_day_samples[key].append((ts, rx_val))

    rama_day_acc: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"ultima_vals": [], "pico_vals": [], "down": 0}
    )
    all_keys = set(ont_day_samples.keys()) | ont_day_down
    for rama, dia_key, _ont in all_keys:
        key = (rama, dia_key, _ont)
        acc = rama_day_acc[(rama, dia_key)]
        samples = ont_day_samples.get(key, [])
        ultima = _ultima_rx_por_ont_en_dia(samples)
        pico = _peor_rx_por_ont_en_dia(samples)
        if ultima is None:
            if key in ont_day_down:
                acc["down"] += 1
            continue
        acc["ultima_vals"].append(ultima)
        if pico is not None:
            acc["pico_vals"].append(pico)

    daily_by_rama: dict[str, list[dict]] = defaultdict(list)
    for (rama, dia_key), acc in sorted(rama_day_acc.items()):
        ultima_vals = acc["ultima_vals"]
        if not ultima_vals and acc["down"] <= 0:
            continue
        ultima_peor_rx = min(ultima_vals) if ultima_vals else None
        ultima_mediana_rx = median(ultima_vals) if ultima_vals else None
        peor_rx_pico = min(acc["pico_vals"]) if acc["pico_vals"] else ultima_peor_rx
        onts_validas = len(ultima_vals)
        onts_amarillo_rojo = sum(1 for v in ultima_vals if float(v) <= -25.0)
        evento_transitorio_dia = _dia_es_transitorio(peor_rx_pico, ultima_peor_rx)
        daily_by_rama[rama].append({
            "dia": dia_key,
            "ultima_peor_rx": None if ultima_peor_rx is None else float(ultima_peor_rx),
            "ultima_mediana_rx": None if ultima_mediana_rx is None else float(ultima_mediana_rx),
            "peor_rx_pico": None if peor_rx_pico is None else float(peor_rx_pico),
            "onts_amarillo_rojo": onts_amarillo_rojo,
            "onts_down": int(acc["down"]),
            "onts_validas": onts_validas,
            "evento_transitorio_dia": evento_transitorio_dia,
        })
    return daily_by_rama


def _merge_daily_by_rama(
    merged: dict[str, list[dict]],
    chunk: dict[str, list[dict]],
) -> None:
    for rama, rows in chunk.items():
        by_day: dict[str, dict] = {r["dia"]: dict(r) for r in merged.get(rama, [])}
        for row in rows:
            dia = row["dia"]
            prev = by_day.get(dia)
            if prev is None:
                by_day[dia] = dict(row)
                continue
            ultima_peor_vals = [
                v
                for v in (prev.get("ultima_peor_rx"), row.get("ultima_peor_rx"))
                if v is not None
            ]
            ultima_mediana_vals = [
                v
                for v in (prev.get("ultima_mediana_rx"), row.get("ultima_mediana_rx"))
                if v is not None
            ]
            pico_vals = [
                v
                for v in (prev.get("peor_rx_pico"), row.get("peor_rx_pico"))
                if v is not None
            ]
            ultima_peor_rx = min(ultima_peor_vals) if ultima_peor_vals else None
            peor_rx_pico = min(pico_vals) if pico_vals else ultima_peor_rx
            by_day[dia] = {
                "dia": dia,
                "ultima_peor_rx": ultima_peor_rx,
                "ultima_mediana_rx": median(ultima_mediana_vals) if ultima_mediana_vals else None,
                "peor_rx_pico": peor_rx_pico,
                "onts_amarillo_rojo": int(prev.get("onts_amarillo_rojo") or 0)
                + int(row.get("onts_amarillo_rojo") or 0),
                "onts_down": int(prev.get("onts_down") or 0) + int(row.get("onts_down") or 0),
                "onts_validas": int(prev.get("onts_validas") or 0)
                + int(row.get("onts_validas") or 0),
                "evento_transitorio_dia": _dia_es_transitorio(peor_rx_pico, ultima_peor_rx),
            }
        merged[rama] = [by_day[d] for d in sorted(by_day.keys())]


def _batch_maps_por_ramas(ramas: list[str]) -> tuple[dict[str, str | None], dict[str, set[str]]]:
    """Resuelve PON y claves ONT en lotes para no saturar una sola query."""
    ramas_norm = sorted({str(r or "").strip() for r in ramas if str(r or "").strip()})
    pon_by_rama: dict[str, str | None] = {}
    ont_keys_by_rama: dict[str, set[str]] = defaultdict(set)
    for i in range(0, len(ramas_norm), _RAMA_BATCH_SIZE):
        chunk = ramas_norm[i : i + _RAMA_BATCH_SIZE]
        pon_by_rama.update(_batch_pon_desde_ramas(chunk))
        for rama, keys in _batch_ont_keys_por_ramas(chunk).items():
            ont_keys_by_rama[rama].update(keys)
    return pon_by_rama, ont_keys_by_rama


def _fetch_radar_rows_por_olt(olt: str, days: int) -> list:
    timeout_ms = get_radar_degradacion_statement_timeout_ms()
    with db_cursor() as cur:
        if timeout_ms > 0:
            cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        cur.execute(
            QUERIES["radar_degradacion_muestras_por_olt"],
            (int(days), f"%{olt}-%", f"%{olt}:%"),
        )
        return cur.fetchall()


def _merge_olt_chunk(
    merged: dict[str, list[dict]],
    rows: list,
    ramas_by_pon: dict[str, set[str]],
    ont_keys_by_rama: dict[str, set[str]],
) -> None:
    chunk = _procesar_filas_radar_por_olt(rows, ramas_by_pon, ont_keys_by_rama)
    _merge_daily_by_rama(merged, chunk)


def _cargar_muestras_diarias_por_rama(days: int, ramas: list[str]) -> dict[str, list[dict]]:
    """Lee potencias por OLT (evita join masivo inventario × potencias)."""
    ramas_norm = sorted({str(r or "").strip() for r in ramas if str(r or "").strip()})
    if not ramas_norm:
        return {}

    pon_by_rama, ont_keys_by_rama = _batch_maps_por_ramas(ramas_norm)
    ramas_by_pon: dict[str, set[str]] = defaultdict(set)
    olts: set[str] = set()
    for rama in ramas_norm:
        pon = pon_by_rama.get(rama)
        if not pon:
            continue
        ramas_by_pon[pon].add(rama)
        olt = _olt_desde_pon(pon)
        if olt:
            olts.add(olt)

    merged: dict[str, list[dict]] = {}
    olt_list = sorted(olts)
    if not olt_list:
        return merged

    workers = max(1, min(get_radar_degradacion_olt_workers(), len(olt_list)))
    failed_olts: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch_radar_rows_por_olt, olt, days): olt for olt in olt_list
        }
        for fut in as_completed(futures):
            olt = futures[fut]
            try:
                rows = fut.result()
                _merge_olt_chunk(merged, rows, ramas_by_pon, ont_keys_by_rama)
            except QueryCanceled:
                logger.warning("Radar degradacion: timeout OLT %s (reintento secuencial)", olt)
                failed_olts.append(olt)
            except Exception:
                logger.exception("Radar degradacion: error OLT %s", olt)
                failed_olts.append(olt)

    for olt in failed_olts:
        try:
            rows = _fetch_radar_rows_por_olt(olt, days)
            _merge_olt_chunk(merged, rows, ramas_by_pon, ont_keys_by_rama)
        except Exception:
            logger.warning(
                "Radar degradacion: OLT %s omitido tras reintento",
                olt,
                exc_info=True,
            )
    return merged


def _radar_degradacion_uncached(
    days: int,
    *,
    principal: str | None = None,
    nivel: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> dict:
    inv_by_rama: dict[str, tuple[int, int]] = {}
    with db_cursor() as cur:
        cur.execute(QUERIES["radar_degradacion_inventario"])
        for rama, ont_count, cto_count in cur.fetchall():
            key = str(rama or "").strip()
            if key:
                inv_by_rama[key] = (int(ont_count or 0), int(cto_count or 0))

    daily_by_rama = _cargar_muestras_diarias_por_rama(days, list(inv_by_rama.keys()))

    items: list[dict] = []
    sin_datos = 0
    for rama, (ont_count, cto_count) in inv_by_rama.items():
        metrics = _compute_rama_metrics(
            daily_by_rama.get(rama, []),
            ont_count,
            cto_count,
            window_days=days,
        )
        if metrics is None:
            sin_datos += 1
            continue
        principal_name = _principal_desde_rama(rama)
        items.append({
            "RAMA": rama,
            "PRINCIPAL": principal_name,
            "REGION": region_desde_rama(rama),
            **metrics,
        })

    items.sort(
        key=lambda x: (
            -float(x.get("SCORE") or 0),
            float(x.get("ULTIMA_PEOR_RX") or x.get("PEOR_RX") or 0),
        )
    )

    principal_filter = (principal or "").strip()
    nivel_filter = (nivel or "").strip().upper()
    q_filter = (q or "").strip().lower()
    limit_val = max(1, min(int(limit or _RADAR_MAX_ITEMS), _RADAR_MAX_ITEMS))

    filtered: list[dict] = []
    for row in items:
        if principal_filter and principal_filter != "ALL" and row.get("PRINCIPAL") != principal_filter:
            continue
        if nivel_filter and nivel_filter != "ALL" and row.get("NIVEL") != nivel_filter:
            continue
        if q_filter:
            haystack = " ".join([
                str(row.get("RAMA") or ""),
                str(row.get("PRINCIPAL") or ""),
                str(row.get("REGION") or ""),
            ]).lower()
            if q_filter not in haystack:
                continue
        filtered.append(row)

    totales = {
        "RAMAS_INVENTARIO": len(inv_by_rama),
        "RAMAS_CON_TENDENCIA": len(items),
        "RAMAS_SIN_DATOS": sin_datos,
        "CRITICO": sum(1 for r in items if r.get("NIVEL") == "CRITICO"),
        "ATENCION": sum(1 for r in items if r.get("NIVEL") == "ATENCION"),
        "ESTABLE": sum(1 for r in items if r.get("NIVEL") == "ESTABLE"),
    }

    return {
        "ok": True,
        "days": days,
        "source": "historico",
        "mode": "tendencia_ultima_rx_por_olt",
        "totales": totales,
        "items": filtered[:limit_val],
        "total_filtrado": len(filtered),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def consultar_radar_degradacion(
    days: int = 14,
    *,
    principal: str | None = None,
    nivel: str | None = None,
    q: str | None = None,
    limit: int = 200,
) -> dict:
    """Ranking de ramas con señales de degradación en Rx (histórico Postgres)."""
    days_validado = _validar_radar_days(days)
    if days_validado is None:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 7, 14, 30",
        }
    cache_key = "|".join([
        str(days_validado),
        (principal or "ALL").strip(),
        (nivel or "ALL").strip().upper(),
        (q or "").strip().lower(),
        str(max(1, min(int(limit or _RADAR_MAX_ITEMS), _RADAR_MAX_ITEMS))),
    ])
    return get_cached_historico_potencias(
        get_dashboard_historico_cache_seconds(),
        f"radar_degradacion|v5|{cache_key}",
        lambda: _radar_degradacion_uncached(
            days_validado,
            principal=principal,
            nivel=nivel,
            q=q,
            limit=limit,
        ),
    )


def _timeline_csv_cell(timeline: list[dict] | None) -> str:
    if not timeline:
        return ""
    parts: list[str] = []
    for day in timeline:
        dia = str(day.get("d") or "")
        estado = str(day.get("e") or "N")
        seg = f"{dia}:{estado}"
        if day.get("r") is not None:
            seg += f":{day['r']}"
        if day.get("t"):
            seg += ":t"
            if day.get("p") is not None:
                seg += f":{day['p']}"
        parts.append(seg)
    return "|".join(parts)


def export_csv_radar_degradacion(
    days: int = 14,
    *,
    principal: str | None = None,
    nivel: str | None = None,
    q: str | None = None,
    limit: int = 2000,
) -> dict:
    payload = consultar_radar_degradacion(
        days=days,
        principal=principal,
        nivel=nivel,
        q=q,
        limit=limit,
    )
    if not payload.get("ok"):
        return payload

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "rama",
        "principal",
        "region",
        "nivel",
        "score",
        "ultima_peor_rx_dbm",
        "ultima_mediana_rx_dbm",
        "peor_rx_pico_dbm",
        "pendiente_peor_rx",
        "delta_baseline_db",
        "pct_amarillo_rojo",
        "dias_con_muestra",
        "timeline",
        "ultima_muestra",
        "cto_count",
        "ont_count",
        "senales",
    ])
    for row in payload.get("items", []):
        writer.writerow([
            row.get("RAMA", ""),
            row.get("PRINCIPAL", ""),
            row.get("REGION", ""),
            row.get("NIVEL", ""),
            row.get("SCORE", ""),
            row.get("ULTIMA_PEOR_RX", row.get("PEOR_RX", "")),
            row.get("ULTIMA_MEDIANA_RX", row.get("MEDIANA_RX", "")),
            row.get("PEOR_RX_PICO", ""),
            row.get("PENDIENTE_PEOR_RX", ""),
            row.get("DELTA_BASELINE_DB", ""),
            row.get("PCT_AMARILLO_ROJO", ""),
            row.get("DIAS_CON_MUESTRA", ""),
            _timeline_csv_cell(row.get("TIMELINE")),
            row.get("ULTIMA_MUESTRA", ""),
            row.get("CTO_COUNT", ""),
            row.get("ONT_COUNT", ""),
            "|".join(row.get("SENALES") or []),
        ])

    return {
        "ok": True,
        "csv": out.getvalue(),
        "days": payload.get("days", days),
    }
