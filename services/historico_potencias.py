"""Servicios para dashboard de histórico de potencias por rama."""
import csv
import re
from collections import defaultdict
from datetime import datetime
from io import StringIO
from statistics import median

from config import get_dashboard_historico_cache_seconds
from db import db_cursor
from queries import QUERIES

from .dashboard_cache import get_cached_historico_potencias
from .domain import lt_desde_object_name, resumen_semaforo_desde_rx_values
from .inventory import consultar_rama_potencias_altiplano_por_ont


_OBJ_RE = re.compile(r"^(.*?):1-1-(\d+)-(\d+)-")
_POTENCIAS_OBJ_PREFIX_RE = re.compile(r"^v\d+__t_")
ALLOWED_HISTORICO_DAYS = (1, 7, 15, 30)
# Lectura guardada en Postgres cuando la rama/ONT no tenía señal (no comparar como baseline).
HISTORICO_RX_DOWN_PLACEHOLDER_DBM = -100.0


def _is_historico_rx_down_placeholder(rx: float | None) -> bool:
    if rx is None:
        return False
    return float(rx) == HISTORICO_RX_DOWN_PLACEHOLDER_DBM


def _resolver_pon_desde_rama(ratc: str) -> str | None:
    """Resuelve `OLT-B-P` a partir de una rama RATC."""
    with db_cursor() as cur:
        cur.execute(QUERIES["historico_resolver_pon_desde_rama"], (ratc,))
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    obj_name = str(row[0]).strip()
    m = _OBJ_RE.search(obj_name)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _validar_days(days: int | str | None) -> int | None:
    try:
        value = int(days if days is not None else 30)
    except (TypeError, ValueError):
        return None
    return value if value in ALLOWED_HISTORICO_DAYS else None


def _ont_key_from_object_name(obj) -> str:
    """Clave ONT (último segmento) alineada con histórico Altiplano y consulta índice."""
    s = str(obj or "").strip()
    if not s:
        return ""
    if ":1-1" in s:
        s = s.split(":1-1", 1)[-1]
    parts = s.split("-")
    return parts[-1].strip() if parts else ""


def _ont_inventory_maps(rama: str) -> tuple[dict[str, str], dict[str, str]]:
    """Último segmento de `object_name` (ONT) → CTO y Access ID en la rama."""
    cto_by_ont: dict[str, str] = {}
    access_by_ont: dict[str, str] = {}
    rama_s = str(rama or "").strip()
    if not rama_s:
        return cto_by_ont, access_by_ont
    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_rama"], (rama_s,))
        rows = cur.fetchall()
    for r in rows:
        aid = r[0]
        aid_s = str(aid).strip() if aid is not None else ""
        cto = str(r[2] or "").strip()
        ont_keys: set[str] = set()
        for col in (r[4], r[5]):
            ok = _ont_key_from_object_name(col)
            if ok:
                ont_keys.add(ok)
        if not ont_keys:
            continue
        for ont_key in ont_keys:
            if cto and ont_key not in cto_by_ont:
                cto_by_ont[ont_key] = cto
            if aid_s:
                access_by_ont[ont_key] = aid_s
    return cto_by_ont, access_by_ont


def _ont_sort_key(ont: str, cto_by_ont: dict[str, str]) -> tuple:
    cto = (cto_by_ont.get(ont) or "").strip()
    prim = cto if cto else "\uffff"
    s = str(ont)
    if s.isdigit():
        return (prim, 0, int(s))
    return (prim, 1, s)


def consultar_potencias_historico_rama(ratc: str, days: int = 30) -> dict:
    """Devuelve serie histórica de RX para todas las ONT de la rama."""
    rama = (ratc or "").strip()
    if not rama:
        return {"ok": False, "status_code": 400, "error": "Parámetro ratc requerido"}
    days_validado = _validar_days(days)
    if days_validado is None:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 1 (24h), 7, 15, 30",
        }

    cache_key = f"{rama.upper()}|{days_validado}"
    return get_cached_historico_potencias(
        get_dashboard_historico_cache_seconds(),
        cache_key,
        lambda: _consultar_potencias_historico_rama_uncached(rama, days_validado),
    )


