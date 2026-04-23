"""Dashboard por OLT / LT."""
import copy
import re
from collections import defaultdict

from config import get_dashboard_olt_cache_seconds
from db import db_cursor

from .dashboard_cache import get_cached_olt
from .domain import (
    OLT_PRESENCIA_FORZADA,
    lt_desde_object_name,
    natural_sort_key_str,
    nombre_operador,
    principal_sort_key,
    principal_y_sitio_desde_olt,
)


def _is_fatc_path(path: str) -> bool:
    u = str(path).upper()
    return "-FATC-" in u


def _is_ratc_path(path: str) -> bool:
    u = str(path).upper()
    return "-RATC-" in u


def _nest_fatc_under_ratc(ramas_out: dict) -> dict:
    """
    Cuelga paths FATC bajo paths RATC del mismo LT.

    Las ONT tienen path_atc a nivel FATC; los paths RATC suelen ser agregadores sin
    ONT directas. No hay en esta API un campo padre RATC↔FATC desde BD.

    Repartos por índice (partición equitativa) dejan muchas RATC sin ninguna FATC
    cuando hay pocas FATC y muchas RATC (p. ej. 1 FATC y 7 RATC → solo la primera
    recibía hijos y el resto expandía vacío).

    Heurística: se sacan las FATC del mapa raíz y, por cada RATC, se copian **todas**
    las ramas FATC en ``SUBRAMAS`` (deep copy). Así al expandir cualquier RATC se
    ven las mismas FATC → CTO → ONT. Es redundante pero evita árboles vacíos hasta
    poder usar jerarquía real en inventario.
    """
    if not ramas_out:
        return ramas_out
    keys = list(ramas_out.keys())
    ratc_keys = [k for k in keys if _is_ratc_path(k)]
    fatc_keys = [k for k in keys if _is_fatc_path(k)]
    if not fatc_keys or not ratc_keys:
        return ramas_out

    ratc_sorted = sorted(ratc_keys, key=natural_sort_key_str)
    fatc_data = {fk: ramas_out.pop(fk) for fk in fatc_keys if fk in ramas_out}

    for ratc in ratc_sorted:
        if ratc not in ramas_out:
            continue
        sub = ramas_out[ratc].setdefault("SUBRAMAS", {})
        for fk, payload in fatc_data.items():
            sub[fk] = copy.deepcopy(payload)
    return ramas_out


def _lt_natural_order(lt_str: str):
    olt = lt_str.split(".")[0] if "." in lt_str else lt_str
    principal, codigo, _ = principal_y_sitio_desde_olt(olt)
    m = re.search(r"\.LT(\d+)$", lt_str, re.I)
    n = int(m.group(1)) if m else 0
    return (
        principal_sort_key(principal),
        natural_sort_key_str(codigo),
        natural_sort_key_str(olt),
        n,
        lt_str.lower(),
    )


def estructura_dashboard_lt(lt):
    """
    Inventario bajo un LT: RAMA → CTO → ONT (sin TX/RX).
    Las potencias se consultan aparte por RAMA, CTO o Access ID para no saturar Altiplano.
    """
    if not lt or not str(lt).strip():
        return {"RESUMEN": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "PEOR_RX": None}, "RAMAS": {}}

    lt = str(lt).strip()

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.path_atc AS rama,
                f.location_description AS cto,
                f.access_id,
                s.object_name,
                o.invocator_system
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
            WHERE f.status = 'IN SERVICE'
            """
        )
        rows = cur.fetchall()

    por_rama = defaultdict(lambda: defaultdict(list))
    for rama, cto, aid, obj_raw, inv in rows:
        if rama is None or not obj_raw:
            continue
        if lt_desde_object_name(obj_raw) != lt:
            continue
        por_rama[rama][cto].append({
            "AID": str(aid),
            "OPERADOR": nombre_operador(inv),
        })

    ramas_out = {}
    for rama in sorted(por_rama.keys(), key=natural_sort_key_str):
        ramas_out[rama] = {"CTOS": {}}
        for cto in sorted(por_rama[rama].keys(), key=natural_sort_key_str):
            ramas_out[rama]["CTOS"][cto] = por_rama[rama][cto]

    _nest_fatc_under_ratc(ramas_out)

    return {
        "RESUMEN": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0, "PEOR_RX": None},
        "RAMAS": ramas_out,
    }


def _compute_dashboard_olts():
    """
    Árbol: Sitio principal → OLT (BA_OLTA_…) → filas LT.
    Incluye OLT MR01_01..03 aunque no haya aún ONT en inventario.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.path_atc, f.location_description, s.object_name
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id=f.access_id
            WHERE f.status='IN SERVICE'
            """
        )
        rows = cur.fetchall()

    tree = defaultdict(lambda: {"ont": 0, "ramas": set(), "ctos": set()})
    for rama, cto, obj in rows:
        if not obj:
            continue
        lt = lt_desde_object_name(obj)
        if not lt:
            continue
        t = tree[lt]
        t["ont"] += 1
        if rama:
            t["ramas"].add(rama)
        if cto:
            t["ctos"].add(cto)

    for olt_forzado in OLT_PRESENCIA_FORZADA:
        if not any(k.startswith(olt_forzado + ".") for k in tree):
            tree[f"{olt_forzado}.LT1"] = {"ont": 0, "ramas": set(), "ctos": set()}

    rows_flat = []
    for lt in sorted(tree.keys(), key=_lt_natural_order):
        info = tree[lt]
        olt = lt.split(".")[0]
        principal, sitio_codigo, _ = principal_y_sitio_desde_olt(olt)
        rows_flat.append({
            "PRINCIPAL": principal,
            "SITIO_CODIGO": sitio_codigo,
            "OLT_LOGICO": olt,
            "LT": lt,
            "RAMAS": len(info["ramas"]),
            "CTO_COUNT": len(info["ctos"]),
            "ONT_COUNT": info["ont"],
            "ROJAS": 0,
            "AMARILLAS": 0,
            "VERDES": 0,
            "PEOR_RX": None,
        })

    nested = defaultdict(lambda: defaultdict(list))
    for row in rows_flat:
        nested[row["PRINCIPAL"]][row["OLT_LOGICO"]].append(row)

    hierarchy = []
    for principal in sorted(nested.keys(), key=principal_sort_key):
        olts_list = []
        for olt in sorted(
            nested[principal].keys(),
            key=lambda o: (natural_sort_key_str(principal_y_sitio_desde_olt(o)[1]), o),
        ):
            lts = nested[principal][olt]
            _, codigo, _ = principal_y_sitio_desde_olt(olt)
            olt_search = " ".join(
                [principal, olt, codigo] + [x["LT"] for x in lts]
            ).lower()
            olts_list.append({
                "OLT_LOGICO": olt,
                "SITIO_CODIGO": codigo,
                "SEARCH_TEXT": olt_search,
                "LTS": lts,
            })
        principal_search = " ".join([principal] + [o["SEARCH_TEXT"] for o in olts_list])
        hierarchy.append({
            "PRINCIPAL": principal,
            "SEARCH_TEXT": principal_search,
            "OLTS": olts_list,
        })
    return hierarchy


def dashboard_olts():
    """Árbol OLT/LT (Postgres). Resultados cacheados por TTL."""
    return get_cached_olt(get_dashboard_olt_cache_seconds(), _compute_dashboard_olts)
