"""Dashboard por rama (árbol Postgres + potencias Altiplano)."""
from collections import defaultdict

from config import get_dashboard_rama_cache_seconds, get_dashboard_rama_power_cache_seconds
from db import db_cursor

from .dashboard_cache import get_cached_rama, get_cached_rama_inventario, get_cached_rama_potencias

from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    resumen_semaforo_desde_rx_values,
    natural_sort_key_str,
    principal_sort_key,
    region_desde_rama,
)
from .inventory import consultar_rama_estructura, consultar_rama_potencias


def _compute_dashboard_ramas():
    """Construye el árbol base de dashboard RAMA desde Postgres.

    Returns:
        Dict con ``bloques`` (lista por sitio principal) y ``totales`` (RAMAS/CTO/ONT).

    Notes:
        No consulta potencias; solo arma inventario estructural para UI y exportación.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.path_atc AS rama,
                COUNT(*)::int AS ont_count,
                COUNT(DISTINCT f.location_description)::int AS cto_count,
                COALESCE(
                    STRING_AGG(DISTINCT f.location_description, ' ' ORDER BY f.location_description),
                    ''
                ) AS ctos_search
            FROM cm.inventory_fat_occupation f
            WHERE f.status = 'IN SERVICE'
              AND f.path_atc IS NOT NULL
            GROUP BY f.path_atc
            ORDER BY f.path_atc
            """
        )
        rows = cur.fetchall()

    ramas = []
    for rama, ont_count, cto_count, ctos_search in rows:
        ramas.append({
            "RAMA": rama,
            "CTO_COUNT": int(cto_count or 0),
            "ONT_COUNT": int(ont_count or 0),
            "CTOS_SEARCH": str(ctos_search or ""),
            "ROJAS": 0,
            "AMARILLAS": 0,
            "VERDES": 0,
        })

    by_principal = defaultdict(list)
    for r in ramas:
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
        hierarchy.append({
            "PRINCIPAL": principal,
            "SEARCH_TEXT": " ".join(map(str, words)).lower(),
            "RAMAS": group,
        })

    totales = {
        "RAMAS": len(ramas),
        "CTO": sum(r["CTO_COUNT"] for r in ramas),
        "ONT": sum(r["ONT_COUNT"] for r in ramas),
    }
    return {"bloques": hierarchy, "totales": totales}


def dashboard_rama_bundle():
    """Árbol + totales en una sola lectura de caché (como mucho una query SQL por TTL)."""
    return get_cached_rama(get_dashboard_rama_cache_seconds(), _compute_dashboard_ramas)


def dashboard_ramas():
    """Árbol principal → rama → CTO (Postgres). Resultados cacheados por TTL."""
    return dashboard_rama_bundle()["bloques"]


def dashboard_rama_totales():
    """Totales globales RAMA / CTO / ONT para la barra superior (misma caché que `dashboard_ramas`)."""
    return dashboard_rama_bundle()["totales"]


def inventario_dashboard_rama(rama):
    """Inventario estructural de una rama: CTO -> ONT (sin potencias)."""
    if rama is None or not str(rama).strip():
        return {}
    rama_norm = str(rama).strip()

    def _compute():
        return dict(consultar_rama_estructura(rama_norm))

    return get_cached_rama_inventario(get_dashboard_rama_cache_seconds(), rama_norm, _compute)


def consultar_dashboard_rama(rama):
    """Consulta potencias de una rama y devuelve resumen semafórico.

    Args:
        rama: Identificador de rama (ej. `XX01-RATC-...`).

    Returns:
        Dict por CTO/AID con TX/RX y una clave extra `__dashboard_resumen__`
        con conteos `ROJAS`, `AMARILLAS`, `VERDES`.
    """
    if rama is None or not str(rama).strip():
        return {
            "__dashboard_resumen__": {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0},
        }

    rama_norm = str(rama).strip()

    def _compute():
        inv = consultar_rama_estructura(rama_norm)
        plist = consultar_rama_potencias(rama_norm)
        pot_by_aid = {p["AID"]: p for p in plist}

        resultado = {}
        rx_values = []

        for cto, rows in inv.items():
            resultado[cto] = {}
            for r in rows:
                aid = r["AID"]
                tx = pot_by_aid.get(aid, {}).get("TX")
                rx = pot_by_aid.get(aid, {}).get("RX")
                resultado[cto][aid] = {"TX": tx, "RX": rx}
                rx_values.append(rx)

        resultado["__dashboard_resumen__"] = resumen_semaforo_desde_rx_values(rx_values)
        return resultado

    ttl = get_dashboard_rama_power_cache_seconds()
    return get_cached_rama_potencias(ttl, rama_norm, _compute)