def _consultar_potencias_historico_rama_uncached(rama: str, days_validado: int) -> dict:
    pon = _resolver_pon_desde_rama(rama)
    if not pon:
        return {
            "ok": False,
            "status_code": 404,
            "error": "Rama RATC no encontrada en inventario",
        }

    with db_cursor() as cur:
        cur.execute(QUERIES["historico_potencias_por_pon"], (f"%{pon}-%", int(days_validado)))
        rows = cur.fetchall()

    if not rows:
        return {
            "ok": False,
            "status_code": 200,
            "error": f"Sin muestras de potencia en el rango seleccionado ({days_validado} dias)",
        }

    ont_cto, ont_access = _ont_inventory_maps(rama)

    by_ont = defaultdict(dict)
    timestamps = set()
    last_by_ont: dict[str, float | None] = {}
    last_ts_by_ont: dict[str, str] = {}

    csv_rows = []
    for ts, objectname, rx in rows:
        if not isinstance(ts, datetime):
            continue
        ts_key = ts.strftime("%Y-%m-%d %H:%M")
        objectname_str = str(objectname)
        ont_short = _ont_key_from_object_name(objectname_str)
        if not ont_short:
            continue
        rx_val = None if rx is None else float(rx)
        by_ont[ont_short][ts_key] = rx_val
        timestamps.add(ts_key)
        if rx is not None and not _is_historico_rx_down_placeholder(rx_val):
            last_by_ont[ont_short] = rx_val
            last_ts_by_ont[ont_short] = ts_key
        csv_rows.append({
            "timestamp": ts_key,
            "objectname": objectname_str,
            "ont": ont_short,
            "rx_dbm": None if rx is None else round(float(rx), 2),
            "pon": pon,
        })

    labels = sorted(timestamps)
    datasets = []
    for ont in sorted(by_ont.keys(), key=lambda v: int(v) if str(v).isdigit() else str(v)):
        points = [by_ont[ont].get(ts) for ts in labels]
        datasets.append({
            "label": f"ONT {ont}",
            "data": points,
            "fill": False,
            "tension": 0.3,
        })

    ont_summary: list[dict] = []
    for ont in sorted(by_ont.keys(), key=lambda o: _ont_sort_key(o, ont_cto)):
        lv = last_by_ont.get(ont)
        ont_summary.append({
            "ont_key": ont,
            "cto": ont_cto.get(ont) or "",
            "access_id": ont_access.get(ont) or "",
            "last_hist_rx": None if lv is None else round(float(lv), 2),
            "last_hist_ts": last_ts_by_ont.get(ont),
        })

    last_values = [
        v for v in last_by_ont.values()
        if v is not None and not _is_historico_rx_down_placeholder(v)
    ]
    median_value = round(float(median(last_values)), 2) if last_values else "-"

    return {
        "ok": True,
        "labels": labels,
        "datasets": datasets,
        "pon": pon,
        "days": days_validado,
        "median": median_value,
        "total_onts": len(datasets),
        "status": "Activo" if datasets else "Sin datos",
        "rows": csv_rows,
        "ont_summary": ont_summary,
    }


def export_csv_potencias_historico_rama(ratc: str, days: int = 30) -> dict:
    """Devuelve CSV UTF-8 (sin BOM) del histórico según rama y rango."""
    payload = consultar_potencias_historico_rama(ratc, days=days)
    if not payload.get("ok"):
        return payload

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(["timestamp", "objectname", "ont", "rx_dbm", "pon"])
    for row in payload.get("rows", []):
        writer.writerow([
            row.get("timestamp", ""),
            row.get("objectname", ""),
            row.get("ont", ""),
            row.get("rx_dbm", ""),
            row.get("pon", ""),
        ])

    return {
        "ok": True,
        "csv": out.getvalue(),
        "ratc": (ratc or "").strip(),
        "days": payload.get("days", 30),
    }


