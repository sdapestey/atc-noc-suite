"""Servicios para dashboard de histórico de potencias."""
import csv
import re
from collections import defaultdict
from datetime import datetime
from io import StringIO
from statistics import median

from db import db_cursor
from queries import QUERIES


_OBJ_RE = re.compile(r"^(.*?):1-1-(\d+)-(\d+)-")
_SITE_RE = re.compile(r"^BA_OLTA_([^_:\s]+)")
ALLOWED_HISTORICO_DAYS = (7, 15, 30)
ALLOWED_HIERARCHY_LEVELS = ("sitio", "olt", "lt", "pon", "rama")


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


def _consultar_historico_por_pones(pones: list[str], days_validado: int, scope: str) -> dict:
    rows = []
    with db_cursor() as cur:
        for pon in pones:
            cur.execute(QUERIES["historico_potencias_por_pon"], (f"%{pon}-%", int(days_validado)))
            rows.extend(cur.fetchall())

    if not rows:
        return {
            "ok": False,
            "status_code": 200,
            "error": f"Sin muestras de potencia en el rango seleccionado ({days_validado} dias)",
        }

    rows.sort(key=lambda item: item[0] if isinstance(item[0], datetime) else datetime.min)
    by_ont = defaultdict(dict)
    timestamps = set()
    last_by_ont = {}
    csv_rows = []
    pones_seen = set()
    for ts, objectname, rx in rows:
        if not isinstance(ts, datetime):
            continue
        ts_key = ts.strftime("%Y-%m-%d %H:%M")
        objectname_str = str(objectname)
        ont_short = objectname_str.rsplit(":", 1)[0]
        pones_seen.add("-".join(objectname_str.rsplit(":", 1)[0].split("-")[:-1]))
        by_ont[ont_short][ts_key] = None if rx is None else float(rx)
        timestamps.add(ts_key)
        last_by_ont[ont_short] = None if rx is None else float(rx)
        csv_rows.append({
            "timestamp": ts_key,
            "objectname": objectname_str,
            "ont": ont_short,
            "rx_dbm": None if rx is None else round(float(rx), 2),
            "pon": "-".join(objectname_str.rsplit(":", 1)[0].split("-")[:-1]),
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

    last_values = [v for v in last_by_ont.values() if v is not None]
    median_value = round(float(median(last_values)), 2) if last_values else "-"

    return {
        "ok": True,
        "labels": labels,
        "datasets": datasets,
        "pon": pones[0] if len(pones) == 1 else "MULTI",
        "pones": sorted([p for p in pones_seen if p]),
        "scope": scope,
        "days": days_validado,
        "median": median_value,
        "total_onts": len(datasets),
        "status": "Activo" if datasets else "Sin datos",
        "rows": csv_rows,
    }


def _parse_hierarchy_from_objectname(object_name: str) -> dict | None:
    m = _OBJ_RE.search(object_name or "")
    if not m:
        return None
    olt = m.group(1).strip()
    lt = m.group(2).strip()
    pon = m.group(3).strip()
    site_match = _SITE_RE.search(olt)
    sitio = site_match.group(1).strip() if site_match else olt
    return {
        "sitio": sitio,
        "olt": olt,
        "lt": lt,
        "pon": f"{olt}-{lt}-{pon}",
    }


def _cargar_hierarchy_mapping() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(QUERIES["historico_hierarchy_mapping"])
        rows = cur.fetchall()
    out = []
    for rama, object_name in rows:
        rama_val = str(rama or "").strip()
        obj_val = str(object_name or "").strip()
        if not rama_val or not obj_val:
            continue
        parsed = _parse_hierarchy_from_objectname(obj_val)
        if not parsed:
            continue
        parsed["rama"] = rama_val
        out.append(parsed)
    return out


def consultar_historico_hierarchy_tree() -> dict:
    rows = _cargar_hierarchy_mapping()
    if not rows:
        return {"ok": True, "tree": []}

    nested = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(set))))
    for item in rows:
        nested[item["sitio"]][item["olt"]][item["lt"]][item["pon"]].add(item["rama"])

    tree = []
    for sitio in sorted(nested.keys()):
        olts = []
        for olt in sorted(nested[sitio].keys()):
            lts = []
            for lt in sorted(nested[sitio][olt].keys(), key=lambda v: int(v) if v.isdigit() else v):
                pones = []
                for pon in sorted(nested[sitio][olt][lt].keys()):
                    ramas = sorted(nested[sitio][olt][lt][pon])
                    pones.append({"name": pon, "ramas": ramas})
                lts.append({"name": lt, "pones": pones})
            olts.append({"name": olt, "lts": lts})
        tree.append({"name": sitio, "olts": olts})
    return {"ok": True, "tree": tree}


def _resolver_pones_desde_nivel(level: str, value: str, mapping_rows: list[dict]) -> list[str]:
    level_norm = str(level or "").strip().lower()
    value_norm = str(value or "").strip()
    if level_norm not in ALLOWED_HIERARCHY_LEVELS or not value_norm:
        return []

    filtered = []
    if level_norm == "sitio":
        filtered = [row for row in mapping_rows if row["sitio"] == value_norm]
    elif level_norm == "olt":
        filtered = [row for row in mapping_rows if row["olt"] == value_norm]
    elif level_norm == "lt":
        filtered = [row for row in mapping_rows if row["lt"] == value_norm]
    elif level_norm == "pon":
        filtered = [row for row in mapping_rows if row["pon"] == value_norm]
    elif level_norm == "rama":
        filtered = [row for row in mapping_rows if row["rama"] == value_norm]
    return sorted({row["pon"] for row in filtered})


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
            "error": "Parámetro days inválido. Valores permitidos: 7, 15, 30",
        }

    pon = _resolver_pon_desde_rama(rama)
    if not pon:
        return {
            "ok": False,
            "status_code": 404,
            "error": "Rama RATC no encontrada en inventario",
        }
    payload = _consultar_historico_por_pones([pon], days_validado, scope=f"rama:{rama}")
    if payload.get("ok"):
        payload["ratc"] = rama
    return payload


def consultar_potencias_historico_hierarquia(level: str, value: str, days: int = 30) -> dict:
    """Devuelve histórico agregable desde nivel sitio/olt/lt/pon/rama."""
    days_validado = _validar_days(days)
    if days_validado is None:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 7, 15, 30",
        }
    level_norm = str(level or "").strip().lower()
    value_norm = str(value or "").strip()
    if level_norm not in ALLOWED_HIERARCHY_LEVELS:
        return {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro level inválido. Valores permitidos: sitio, olt, lt, pon, rama",
        }
    if not value_norm:
        return {"ok": False, "status_code": 400, "error": "Parámetro value requerido"}

    mapping_rows = _cargar_hierarchy_mapping()
    pones = _resolver_pones_desde_nivel(level_norm, value_norm, mapping_rows)
    if not pones:
        return {
            "ok": False,
            "status_code": 404,
            "error": f"No se encontraron PON para {level_norm}={value_norm}",
        }
    payload = _consultar_historico_por_pones(pones, days_validado, scope=f"{level_norm}:{value_norm}")
    if payload.get("ok"):
        payload["level"] = level_norm
        payload["value"] = value_norm
    return payload


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


def export_csv_potencias_historico_hierarquia(level: str, value: str, days: int = 30) -> dict:
    """Devuelve CSV UTF-8 (sin BOM) del histórico por nivel jerárquico."""
    payload = consultar_potencias_historico_hierarquia(level, value, days=days)
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
        "level": str(level or "").strip().lower(),
        "value": str(value or "").strip(),
        "days": payload.get("days", 30),
    }
