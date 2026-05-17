"""Servicios para dashboard de histórico de potencias por rama."""
import csv
import re
from collections import defaultdict
from datetime import datetime
from io import StringIO
from statistics import median

from db import db_cursor
from queries import QUERIES

from .inventory import consultar_rama_potencias_altiplano_por_ont


_OBJ_RE = re.compile(r"^(.*?):1-1-(\d+)-(\d+)-")
ALLOWED_HISTORICO_DAYS = (1, 7, 15, 30)


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
        obj_raw = r[4]
        if not obj_raw:
            continue
        ont_key = str(obj_raw).split("-")[-1].strip()
        if not ont_key:
            continue
        cto_by_ont[ont_key] = str(r[2] or "").strip()
        aid = r[0]
        if aid is not None:
            aid_s = str(aid).strip()
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
        ont_short = objectname_str.split("-")[-1]
        by_ont[ont_short][ts_key] = None if rx is None else float(rx)
        timestamps.add(ts_key)
        last_by_ont[ont_short] = None if rx is None else float(rx)
        if rx is not None:
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

    last_values = [v for v in last_by_ont.values() if v is not None]
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