def consultar_potencias_altiplano_ahora_rama(ratc: str) -> dict:
    """Lectura instantánea Altiplano para todas las ONT de la rama (sin persistir en BD).

    Valida RAMA vía `_resolver_pon_desde_rama` como el histórico. Timestamp `YYYY-MM-DD HH:MM:SS`.
    Las ONT sin operador soportado en Altiplano van con `rx_dbm: null` en `samples`.
    Se omiten entradas sin `ont_key` (p. ej. filas de inventario sin `object_name`).

    Los KPIs del formulario siguen mostrando solo el histórico en Postgres; el gráfico
    incorpora el punto en el cliente.
    """
    rama = (ratc or "").strip()
    if not rama:
        return {"ok": False, "status_code": 400, "error": "Parámetro ratc requerido"}

    pon = _resolver_pon_desde_rama(rama)
    if not pon:
        return {
            "ok": False,
            "status_code": 404,
            "error": "Rama RATC no encontrada en inventario",
        }

    rows = consultar_rama_potencias_altiplano_por_ont(rama)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Filas de inventario sin object_name dejan `ont_key` vacío: no son ONT identificable;
    # no deben ir al cliente (evita filas basura en tabla comparación / sampleMap).
    samples = [
        {"ont_key": str(r["ont_key"]).strip(), "rx_dbm": r["rx_dbm"]}
        for r in rows
        if str(r.get("ont_key") or "").strip()
    ]

    return {
        "ok": True,
        "timestamp": ts,
        "pon": pon,
        "samples": samples,
    }


def _strip_potencias_objectname_prefix(objectname: str) -> str:
    """Quita prefijo de telemetría (``v1__t_``, ``v7__t_``, …) de ``altiplano.potencias``."""
    return _POTENCIAS_OBJ_PREFIX_RE.sub("", str(objectname or "").strip())


def _normalizar_potencias_objectname(objectname: str) -> str:
    """Alinea ``v1__t_BA_OLTA_x:1-1-L-P-ONT`` al formato con guiones (como Altiplano)."""
    s = _strip_potencias_objectname_prefix(objectname)
    if ":1-1-" in s:
        base, resto = s.split(":1-1-", 1)
        return f"{base}-{resto}"
    return s


def _lt_key_from_potencias_objectname(objectname: str) -> str | None:
    """Deriva ``OLT.LT<n>`` desde ``objectname`` guardado en ``altiplano.potencias``."""
    normalized = _normalizar_potencias_objectname(objectname)
    m = re.match(r"^(BA_OLTA_[A-Za-z0-9_]+)-(\d+)", normalized)
    if m:
        return f"{m.group(1)}.LT{m.group(2)}"
    return lt_desde_object_name(normalized)


def _olt_prefix_from_lt(lt: str) -> str | None:
    """``BA_OLTA_ES01_01.LT2`` → ``BA_OLTA_ES01_01``."""
    lt_s = str(lt or "").strip()
    if ".LT" not in lt_s.upper():
        return None
    return lt_s.rsplit(".", 1)[0].strip() or None


def _procesar_filas_historico_por_lt(
    rows: list,
    lts_solicitados: set[str],
) -> dict[str, dict]:
    """Última RX por ``objectname`` agrupada por LT; excluye placeholder DOWN."""
    last_rx_by_lt: dict[str, dict[str, float]] = defaultdict(dict)

    for ts, objectname, rx in rows:
        if not isinstance(ts, datetime):
            continue
        lt_key = _lt_key_from_potencias_objectname(str(objectname or ""))
        if not lt_key or lt_key not in lts_solicitados:
            continue
        obj_s = _normalizar_potencias_objectname(str(objectname or ""))
        if not obj_s:
            continue
        if rx is None:
            continue
        rx_val = float(rx)
        if _is_historico_rx_down_placeholder(rx_val):
            continue
        prev = last_rx_by_lt[lt_key].get(obj_s)
        if prev is None or ts >= prev[0]:
            last_rx_by_lt[lt_key][obj_s] = (ts, rx_val)

    out: dict[str, dict] = {}
    for lt_key in lts_solicitados:
        rx_map = last_rx_by_lt.get(lt_key) or {}
        rx_values = [pair[1] for pair in rx_map.values()]
        resumen = resumen_semaforo_desde_rx_values(rx_values)
        peor = min(rx_values) if rx_values else None
        out[lt_key] = {
            "ROJAS": resumen["ROJAS"],
            "AMARILLAS": resumen["AMARILLAS"],
            "VERDES": resumen["VERDES"],
            "PEOR_RX": None if peor is None else round(float(peor), 2),
            "ONT_CON_RX": len(rx_values),
        }
    return out


