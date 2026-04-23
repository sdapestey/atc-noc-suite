"""Dashboard por rama (árbol Postgres + potencias Altiplano)."""
from collections import defaultdict

from config import get_dashboard_rama_cache_seconds
from db import db_cursor

from altiplano import obtener_potencias_por_cto

from .dashboard_cache import get_cached_rama

from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    calcular_ne,
    clasificar_rx_dbm,
    natural_sort_key_str,
    nombre_operador,
    principal_sort_key,
    region_desde_rama,
)


def _compute_dashboard_ramas():
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.path_atc AS rama,
                f.location_description AS cto,
                f.access_id,
                o.invocator_system,
                REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui
            FROM cm.inventory_fat_occupation f
            JOIN cm.inventory_olt_occupation o
              ON o.access_id = f.access_id
            LEFT JOIN altiplano.serial s
              ON s.access_id = f.access_id
            WHERE f.status = 'IN SERVICE'
            ORDER BY f.path_atc, f.location_description, f.access_id
            """
        )
        rows = cur.fetchall()

    ramas = defaultdict(lambda: {
        "RAMA": None,
        "CTOS": defaultdict(list),
        "CTO_COUNT": 0,
        "ONT_COUNT": 0,
        "ROJAS": 0,
        "AMARILLAS": 0,
        "VERDES": 0,
    })

    for rama, cto, aid, op_id, object_name_ui in rows:
        if rama is None:
            continue

        r = ramas[rama]
        r["RAMA"] = rama
        ont_label = (object_name_ui or "").strip() or "—"
        r["CTOS"][cto].append({
            "AID": str(aid),
            "OPERADOR": nombre_operador(op_id),
            "ONT": ont_label,
            "TX": None,
            "RX": None,
        })
        r["ONT_COUNT"] += 1

    for r in ramas.values():
        r["CTO_COUNT"] = len(r["CTOS"])

    lista = list(ramas.values())
    by_principal = defaultdict(list)
    for r in lista:
        reg = region_desde_rama(r["RAMA"])
        principal = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)
        by_principal[principal].append(r)

    hierarchy = []
    for principal in sorted(by_principal.keys(), key=principal_sort_key):
        group = by_principal[principal]
        group.sort(key=lambda x: natural_sort_key_str(x["RAMA"]))
        words = [principal]
        for item in group:
            words.append(item["RAMA"])
            words.extend(item["CTOS"].keys())
        hierarchy.append({
            "PRINCIPAL": principal,
            "SEARCH_TEXT": " ".join(map(str, words)).lower(),
            "RAMAS": group,
        })
    return hierarchy


def dashboard_ramas():
    """Árbol principal → rama → CTO (Postgres). Resultados cacheados por TTL."""
    return get_cached_rama(get_dashboard_rama_cache_seconds(), _compute_dashboard_ramas)


def consultar_dashboard_rama(rama):
    if rama is None or not str(rama).strip():
        return {
            "__dashboard_resumen__": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0},
        }

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.location_description AS cto,
                f.access_id,
                s.object_name,
                o.invocator_system
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
            WHERE f.path_atc = %s
              AND f.status = 'IN SERVICE'
            """,
            (rama,),
        )
        rows = cur.fetchall()

    por_cto = defaultdict(list)
    for cto, aid, obj_raw, inv in rows:
        if not obj_raw:
            continue
        por_cto[cto].append({
            "AID": str(aid),
            "OBJ": obj_raw,
            "INV": inv,
        })

    resultado = {}
    rojas = 0
    amarillas = 0
    verdes = 0

    for cto, onts in por_cto.items():
        ne = calcular_ne(onts[0]["OBJ"])
        potencias = obtener_potencias_por_cto(
            ne,
            [(o["AID"], o["OBJ"], o["INV"]) for o in onts],
        )

        resultado[cto] = {}
        for o in onts:
            tx, rx = potencias.get(o["AID"], (None, None))
            resultado[cto][o["AID"]] = {"TX": tx, "RX": rx}
            estado = clasificar_rx_dbm(rx)
            if estado == "rojo":
                rojas += 1
            elif estado == "amarillo":
                amarillas += 1
            elif estado == "verde":
                verdes += 1

    resultado["__dashboard_resumen__"] = {
        "ROJAS": rojas,
        "AMARILLAS": amarillas,
        "VERDES": verdes,
    }
    return resultado