def _merge_semaforo_historico_chunk(merged: dict[str, dict], chunk: dict[str, dict]) -> None:
    """Fusiona resultados por OLT sin pisar RAMAs/LTs ya resueltas con ceros vacíos."""
    for key, data in chunk.items():
        if int(data.get("ONT_CON_RX") or 0) > 0:
            merged[key] = data


def _semaforo_historico_por_lts_uncached(lts: list[str]) -> dict:
    """Última RX guardada por ONT en Postgres (sin ventana temporal)."""
    lts_norm = sorted({str(lt or "").strip() for lt in lts if str(lt or "").strip()})
    if not lts_norm:
        return {"ok": False, "status_code": 400, "error": "Parámetro lts requerido"}

    por_olt: dict[str, set[str]] = defaultdict(set)
    for lt in lts_norm:
        olt = _olt_prefix_from_lt(lt)
        if olt:
            por_olt[olt].add(lt)

    lts_set = set(lts_norm)
    merged: dict[str, dict] = {lt: {
        "ROJAS": 0,
        "AMARILLAS": 0,
        "VERDES": 0,
        "PEOR_RX": None,
        "ONT_CON_RX": 0,
    } for lt in lts_norm}

    with db_cursor() as cur:
        for olt in sorted(por_olt.keys()):
            cur.execute(
                QUERIES["historico_ultima_rx_por_olt"],
                (f"%{olt}-%", f"%{olt}:%"),
            )
            rows = cur.fetchall()
            chunk = _procesar_filas_historico_por_lt(rows, lts_set)
            _merge_semaforo_historico_chunk(merged, chunk)

    return {
        "ok": True,
        "mode": "ultima_guardada",
        "source": "historico",
        "lts": merged,
    }


def semaforo_historico_por_lts(lts: list[str], days: int | None = None) -> dict:
    """Resumen semafórico por LT desde la última RX en ``altiplano.potencias`` (Postgres).

    Ignora ``days`` (compatibilidad con clientes viejos): siempre usa la última
    medición persistida por ``objectname``, sin filtro temporal.
    """
    del days  # ventana temporal retirada: última guardada en BD
    lts_norm = sorted({str(lt or "").strip() for lt in lts if str(lt or "").strip()})
    cache_key = "|".join(lts_norm)
    return get_cached_historico_potencias(
        get_dashboard_historico_cache_seconds(),
        f"semaforo_lt|ultima_v2|{cache_key}",
        lambda: _semaforo_historico_por_lts_uncached(lts_norm),
    )


def _pon_desde_object_name_resuelto(object_name: str) -> str | None:
    """``BA_OLTA_x:1-1-L-P-…`` → ``BA_OLTA_x-L-P`` (misma regla que histórico por rama)."""
    obj_name = str(object_name or "").strip()
    m = _OBJ_RE.search(obj_name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    norm = _normalizar_potencias_objectname(obj_name)
    m2 = re.match(r"^(BA_OLTA_[A-Za-z0-9_]+-\d+-\d+)", norm)
    return m2.group(1) if m2 else None


def _pon_prefix_from_normalized_objectname(norm: str) -> str | None:
    m = re.match(r"^(BA_OLTA_[A-Za-z0-9_]+-\d+-\d+)", str(norm or "").strip())
    return m.group(1) if m else None


def _olt_desde_pon(pon: str) -> str | None:
    m = re.match(r"^(BA_OLTA_[A-Za-z0-9_]+)-\d+-\d+$", str(pon or "").strip())
    return m.group(1) if m else None


def _batch_pon_desde_ramas(ramas: list[str]) -> dict[str, str | None]:
    ramas_norm = [str(r or "").strip() for r in ramas if str(r or "").strip()]
    out: dict[str, str | None] = {r: None for r in ramas_norm}
    if not ramas_norm:
        return out
    with db_cursor() as cur:
        cur.execute(QUERIES["historico_resolver_pon_desde_ramas"], (ramas_norm,))
        rows = cur.fetchall()
    for path_atc, object_name in rows:
        rama = str(path_atc or "").strip()
        if rama:
            out[rama] = _pon_desde_object_name_resuelto(str(object_name or ""))
    return out


def _batch_ont_keys_por_ramas(ramas: list[str]) -> dict[str, set[str]]:
    ramas_norm = [str(r or "").strip() for r in ramas if str(r or "").strip()]
    out: dict[str, set[str]] = defaultdict(set)
    if not ramas_norm:
        return out
    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_ramas_batch"], (ramas_norm,))
        rows = cur.fetchall()
    for path_atc, obj_raw, obj_ui in rows:
        rama = str(path_atc or "").strip()
        if not rama:
            continue
        for col in (obj_raw, obj_ui):
            ok = _ont_key_from_object_name(col)
            if ok:
                out[rama].add(ok)
    return out


def _procesar_filas_historico_por_ramas(
    rows: list,
    ramas_solicitadas: set[str],
    pon_by_rama: dict[str, str | None],
    ont_keys_by_rama: dict[str, set[str]],
) -> dict[str, dict]:
    """Última RX por ONT de inventario IN SERVICE, agrupada por RAMA."""
    ramas_by_pon: dict[str, set[str]] = defaultdict(set)
    for rama in ramas_solicitadas:
        pon = pon_by_rama.get(rama)
        if pon:
            ramas_by_pon[pon].add(rama)

    last_rx: dict[str, dict[str, tuple]] = {r: {} for r in ramas_solicitadas}

    for ts, objectname, rx in rows:
        if not isinstance(ts, datetime):
            continue
        if rx is None:
            continue
        rx_val = float(rx)
        if _is_historico_rx_down_placeholder(rx_val):
            continue
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
            canon = f"{pon}-{ont_key}"
            prev = last_rx[rama].get(canon)
            if prev is None or ts >= prev[0]:
                last_rx[rama][canon] = (ts, rx_val)

    out: dict[str, dict] = {}
    for rama in ramas_solicitadas:
        rx_values = [pair[1] for pair in last_rx.get(rama, {}).values()]
        resumen = resumen_semaforo_desde_rx_values(rx_values)
        peor = min(rx_values) if rx_values else None
        out[rama] = {
            "ROJAS": resumen["ROJAS"],
            "AMARILLAS": resumen["AMARILLAS"],
            "VERDES": resumen["VERDES"],
            "PEOR_RX": None if peor is None else round(float(peor), 2),
            "ONT_CON_RX": len(rx_values),
        }
    return out


def _semaforo_historico_por_ramas_uncached(ramas: list[str]) -> dict:
    ramas_norm = sorted({str(r or "").strip() for r in ramas if str(r or "").strip()})
    if not ramas_norm:
        return {"ok": False, "status_code": 400, "error": "Parámetro ramas requerido"}

    pon_by_rama = _batch_pon_desde_ramas(ramas_norm)
    ont_keys_by_rama = _batch_ont_keys_por_ramas(ramas_norm)
    ramas_set = set(ramas_norm)
    merged: dict[str, dict] = {
        r: {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "ONT_CON_RX": 0}
        for r in ramas_norm
    }

    olts: set[str] = set()
    for pon in pon_by_rama.values():
        if pon:
            olt = _olt_desde_pon(pon)
            if olt:
                olts.add(olt)

    with db_cursor() as cur:
        for olt in sorted(olts):
            cur.execute(
                QUERIES["historico_ultima_rx_por_olt"],
                (f"%{olt}-%", f"%{olt}:%"),
            )
            rows = cur.fetchall()
            chunk = _procesar_filas_historico_por_ramas(
                rows, ramas_set, pon_by_rama, ont_keys_by_rama,
            )
            _merge_semaforo_historico_chunk(merged, chunk)

    return {
        "ok": True,
        "mode": "ultima_guardada",
        "source": "historico",
        "ramas": merged,
    }


def semaforo_historico_por_ramas(ramas: list[str]) -> dict:
    """Resumen semafórico por RAMA desde la última RX en ``altiplano.potencias``."""
    ramas_norm = sorted({str(r or "").strip() for r in ramas if str(r or "").strip()})
    cache_key = "|".join(ramas_norm)
    return get_cached_historico_potencias(
        get_dashboard_historico_cache_seconds(),
        f"semaforo_rama|ultima_v2|{cache_key}",
        lambda: _semaforo_historico_por_ramas_uncached(ramas_norm),
    )
