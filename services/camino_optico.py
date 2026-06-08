"""Dashboard prueba: camino óptico (FAT + cm_report_isp)."""
from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from urllib.parse import quote_plus

from db import db_cursor

from .camino_gis import (
    cabecera_desde_rama,
    cabecera_para_fosc,
    consultar_ci_op_por_rama,
    consultar_cto_coordenadas_desde_sfat,
    consultar_feeder_distribucion_planta_interna,
    consultar_fusiones_verificacion_rama,
    consultar_fosc_cerca_trazado_ramas,
    consultar_fosc_ordenadas_en_rama,
    es_codigo_fusion_planta,
    resolver_rama_desde_fusion_planta,
    snap_corte_a_fosc,
)
from .dashboard_olt import dashboard_olts
from .domain import (
    nombre_operador,
    lt_desde_object_name,
    natural_sort_key_str,
    principal_y_sitio_desde_olt,
    region_desde_rama,
    split_index_query_tokens,
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
)
from .inventory import consultar_cto_coordenadas, consultar_cto_coordenadas_batch, consultar_cto_direccion_postal

# Paleta alineada con LT_OVERLAY_PALETTE en dashboard_camino_optico.html
RAMA_MASIVO_PALETTE = [
    {"line": "#3b82f6", "point": "#3b82f6"},
    {"line": "#22c55e", "point": "#22c55e"},
    {"line": "#f59e0b", "point": "#f59e0b"},
    {"line": "#ef4444", "point": "#ef4444"},
    {"line": "#a855f7", "point": "#a855f7"},
    {"line": "#06b6d4", "point": "#06b6d4"},
    {"line": "#84cc16", "point": "#84cc16"},
    {"line": "#ec4899", "point": "#ec4899"},
    {"line": "#f97316", "point": "#f97316"},
    {"line": "#14b8a6", "point": "#14b8a6"},
]

# Límite de ramas a fusionar en PostGIS (evita timeouts en sitios grandes).
MAX_RAMAS_CAMINO_AGREGADO = 120

logger = logging.getLogger(__name__)

_LT_TAIL_RE = re.compile(r"^(.+)\.LT(\d+)$", re.I)


def _normalize_lt_key(lt: str) -> str:
    s = (lt or "").strip()
    m = _LT_TAIL_RE.match(s)
    if not m:
        return s.upper()
    return f"{m.group(1).upper()}.LT{int(m.group(2))}"


def _lt_object_name_coincide(obj_raw, query_norm: str) -> bool:
    sn = lt_desde_object_name(obj_raw)
    if not sn:
        return False
    return _normalize_lt_key(sn) == query_norm


def olt_prefix_desde_lt_string(lt: str) -> str | None:
    """Prefijo de equipo antes de ``.LTn`` (ej. ``BA_OLTA_SF01_01``)."""
    s = (lt or "").strip()
    m = _LT_TAIL_RE.match(s)
    if not m:
        return None
    return m.group(1).upper()


def list_lts_mismo_olt(olt_prefix: str) -> list[str]:
    """Lista normalizada de todos los LT del mismo OLT lógico (inventario en servicio)."""
    op = (olt_prefix or "").strip().upper()
    if not op:
        return []
    found: set[str] = set()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT s.object_name
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            WHERE f.status = 'IN SERVICE'
            """
        )
        for (obj_raw,) in cur.fetchall():
            sn = lt_desde_object_name(obj_raw)
            if not sn:
                continue
            pfx = olt_prefix_desde_lt_string(sn)
            if pfx == op:
                found.add(_normalize_lt_key(sn))
    return sorted(found, key=natural_sort_key_str)


def _looks_like_lt_token(valor: str) -> bool:
    v = (valor or "").strip()
    if not v:
        return False
    if "_OLTA_" not in v.upper():
        return False
    return bool(re.search(r"\.LT\d+$", v, re.I))


def resolve_camino_sitio_token(raw: str) -> tuple[str | None, str]:
    """Resuelve entrada de sitio: nombre (ej. Moreno), código MR01 o ``sitio:…``.

    Returns:
        ``("principal", nombre)``, ``("region", MR01)`` o ``(None, "")``.
    """
    t = (raw or "").strip()
    if t.lower().startswith("sitio:"):
        t = t.split(":", 1)[1].strip()
    if not t:
        return None, ""
    if re.fullmatch(r"[A-Za-z]{2}\d{2}", t):
        return "region", t.upper()
    tl = t.lower()
    principals = set(SITIO_PRINCIPAL_POR_REGION.values())
    for p in principals:
        if p.lower() == tl:
            return "principal", p
    if tl == "otros":
        return "principal", SITIO_PRINCIPAL_DEFAULT
    tu = t.upper()
    if tu in SITIO_PRINCIPAL_POR_REGION:
        return "region", tu
    return None, ""


def infer_camino_consulta_tipo(valor: str) -> str | None:
    """Deduce tipo de consulta: CTO, rama, Access ID, LT o sitio.

    Returns:
        ``cto``, ``rama``, ``access_id``, ``lt``, ``sitio`` o ``None``.
    """
    v_raw = (valor or "").strip()
    if not v_raw:
        return None
    u = v_raw.upper()
    if "FATC" in u:
        return "cto"
    if es_codigo_fusion_planta(v_raw):
        return "fusion_planta"
    if "RATC" in u or "NATC" in u:
        return "rama"
    digits_only = re.sub(r"\s+", "", v_raw)
    if re.fullmatch(r"\d+", digits_only):
        return "access_id"
    if _looks_like_lt_token(v_raw):
        return "lt"
    if resolve_camino_sitio_token(v_raw)[0]:
        return "sitio"
    return None


def _ramas_desde_inventario_por_lt(lt: str) -> list[str]:
    lt_key = str(lt).strip()
    if not lt_key:
        return []
    query_norm = _normalize_lt_key(lt_key)
    ramas: set[str] = set()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.path_atc, s.object_name
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            WHERE f.status = 'IN SERVICE'
            """
        )
        for path_atc, obj_raw in cur.fetchall():
            if _lt_object_name_coincide(obj_raw, query_norm) and path_atc:
                ramas.add(str(path_atc))
    return sorted(ramas)


def _ramas_desde_inventario_por_principal(principal: str) -> list[str]:
    principal = (principal or "").strip()
    if not principal:
        return []
    ramas: set[str] = set()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.path_atc, s.object_name
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            WHERE f.status = 'IN SERVICE'
            """
        )
        for path_atc, obj_raw in cur.fetchall():
            if not path_atc:
                continue
            lt = lt_desde_object_name(obj_raw)
            if not lt:
                continue
            olt = lt.split(".")[0]
            pr, _, _ = principal_y_sitio_desde_olt(olt)
            if pr == principal:
                ramas.add(str(path_atc))
    return sorted(ramas)


def _ramas_desde_inventario_por_region(region: str) -> list[str]:
    region = (region or "").strip().upper()
    if not region:
        return []
    ramas: set[str] = set()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT f.path_atc
            FROM cm.inventory_fat_occupation f
            WHERE f.status = 'IN SERVICE'
              AND f.path_atc IS NOT NULL
            """
        )
        for (path_atc,) in cur.fetchall():
            p = str(path_atc)
            if p.upper().startswith(region + "-") or region_desde_rama(p) == region:
                ramas.add(p)
    return sorted(ramas)


def gis_payload_para_lt(lt: str) -> dict:
    """GIS + marcadores para un LT (para dashboard y endpoint de superposición)."""
    lt = (lt or "").strip()
    if not lt:
        return {"ok": False, "error": "LT vacío"}
    ramas = _ramas_desde_inventario_por_lt(lt)
    if not ramas:
        return {"ok": False, "error": "Sin ramas en inventario para ese LT", "lt": lt}
    if len(ramas) > MAX_RAMAS_CAMINO_AGREGADO:
        return {
            "ok": False,
            "error": (
                f"Demasiadas ramas ({len(ramas)}) para un solo mapa "
                f"(máx. {MAX_RAMAS_CAMINO_AGREGADO})."
            ),
            "lt": lt,
            "resumen": {"rama_count": len(ramas)},
        }
    cto_markers = _cto_markers_para_ramas(ramas, "")
    try:
        gis = _gis_merge_para_ramas(ramas)
    except Exception:
        logger.exception("GIS LT (ramas %s) falló", ramas)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}
    return {
        "ok": True,
        "lt": lt,
        "resumen": {"rama_count": len(ramas), "ramas": ramas},
        "cto_markers": cto_markers,
        "gis": gis,
    }


def dashboard_camino_optico_lt(lt: str):
    """Agrega trazado GIS y CTOs para todas las ramas de un LT (misma lógica que dashboard OLT)."""
    lt = (lt or "").strip()
    if not lt:
        return {"error": "LT vacío"}
    payload = gis_payload_para_lt(lt)
    if not payload.get("ok"):
        out = {
            "error": payload.get("error") or "Error",
            "lt": payload.get("lt", lt),
        }
        if payload.get("resumen"):
            out["resumen"] = payload["resumen"]
        return out
    olt = olt_prefix_desde_lt_string(lt)
    siblings = list_lts_mismo_olt(olt) if olt else []
    ramas_list = payload["resumen"].get("ramas") or []
    r0 = ramas_list[0] if ramas_list else None
    sitio_q = _sitio_valor_para_consulta(olt, r0)
    payload_lt_nav = {"tipo": "lt", "lt": payload["lt"], "sitio": "", "rama": ""}
    jerarquia_nav = _jerarquia_nav_armar(
        "lt",
        payload_lt_nav,
        sitio_consulta=sitio_q,
        lt_val=payload["lt"],
        ramas_vals=[],
        cto_val=None,
        access_val=None,
        pasos_equipo=_paso_equipo_focal_desde_olt(olt),
    )
    return {
        "tipo": "lt",
        "lt": payload["lt"],
        "olt_logico": olt or "",
        "lts_mismo_olt": siblings,
        "jerarquia_nav": jerarquia_nav,
        "resumen": {
            "rama_count": payload["resumen"]["rama_count"],
            "ramas": payload["resumen"]["ramas"],
        },
        "cto_markers": payload["cto_markers"],
        "gis": payload["gis"],
    }


def dashboard_camino_optico_equipo(olt_logico: str) -> dict:
    """Mapa agregado por equipo OLT (todas las ramas de todos los LT de ese prefijo)."""
    olt = (olt_logico or "").strip().upper()
    if not olt:
        return {"error": "Equipo OLT vacío"}
    if "_OLTA_" not in olt or not olt.startswith("BA_OLTA_"):
        return {
            "error": "Formato de equipo no reconocido (esperado p. ej. BA_OLTA_MR01_01)",
            "olt_logico": olt_logico,
        }
    lts = list_lts_mismo_olt(olt)
    if not lts:
        return {"error": "Sin LT en inventario para ese equipo", "olt_logico": olt}
    all_ramas: set[str] = set()
    for lt_key in lts:
        all_ramas.update(_ramas_desde_inventario_por_lt(lt_key))
    ramas_sorted = sorted(all_ramas)
    if len(ramas_sorted) > MAX_RAMAS_CAMINO_AGREGADO:
        return {
            "error": (
                f"Demasiadas ramas ({len(ramas_sorted)}) para un solo mapa "
                f"(máx. {MAX_RAMAS_CAMINO_AGREGADO}). Acotá por un LT concreto."
            ),
            "olt_logico": olt,
            "resumen": {"rama_count": len(ramas_sorted)},
        }
    cto_markers = _cto_markers_para_ramas(ramas_sorted, "")
    try:
        gis = _gis_merge_para_ramas(ramas_sorted)
    except Exception:
        logger.exception("GIS equipo OLT (ramas %s) falló", ramas_sorted)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}
    principal, codigo, _ = principal_y_sitio_desde_olt(olt)
    sitio_q = _sitio_valor_para_consulta(olt, ramas_sorted[0] if ramas_sorted else None)
    pasos_eq = _pasos_equipo_desde_contexto(principal)
    payload_eq = {"tipo": "equipo", "olt_logico": olt, "sitio": principal, "lt": ""}
    jerarquia_nav = _jerarquia_nav_armar(
        "equipo",
        payload_eq,
        sitio_consulta=sitio_q or principal,
        lt_val=None,
        ramas_vals=[],
        cto_val=None,
        access_val=None,
        pasos_equipo=pasos_eq,
    )
    return {
        "tipo": "equipo",
        "olt_logico": olt,
        "lt": lts[0] if lts else "",
        "sitio_codigo": codigo,
        "sitio_principal": principal,
        "lts_mismo_olt": lts,
        "jerarquia_nav": jerarquia_nav,
        "resumen": {
            "rama_count": len(ramas_sorted),
            "ramas": ramas_sorted,
        },
        "cto_markers": cto_markers,
        "gis": gis,
    }


def dashboard_camino_optico_sitio(token: str):
    """Mapa agregado por sitio principal (ej. Moreno) o por código de región (ej. MR01)."""
    mode, key = resolve_camino_sitio_token(token)
    if not mode or not key:
        return {"error": "Sitio no reconocido. Ej.: Moreno, MR01, sitio:Tigre"}
    if mode == "principal":
        ramas = _ramas_desde_inventario_por_principal(key)
        label = key
    else:
        ramas = _ramas_desde_inventario_por_region(key)
        label = key
    if not ramas:
        return {
            "error": "Sin ramas en inventario para ese criterio de sitio",
            "sitio": label,
            "sitio_modo": mode,
        }
    if len(ramas) > MAX_RAMAS_CAMINO_AGREGADO:
        return {
            "error": (
                f"Demasiadas ramas ({len(ramas)}) para un solo mapa "
                f"(máx. {MAX_RAMAS_CAMINO_AGREGADO}). Acotá por LT (ej. BA_OLTA_MR01_01.LT1)."
            ),
            "sitio": label,
            "sitio_modo": mode,
            "resumen": {"rama_count": len(ramas)},
        }
    cto_markers = _cto_markers_para_ramas(ramas, "")
    try:
        gis = _gis_merge_para_ramas(ramas)
    except Exception:
        logger.exception("GIS sitio (ramas %s) falló", ramas)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}
    payload_sitio = {"tipo": "sitio", "sitio": label}
    pr_tree = _principal_arbol_desde_sitio_respuesta(label, mode)
    pasos_eq = _pasos_equipo_desde_contexto(pr_tree)
    jerarquia_nav = _jerarquia_nav_armar(
        "sitio",
        payload_sitio,
        sitio_consulta=label,
        lt_val=None,
        ramas_vals=[],
        cto_val=None,
        access_val=None,
        pasos_equipo=pasos_eq,
    )
    return {
        "tipo": "sitio",
        "sitio": label,
        "sitio_modo": mode,
        "jerarquia_nav": jerarquia_nav,
        "resumen": {
            "rama_count": len(ramas),
            "ramas": ramas,
        },
        "cto_markers": cto_markers,
        "gis": gis,
    }


def _cto_maps_url_for_fatc_location(cto_fat: str) -> str | None:
    """URL de Google Maps si hay coordenadas reales (misma regla que índice / access_id)."""
    cto_fat = (cto_fat or "").strip()
    if not cto_fat:
        return None
    coords = consultar_cto_coordenadas(cto_fat)
    if not coords:
        return None
    lat_lon = f"{coords['lat']},{coords['lon']}"
    return (
        "https://www.google.com/maps/search/?api=1&query="
        f"{quote_plus(lat_lon)}"
    )


def _report_isp_por_rama(cur, path_atc):
    """Obtiene una fila reciente de `cm_report_isp` para una rama.

    Args:
        cur: Cursor abierto de Postgres.
        path_atc: Rama/path ATC.

    Returns:
        Diccionario con columnas del reporte ISP o `None` si no hay fila.
    """
    if not path_atc:
        return None
    cur.execute(
        """
        SELECT
            headend,
            headend_name,
            shelter,
            olt_rack,
            olt_name,
            olt_slot,
            olt_card,
            olt_port,
            olt_port_type,
            cable_patch_cord_name,
            cable_trunk_name,
            cable_trunk_fiber,
            cable_trunk_fiber_color,
            fec_name,
            fec_port,
            pp_name,
            path_atc,
            cable_feeder_name,
            cable_feeder_description,
            feeder_fiber_group,
            feeder_fiber_group_color,
            cable_feeder_fibber_color
        FROM cm.cm_report_isp
        WHERE path_atc = %s
        ORDER BY upload_date DESC NULLS LAST
        LIMIT 1
        """,
        (path_atc,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = [d[0] for d in cur.description]
    return {k: (v if v is not None else "") for k, v in zip(keys, row)}


def _cto_markers_para_ramas(ramas: list[str], focal_cto: str) -> list[dict]:
    """Marcadores Leaflet: CTOs en servicio en las ramas dadas; marca la CTO buscada.

    La consulta SQL usa una conexión y se cierra antes de resolver coordenadas por CTO,
    para no anidar ``db_cursor()`` (evita deadlock si ``DB_POOL_MAX`` es 1).
    """
    ramas = [r for r in ramas if r]
    focal_u = (focal_cto or "").strip().upper()
    if not ramas:
        return []
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.location_description, COUNT(*)::bigint
            FROM cm.inventory_fat_occupation f
            WHERE f.path_atc = ANY(%s) AND f.status = 'IN SERVICE'
            GROUP BY f.location_description
            ORDER BY f.location_description
            """,
            (ramas,),
        )
        rows = list(cur.fetchall())
    markers: list[dict] = []
    for row in rows:
        cto_id = row[0]
        if not cto_id:
            continue
        try:
            coords = consultar_cto_coordenadas(cto_id)
            source = "bajada_inventario"
            if not coords:
                coords = consultar_cto_coordenadas_desde_sfat(cto_id)
                source = "cm_sfat"
            if not coords:
                continue
            direccion_postal = None
            try:
                direccion_postal = consultar_cto_direccion_postal(str(cto_id))
            except Exception:
                logger.debug(
                    "dirección postal CTO marcador omitida (%s)", cto_id, exc_info=True
                )
            markers.append(
                {
                    "cto": str(cto_id),
                    "lat": float(coords["lat"]),
                    "lon": float(coords["lon"]),
                    "onts": int(row[1] or 0),
                    "source": source,
                    "focal": (str(cto_id).strip().upper() == focal_u),
                    "direccion_postal": direccion_postal,
                }
            )
        except Exception:
            logger.debug("coord CTO omitida en camino óptico (%s)", cto_id, exc_info=True)
    return markers


def _olt_base_desde_lt_key(lt_key: str | None) -> str | None:
    """Extrae nombre de OLT (sin ``.LTn``) desde una clave tipo ``BA_OLTA_MR01_01.LT1``."""
    if not lt_key or not str(lt_key).strip():
        return None
    m = re.match(r"^(.+)\.LT\d+$", str(lt_key).strip(), re.I)
    return m.group(1) if m else None


def _camino_contexto_desde_cto(
    cto: str,
    path_atcs: list[str],
    onts: list[dict],
) -> dict:
    """Resume jerarquía útil al operador: CTO → rama(s) RATC → LT → sitio (desde inventario)."""
    lt_set: set[str] = set()
    for o in onts:
        lt = lt_desde_object_name(o.get("object_name_ui"))
        if lt:
            lt_set.add(lt)
    lts_sorted = sorted(lt_set, key=natural_sort_key_str)
    primary_lt = lts_sorted[0] if lts_sorted else None
    olt_base = _olt_base_desde_lt_key(primary_lt)
    sitio_principal = None
    sitio_codigo = None
    if olt_base:
        sitio_principal, sitio_codigo, _ = principal_y_sitio_desde_olt(olt_base)

    site_fullname = (onts[0].get("site_fullname") if onts else None) or None
    physical_path = (onts[0].get("physical_path") if onts else None) or None

    return {
        "cto": (cto or "").strip(),
        "ramas": list(path_atcs),
        "lt": primary_lt,
        "lts": lts_sorted,
        "olt_logico": olt_base,
        "sitio_principal": sitio_principal,
        "sitio_codigo": sitio_codigo,
        "site_fullname": site_fullname,
        "physical_path": physical_path,
    }


def _nav_paso(
    tipo: str, valor: str | None, rotulo: str, titulo: str | None = None
) -> dict | None:
    v = (valor or "").strip()
    if not v:
        return None
    out: dict = {"tipo": tipo, "valor": v, "rotulo": rotulo}
    if titulo and str(titulo).strip():
        out["titulo"] = str(titulo).strip()
    return out


def _principal_arbol_desde_sitio_respuesta(
    sitio_label: str, sitio_modo: str | None
) -> str | None:
    """Nombre de sitio principal como en `dashboard_olts` (p. ej. Moreno)."""
    label = (sitio_label or "").strip()
    if not label:
        return None
    if (sitio_modo or "").strip() == "principal":
        if label == SITIO_PRINCIPAL_DEFAULT:
            return None
        return label
    reg = label.upper()
    return SITIO_PRINCIPAL_POR_REGION.get(reg)


def _equipo_nav_steps_mismo_sitio(principal: str | None) -> list[dict]:
    """Pasos jerárquicos Equipo (código MR01_0n + OLT) bajo un mismo sitio principal."""
    principal = (principal or "").strip()
    if not principal or principal == SITIO_PRINCIPAL_DEFAULT:
        return []
    pasos: list[dict] = []
    try:
        bloques = dashboard_olts()
    except Exception:
        logger.exception("dashboard_olts falló al armar pasos equipo camino")
        return []
    for bloque in bloques:
        if (bloque.get("PRINCIPAL") or "").strip() != principal:
            continue
        for o in bloque.get("OLTS") or []:
            olt_l = (o.get("OLT_LOGICO") or "").strip()
            cod = (o.get("SITIO_CODIGO") or "").strip()
            if not olt_l or not cod:
                continue
            p = _nav_paso("equipo", olt_l, "Equipo", titulo=cod)
            if p:
                pasos.append(p)
        break
    return pasos


def _pasos_equipo_desde_contexto(sitio_principal: str | None) -> list[dict] | None:
    steps = _equipo_nav_steps_mismo_sitio(sitio_principal)
    return steps if steps else None


def _paso_equipo_focal_desde_olt(olt_logico: str | None) -> list[dict] | None:
    """Paso Equipo único para una OLT concreta (sin listar otros equipos del sitio)."""
    olt = (olt_logico or "").strip()
    if not olt:
        return None
    _, sitio_codigo, _ = principal_y_sitio_desde_olt(olt)
    p = _nav_paso("equipo", olt, "Equipo", titulo=sitio_codigo or None)
    return [p] if p else None


def _principal_desde_sitio_q_rama(sitio_q: str, olt_hint: str | None) -> str | None:
    if olt_hint:
        pr, _, _ = principal_y_sitio_desde_olt(olt_hint)
        if pr and pr != SITIO_PRINCIPAL_DEFAULT:
            return pr
    sq = (sitio_q or "").strip()
    if not sq:
        return None
    if re.fullmatch(r"[A-Za-z]{2}\d{2}", sq):
        return SITIO_PRINCIPAL_POR_REGION.get(sq.upper())
    if sq != SITIO_PRINCIPAL_DEFAULT:
        return sq
    return None


def _sitio_valor_para_consulta(olt_base: str | None, rama_ref: str | None) -> str:
    """Token compatible con `dashboard_camino_optico_sitio` (nombre o código MR01)."""
    pr, _, _ = principal_y_sitio_desde_olt(olt_base or "")
    if pr and pr != SITIO_PRINCIPAL_DEFAULT:
        return pr
    if rama_ref:
        reg = region_desde_rama(rama_ref)
        if reg:
            return reg
    return ""


def _detalle_access_a_camino_contexto(d: dict) -> dict:
    """Misma forma que `camino_contexto` de CTO para panel y navegación."""
    lt = lt_desde_object_name(d.get("object_name_ui"))
    path = d.get("path_atc")
    ramas = [path] if path else []
    lts_sorted = [lt] if lt else []
    olt_base = _olt_base_desde_lt_key(lt)
    sitio_principal, sitio_codigo, _ = principal_y_sitio_desde_olt(olt_base or "")
    return {
        "cto": (d.get("location_description") or "").strip(),
        "ramas": list(ramas),
        "lt": lt,
        "lts": lts_sorted,
        "olt_logico": olt_base,
        "sitio_principal": sitio_principal,
        "sitio_codigo": sitio_codigo,
        "site_fullname": d.get("site_fullname"),
        "physical_path": d.get("physical_path"),
    }


def _object_name_muestra_rama(rama: str) -> str | None:
    rama = (rama or "").strip()
    if not rama:
        return None
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT s.object_name
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id = f.access_id
            WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
            LIMIT 1
            """,
            (rama,),
        )
        row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _nav_foco_payload(tipo: str, payload: dict) -> dict:
    if tipo == "sitio":
        return {"tipo": "sitio", "valor": (payload.get("sitio") or "").strip()}
    if tipo == "lt":
        return {"tipo": "lt", "valor": (payload.get("lt") or "").strip()}
    if tipo == "equipo":
        return {"tipo": "equipo", "valor": (payload.get("olt_logico") or "").strip()}
    if tipo == "rama":
        return {"tipo": "rama", "valor": (payload.get("rama") or "").strip()}
    if tipo == "cto":
        return {"tipo": "cto", "valor": (payload.get("cto") or "").strip()}
    if tipo == "access_id":
        det = payload.get("detalle") or {}
        av = det.get("access_id")
        return {"tipo": "access_id", "valor": str(av).strip() if av is not None else ""}
    return {"tipo": tipo, "valor": ""}


def _jerarquia_nav_armar(
    tipo_respuesta: str,
    payload: dict,
    *,
    sitio_consulta: str,
    lt_val: str | None,
    ramas_vals: list[str],
    cto_val: str | None,
    access_val: str | None,
    pasos_equipo: list[dict] | None = None,
) -> dict:
    pasos: list[dict] = []
    sp = _nav_paso("sitio", sitio_consulta, "Sitio")
    if sp:
        pasos.append(sp)
    pasos_equipo_filtrados = list(pasos_equipo or [])
    if lt_val and pasos_equipo_filtrados:
        olt_focal = _olt_base_desde_lt_key(lt_val)
        if olt_focal:
            pasos_match = [
                step
                for step in pasos_equipo_filtrados
                if isinstance(step, dict)
                and step.get("tipo") == "equipo"
                and (step.get("valor") or "").strip() == olt_focal
            ]
            if pasos_match:
                pasos_equipo_filtrados = pasos_match
    for step in pasos_equipo_filtrados:
        if isinstance(step, dict) and step.get("valor") and step.get("tipo"):
            pasos.append(step)
    np_lt = _nav_paso("lt", lt_val, "LT / equipo")
    if np_lt:
        pasos.append(np_lt)
    for r in ramas_vals:
        pr = _nav_paso("rama", r, "Rama")
        if pr:
            pasos.append(pr)
    for agregar in (
        _nav_paso("cto", cto_val, "CTO"),
        _nav_paso("access_id", access_val, "Access ID"),
    ):
        if agregar:
            pasos.append(agregar)
    return {
        "foco": _nav_foco_payload(tipo_respuesta, payload),
        "pasos": pasos,
    }


def _gis_merge_para_ramas(ramas: list[str]) -> dict:
    """Une geometrías `ci_op` de varias ramas en un único FeatureCollection."""
    ramas = [r for r in ramas if (r or "").strip()]
    if not ramas:
        return {"ok": False, "error": "Sin ramas para trazado GIS."}
    all_features: list[dict] = []
    meta: dict = {}
    last_error: str | None = None
    for rama in ramas:
        try:
            gis = consultar_ci_op_por_rama(rama)
        except Exception:
            logger.exception("GIS rama falló para %s", rama)
            gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}
        if gis.get("ok") and gis.get("geojson"):
            feats = gis["geojson"].get("features") or []
            all_features.extend(feats)
            if not meta:
                meta = {
                    k: v
                    for k, v in gis.items()
                    if k not in ("ok", "geojson", "error")
                }
        elif isinstance(gis, dict):
            last_error = gis.get("error") or last_error
    if not all_features:
        return {
            "ok": False,
            "error": last_error or "Sin geometría en ci_op para las ramas de esta CTO.",
        }
    out: dict = {
        "ok": True,
        "geojson": {"type": "FeatureCollection", "features": all_features},
    }
    out.update(meta)
    return out


def dashboard_camino_optico_cto(cto):
    """Consulta detalle de una CTO para el dashboard Camino Óptico.

    Args:
        cto: Identificador FATC.

    Returns:
        Dict con resumen, ONTs, caminos ISP por rama y link de mapas.
        Si no hay datos, devuelve `{"error": ...}`.
    """
    cto = (cto or "").strip()
    if not cto:
        return {"error": "CTO vacío"}

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.access_id,
                f.status,
                f.site_fullname,
                f.site_description,
                f.site_type,
                f.physical_path,
                f.path_atc,
                f.feeder_bentley,
                f.feeder_cm,
                f.fiber_feeder,
                f.location_fullname,
                f.location_description,
                f.location_name,
                f.location_type,
                f.alias_atc,
                f.component_name,
                f.componente_fullname,
                f.port_name,
                f.port_number,
                f.olt_odf_fiber,
                REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui,
                COALESCE(o.invocator_system, b_aid.operatorid) AS invocator_system
            FROM cm.inventory_fat_occupation f
            LEFT JOIN altiplano.serial s ON s.access_id = f.access_id
            LEFT JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
            LEFT JOIN LATERAL (
                SELECT
                    CASE
                        WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                        THEN trim(b2.operatorid::text)::bigint
                        ELSE NULL
                    END AS operatorid
                FROM aux.bajada_inventario b2
                WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(f.access_id::text))
                ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
                LIMIT 1
            ) b_aid ON true
            WHERE f.location_description = %s
              AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
            -- Mismo criterio que queries.onts_por_cto (orden OUT/puerto ConnectMaster).
            ORDER BY
                COALESCE(
                    f.port_number,
                    NULLIF(regexp_replace(COALESCE(f.port_name, ''), '[^0-9]', '', 'g'), '')::bigint
                ) NULLS LAST,
                f.access_id
            """,
            (cto,),
        )
        rows = cur.fetchall()
        colnames = [d[0] for d in cur.description]
        if not rows:
            return {"error": "Sin datos de inventario para esa CTO", "cto": cto}

        idx_path = colnames.index("path_atc")
        path_atcs = sorted({r[idx_path] for r in rows if r[idx_path]})

        isp_por_rama = {p: _report_isp_por_rama(cur, p) for p in path_atcs}

        onts = []
        for r in rows:
            d = {colnames[i]: r[i] for i in range(len(colnames))}
            inv = d.pop("invocator_system", None)
            d["OPERADOR"] = nombre_operador(inv)
            p = d.get("path_atc")
            d["camino_isp"] = isp_por_rama.get(p)
            onts.append(d)

    cto_markers = _cto_markers_para_ramas(path_atcs, cto)

    try:
        gis = _gis_merge_para_ramas(path_atcs)
    except Exception:
        logger.exception("GIS CTO (ramas %s) falló", path_atcs)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    cto_maps_url = _cto_maps_url_for_fatc_location(cto)

    camino_contexto = _camino_contexto_desde_cto(cto, path_atcs, onts)

    direccion_postal = None
    try:
        direccion_postal = consultar_cto_direccion_postal(cto)
    except Exception:
        logger.debug(
            "consultar_cto_direccion_postal omitida en camino CTO (%s)", cto, exc_info=True
        )

    ctx_r0 = (camino_contexto.get("ramas") or [None])[0]
    sitio_q = _sitio_valor_para_consulta(camino_contexto.get("olt_logico"), ctx_r0)
    payload_cto = {
        "tipo": "cto",
        "cto": cto,
        "detalle": {},
        "sitio": "",
        "rama": "",
        "lt": camino_contexto.get("lt") or "",
    }
    jerarquia_nav = _jerarquia_nav_armar(
        "cto",
        payload_cto,
        sitio_consulta=sitio_q,
        lt_val=camino_contexto.get("lt"),
        ramas_vals=list(camino_contexto.get("ramas") or []),
        cto_val=camino_contexto.get("cto"),
        access_val=None,
        pasos_equipo=_pasos_equipo_desde_contexto(camino_contexto.get("sitio_principal")),
    )

    return {
        "tipo": "cto",
        "cto": cto,
        "cto_maps_url": cto_maps_url,
        "direccion_postal": direccion_postal,
        "camino_contexto": camino_contexto,
        "jerarquia_nav": jerarquia_nav,
        "resumen": {
            "ont_count": len(onts),
            "rama_count": len(path_atcs),
            "ramas": path_atcs,
        },
        "caminos_isp_por_rama": isp_por_rama,
        "onts": onts,
        "cto_markers": cto_markers,
        "gis": gis,
        "planta_interna": _planta_interna_para_consulta(path_atcs, gis, focal_cto=cto),
    }


def dashboard_camino_optico_rama(rama, *, fusion_destacar: str | None = None):
    """Consulta vista agregada por rama para Camino Óptico.

    Args:
        rama: Identificador RATC.
        fusion_destacar: Código fusión planta a resaltar (p. ej. SF01-R1301-010).

    Returns:
        Dict con conteos (CTO/ONT), lista de CTOs y tramo ISP.
    """
    rama = (rama or "").strip()
    fusion_destacar = (fusion_destacar or "").strip().upper() or None
    if not rama:
        return {"error": "Rama vacía"}

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT f.location_description), COUNT(f.access_id)
            FROM cm.inventory_fat_occupation f
            WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
            """,
            (rama,),
        )
        cto_count, ont_count = cur.fetchone()
        cur.execute(
            """
            SELECT f.location_description, COUNT(*)::bigint
            FROM cm.inventory_fat_occupation f
            WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
            GROUP BY f.location_description
            ORDER BY f.location_description
            """,
            (rama,),
        )
        ctos = [{"cto": r[0], "onts": int(r[1])} for r in cur.fetchall()]
        isp = _report_isp_por_rama(cur, rama)

    cto_markers = _cto_markers_para_ramas([rama], "")

    try:
        gis = consultar_ci_op_por_rama(rama)
    except Exception:
        logger.exception("GIS rama falló para %s", rama)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    raw_obj = _object_name_muestra_rama(rama)
    lt_hint = lt_desde_object_name(raw_obj)
    olt_hint = _olt_base_desde_lt_key(lt_hint)
    sitio_q = _sitio_valor_para_consulta(olt_hint, rama)
    payload_rama = {"tipo": "rama", "rama": rama, "cto": "", "lt": lt_hint or "", "sitio": ""}
    jerarquia_nav = _jerarquia_nav_armar(
        "rama",
        payload_rama,
        sitio_consulta=sitio_q,
        lt_val=lt_hint,
        ramas_vals=[rama],
        cto_val=None,
        access_val=None,
        pasos_equipo=_paso_equipo_focal_desde_olt(olt_hint),
    )

    return {
        "tipo": "rama",
        "rama": rama,
        "jerarquia_nav": jerarquia_nav,
        "resumen": {
            "cto_count": int(cto_count or 0),
            "ont_count": int(ont_count or 0),
        },
        "ctos": ctos,
        "camino_isp": isp,
        "cto_markers": cto_markers,
        "gis": gis,
        "planta_interna": _planta_interna_para_consulta(
            [rama], gis, fusion_destacar=fusion_destacar
        ),
        "fusion_destacar": fusion_destacar,
    }


def dashboard_camino_optico_fusion_planta(codigo: str) -> dict[str, Any]:
    """Busca por código de fusión (``SF01-R1301-010``) y abre la rama RATC asociada."""
    codigo = (codigo or "").strip().upper()
    if not codigo:
        return {"error": "Código de fusión vacío."}
    resolved = resolver_rama_desde_fusion_planta(codigo)
    if not resolved.get("ok"):
        return {"error": resolved.get("error") or "Fusión no encontrada."}
    rama = resolved["rama"]
    out = dashboard_camino_optico_rama(rama, fusion_destacar=codigo)
    if out.get("error"):
        return out
    out["fusion_busqueda"] = codigo
    if resolved.get("nota"):
        pi = out.get("planta_interna") or {}
        fus = pi.get("fusiones") or {}
        fus["nota"] = resolved["nota"]
        pi["fusiones"] = fus
        out["planta_interna"] = pi
    return out


def dashboard_camino_optico_access_id(access_id):
    """Consulta una ONT puntual por Access ID para Camino Óptico.

    Args:
        access_id: Access ID numérico.

    Returns:
        Dict con detalle FAT, operador, tramo ISP y link de mapas.
        Si el formato es inválido o no hay datos, devuelve `{"error": ...}`.
    """
    aid = (access_id or "").strip()
    if not aid or not str(aid).isdigit():
        return {"error": "Access ID inválido (solo números)"}

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.access_id,
                f.status,
                f.site_fullname,
                f.site_description,
                f.site_type,
                f.physical_path,
                f.path_atc,
                f.feeder_bentley,
                f.feeder_cm,
                f.fiber_feeder,
                f.location_fullname,
                f.location_description,
                f.location_name,
                f.location_type,
                f.alias_atc,
                f.component_name,
                f.componente_fullname,
                f.port_name,
                f.port_number,
                f.olt_odf_fiber,
                REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui,
                COALESCE(o.invocator_system, b_aid.operatorid) AS invocator_system
            FROM cm.inventory_fat_occupation f
            LEFT JOIN altiplano.serial s ON s.access_id = f.access_id
            LEFT JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
            LEFT JOIN LATERAL (
                SELECT
                    CASE
                        WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                        THEN trim(b2.operatorid::text)::bigint
                        ELSE NULL
                    END AS operatorid
                FROM aux.bajada_inventario b2
                WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(f.access_id::text))
                ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
                LIMIT 1
            ) b_aid ON true
            WHERE f.access_id = %s AND f.status = 'IN SERVICE'
            LIMIT 1
            """,
            (aid,),
        )
        row = cur.fetchone()
        colnames = [d[0] for d in cur.description]
        if not row:
            return {"error": "Sin datos en servicio para ese Access ID"}

        d = {colnames[i]: row[i] for i in range(len(colnames))}
        inv = d.pop("invocator_system", None)
        d["OPERADOR"] = nombre_operador(inv)
        path = d.get("path_atc")
        d["camino_isp"] = _report_isp_por_rama(cur, path)
        ramas = [path] if path else []

    cto_markers = _cto_markers_para_ramas(ramas, d.get("location_description") or "")

    try:
        gis = _gis_merge_para_ramas(ramas)
    except Exception:
        logger.exception("GIS Access ID (rama %s) falló", ramas)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    cto_maps_url = _cto_maps_url_for_fatc_location(d.get("location_description") or "")

    direccion_postal = None
    try:
        loc = (d.get("location_description") or "").strip()
        if loc:
            direccion_postal = consultar_cto_direccion_postal(loc)
    except Exception:
        logger.debug(
            "consultar_cto_direccion_postal omitida en camino Access ID (%s)",
            access_id,
            exc_info=True,
        )

    camino_contexto = _detalle_access_a_camino_contexto(d)
    path_ref = (camino_contexto.get("ramas") or [None])[0]
    sitio_q = _sitio_valor_para_consulta(camino_contexto.get("olt_logico"), path_ref)
    jerarquia_nav = _jerarquia_nav_armar(
        "access_id",
        {"tipo": "access_id", "detalle": d},
        sitio_consulta=sitio_q,
        lt_val=camino_contexto.get("lt"),
        ramas_vals=list(camino_contexto.get("ramas") or []),
        cto_val=camino_contexto.get("cto"),
        access_val=str(aid),
        pasos_equipo=_pasos_equipo_desde_contexto(camino_contexto.get("sitio_principal")),
    )

    return {
        "tipo": "access_id",
        "detalle": d,
        "cto_maps_url": cto_maps_url,
        "direccion_postal": direccion_postal,
        "camino_contexto": camino_contexto,
        "jerarquia_nav": jerarquia_nav,
        "cto_markers": cto_markers,
        "gis": gis,
        "planta_interna": _planta_interna_para_consulta(
            ramas,
            gis,
            focal_cto=d.get("location_description") or "",
        ),
    }


def _parse_rama_masivo_tokens(raw_values) -> tuple[list[str], list[str]]:
    """Normaliza tokens de consulta masiva: solo ramas RATC, sin duplicados."""
    if isinstance(raw_values, str):
        tokens = split_index_query_tokens(raw_values)
    elif isinstance(raw_values, list):
        tokens: list[str] = []
        for v in raw_values:
            s = str(v or "").strip()
            if not s:
                continue
            if "," in s or "\n" in s:
                tokens.extend(split_index_query_tokens(s))
            else:
                tokens.append(s)
    else:
        tokens = []
    seen: set[str] = set()
    ramas: list[str] = []
    invalid: list[str] = []
    for t in tokens:
        tipo = infer_camino_consulta_tipo(t)
        if tipo != "rama":
            invalid.append(t)
            continue
        key = t.strip().upper()
        if key in seen:
            continue
        seen.add(key)
        ramas.append(t.strip())
    return ramas, invalid


def _rama_resumen_ligero(rama: str) -> dict:
    """Resumen inventario + ISP de una rama (sin GIS individual)."""
    rama = (rama or "").strip()
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT f.location_description), COUNT(f.access_id)
            FROM cm.inventory_fat_occupation f
            WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
            """,
            (rama,),
        )
        row = cur.fetchone()
        cto_count = int((row[0] if row else 0) or 0)
        ont_count = int((row[1] if row else 0) or 0)
        cur.execute(
            """
            SELECT f.location_description, COUNT(*)::bigint
            FROM cm.inventory_fat_occupation f
            WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
            GROUP BY f.location_description
            ORDER BY f.location_description
            """,
            (rama,),
        )
        ctos = [{"cto": r[0], "onts": int(r[1])} for r in cur.fetchall()]
        isp = _report_isp_por_rama(cur, rama)
    return {
        "rama": rama,
        "resumen": {"cto_count": cto_count, "ont_count": ont_count},
        "ctos": ctos,
        "camino_isp": isp,
        "sin_inventario": cto_count == 0 and ont_count == 0,
    }


def _build_ctos_union(ramas_data: list[dict]) -> list[dict]:
    """CTO únicas con conteo de ONT y ramas donde aparecen."""
    by_cto: dict[str, dict] = {}
    for rd in ramas_data:
        rama = rd.get("rama") or ""
        for c in rd.get("ctos") or []:
            cto = (c.get("cto") or "").strip()
            if not cto:
                continue
            if cto not in by_cto:
                by_cto[cto] = {"cto": cto, "onts": 0, "ramas": []}
            by_cto[cto]["onts"] += int(c.get("onts") or 0)
            if rama and rama not in by_cto[cto]["ramas"]:
                by_cto[cto]["ramas"].append(rama)
    out = list(by_cto.values())
    out.sort(key=lambda x: natural_sort_key_str(x.get("cto") or ""))
    for item in out:
        item["shared"] = len(item.get("ramas") or []) > 1
    return out


def _build_rama_colors(ramas: list[str]) -> dict[str, dict]:
    """Asigna color estable por rama (orden de la consulta)."""
    out: dict[str, dict] = {}
    palette_len = len(RAMA_MASIVO_PALETTE) or 1
    for i, rama in enumerate(ramas):
        pack = RAMA_MASIVO_PALETTE[i % palette_len]
        out[rama] = {"index": i % palette_len, "line": pack["line"], "point": pack["point"]}
    return out


def _resolve_cto_coords_map(ctos: list[str]) -> dict[str, dict]:
    """Coordenadas por CTO: inventario batch y fallback sfat."""
    cleaned = sorted({str(c).strip() for c in ctos if c and str(c).strip()})
    if not cleaned:
        return {}
    coords = consultar_cto_coordenadas_batch(cleaned)
    for cto in cleaned:
        if cto in coords:
            continue
        try:
            one = consultar_cto_coordenadas(cto)
            if not one:
                one = consultar_cto_coordenadas_desde_sfat(cto)
            if one:
                coords[cto] = one
        except Exception:
            logger.debug("coord CTO omitida en masivo (%s)", cto, exc_info=True)
    return coords


def _cto_markers_por_rama(ramas: list[str]) -> list[dict]:
    """Marcadores Leaflet por par (rama, CTO) para colorear cada rama."""
    pairs: list[tuple[str, str, int]] = []
    all_ctos: set[str] = set()
    for rama in ramas:
        rama = (rama or "").strip()
        if not rama:
            continue
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT f.location_description, COUNT(*)::bigint
                FROM cm.inventory_fat_occupation f
                WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
                GROUP BY f.location_description
                ORDER BY f.location_description
                """,
                (rama,),
            )
            rows = list(cur.fetchall())
        for cto_id, cnt in rows:
            if not cto_id:
                continue
            cto_s = str(cto_id)
            all_ctos.add(cto_s)
            pairs.append((rama, cto_s, int(cnt or 0)))
    coords = _resolve_cto_coords_map(list(all_ctos))
    markers: list[dict] = []
    for rama, cto, onts in pairs:
        c = coords.get(cto)
        if not c:
            continue
        markers.append(
            {
                "rama": rama,
                "cto": cto,
                "lat": float(c["lat"]),
                "lon": float(c["lon"]),
                "onts": onts,
            }
        )
    return markers


def _sugerir_ctos_medicion(
    ramas_data: list[dict],
    ctos_union: list[dict],
) -> list[dict]:
    """Sugiere CTO para medir ante un posible corte de fibra (heurística inventario)."""
    suggestions: list[dict] = []
    seen_cto_motivo: set[str] = set()

    def _add(cto: str, prioridad: str, motivo: str, ramas: list[str], score: int) -> None:
        cto = (cto or "").strip()
        if not cto:
            return
        key = cto + "|" + prioridad
        if key in seen_cto_motivo:
            return
        seen_cto_motivo.add(key)
        suggestions.append(
            {
                "cto": cto,
                "prioridad": prioridad,
                "motivo": motivo,
                "ramas": list(ramas),
                "score": score,
            }
        )

    for c in ctos_union:
        ramas_c = list(c.get("ramas") or [])
        if c.get("shared") and len(ramas_c) >= 2:
            _add(
                c["cto"],
                "alta",
                (
                    f"CTO compartida por {len(ramas_c)} ramas — tramo común; "
                    "medir aquí para acotar un corte."
                ),
                ramas_c,
                80,
            )

    for rd in ramas_data:
        if rd.get("sin_inventario"):
            continue
        ctos = rd.get("ctos") or []
        if not ctos:
            continue
        rama = rd.get("rama") or ""
        first = (ctos[0].get("cto") or "").strip()
        if first:
            _add(
                first,
                "media",
                f"Primera CTO en inventario de {rama} — punto de entrada típico para medir la rama.",
                [rama],
                50,
            )
        if len(ctos) >= 2:
            last = (ctos[-1].get("cto") or "").strip()
            if last and last != first:
                _add(
                    last,
                    "baja",
                    f"Última CTO en inventario de {rama} — extremo de distribución (corte posible aguas abajo).",
                    [rama],
                    35,
                )

    suggestions.sort(
        key=lambda x: (-int(x.get("score") or 0), natural_sort_key_str(x.get("cto") or ""))
    )
    return suggestions[:20]


# Rejilla ~24 m para detectar tramos comunes en ci_op (troncal compartida).
_CELDA_TRONCAL_GRADOS = 0.00022
_PASO_INTERPOLACION_TRONCAL_M = 40.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def _coords_latlon_from_geometry(geom: dict) -> list[tuple[float, float]]:
    """GeoJSON geometry -> [(lat, lon), ...] (orden Leaflet)."""
    if not geom:
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return []
    out: list[tuple[float, float]] = []

    def add_pair(lon: object, lat: object) -> None:
        try:
            lo, la = float(lon), float(lat)
        except (TypeError, ValueError):
            return
        if math.isnan(lo) or math.isnan(la):
            return
        if abs(la) > 90 or abs(lo) > 180:
            return
        out.append((la, lo))

    if gtype == "LineString":
        for pair in coords:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                add_pair(pair[0], pair[1])
    elif gtype == "MultiLineString":
        for line in coords:
            if not isinstance(line, (list, tuple)):
                continue
            for pair in line:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    add_pair(pair[0], pair[1])
    return out


def _celda_troncal(lat: float, lon: float) -> tuple[int, int]:
    g = _CELDA_TRONCAL_GRADOS
    return (int(round(lat / g)), int(round(lon / g)))


def _interpolate_line_latlon(
    points: list[tuple[float, float]], step_m: float = _PASO_INTERPOLACION_TRONCAL_M
) -> list[tuple[float, float]]:
    if len(points) < 2:
        return list(points)
    out: list[tuple[float, float]] = [points[0]]
    for i in range(len(points) - 1):
        la0, lo0 = points[i]
        la1, lo1 = points[i + 1]
        dist = _haversine_m(la0, lo0, la1, lo1)
        if dist <= step_m:
            out.append((la1, lo1))
            continue
        n_steps = max(1, int(dist / step_m))
        for s in range(1, n_steps + 1):
            t = s / n_steps
            out.append((la0 + (la1 - la0) * t, lo0 + (lo1 - lo0) * t))
    return out


def _headend_desde_features(features: list[dict], ramas_set: set[str]) -> tuple[float, float] | None:
    """Origen típico del trazado: promedio del primer vértice de cada rama."""
    starts: list[tuple[float, float]] = []
    for feat in features:
        props = feat.get("properties") or {}
        rama = str(props.get("camino_rama") or "").strip()
        if not rama or rama not in ramas_set:
            continue
        geom = feat.get("geometry") or {}
        pts = _coords_latlon_from_geometry(geom)
        if pts:
            starts.append(pts[0])
    if not starts:
        return None
    return (sum(p[0] for p in starts) / len(starts), sum(p[1] for p in starts) / len(starts))


def _centro_celda(cell_points: dict[tuple[int, int], list[tuple[float, float]]], ck: tuple[int, int]) -> tuple[float, float]:
    pts = cell_points.get(ck) or []
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _longitud_polyline_m(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        total += _haversine_m(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    return total


_MAX_TRONCAL_PUNTOS_MAPA = 150


def _subsample_polyline(points: list[tuple[float, float]], max_pts: int) -> list[tuple[float, float]]:
    if len(points) <= max_pts:
        return list(points)
    if max_pts < 2:
        return [points[0], points[-1]]
    step = max(1, (len(points) - 1) // (max_pts - 1))
    out: list[tuple[float, float]] = [points[0]]
    for i in range(step, len(points) - 1, step):
        out.append(points[i])
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def _troncal_spine_desde_rama_representativa(
    features: list[dict],
    ramas_set: set[str],
    peak_cells: set[tuple[int, int]],
) -> list[tuple[float, float]]:
    """Troncal compartido ordenado sobre una rama (evita zigzag al unir celdas 2D)."""
    rep = sorted(ramas_set, key=natural_sort_key_str)[0]
    for feat in features:
        props = feat.get("properties") or {}
        if str(props.get("camino_rama") or "").strip() != rep:
            continue
        geom = feat.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            continue
        pts = _interpolate_line_latlon(_coords_latlon_from_geometry(geom))
        spine: list[tuple[float, float]] = []
        for la, lo in pts:
            if _celda_troncal(la, lo) not in peak_cells:
                continue
            if spine and abs(spine[-1][0] - la) < 1e-9 and abs(spine[-1][1] - lo) < 1e-9:
                continue
            spine.append((la, lo))
        if len(spine) >= 2:
            return _subsample_polyline(spine, _MAX_TRONCAL_PUNTOS_MAPA)
    return []


def _recolectar_celdas_troncal(
    features: list[dict], ramas_set: set[str]
) -> tuple[dict[tuple[int, int], set[str]], dict[tuple[int, int], list[tuple[float, float]]]]:
    cells: dict[tuple[int, int], set[str]] = defaultdict(set)
    cell_points: dict[tuple[int, int], list[tuple[float, float]]] = defaultdict(list)
    for feat in features:
        props = feat.get("properties") or {}
        rama = str(props.get("camino_rama") or "").strip()
        if not rama or rama not in ramas_set:
            continue
        geom = feat.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            continue
        pts = _interpolate_line_latlon(_coords_latlon_from_geometry(geom))
        if len(pts) < 2:
            continue
        for la, lo in pts:
            ck = _celda_troncal(la, lo)
            cells[ck].add(rama)
            cell_points[ck].append((la, lo))
    return cells, cell_points


def _analisis_corte_masivo_gis(gis: dict, ramas: list[str]) -> tuple[list[dict], dict]:
    """
    Fase A: último tramo con todas las ramas (punto de reparto) + polyline del troncal.
    Devuelve (zonas_corte_probable con un foco, troncal_compartido).
    """
    empty_troncal: dict = {"ok": False}
    if not gis.get("ok"):
        return [], empty_troncal
    features = (gis.get("geojson") or {}).get("features") or []
    if not features:
        return [], empty_troncal

    ramas_set = {str(r).strip() for r in ramas if r and str(r).strip()}
    total = len(ramas_set)
    if total < 2:
        return [], empty_troncal

    cells, cell_points = _recolectar_celdas_troncal(features, ramas_set)
    if not cells:
        return [], empty_troncal

    ranked = sorted(cells.items(), key=lambda item: len(item[1]), reverse=True)
    peak = len(ranked[0][1])
    if peak < 2:
        return [], empty_troncal

    headend = _headend_desde_features(features, ramas_set)
    if not headend:
        return [], empty_troncal

    peak_cells: list[dict] = []
    for ck, rama_subset in cells.items():
        if len(rama_subset) < peak:
            continue
        la, lo = _centro_celda(cell_points, ck)
        peak_cells.append(
            {
                "cell": ck,
                "lat": la,
                "lon": lo,
                "rama_count": len(rama_subset),
                "ramas": sorted(rama_subset, key=natural_sort_key_str),
                "dist_m": _haversine_m(headend[0], headend[1], la, lo),
            }
        )
    if not peak_cells:
        return [], empty_troncal

    peak_cells.sort(key=lambda z: z["dist_m"])
    origen = peak_cells[0]
    bifurcacion = peak_cells[-1]
    peak_cell_keys = {z["cell"] for z in peak_cells}
    troncal_pts = _troncal_spine_desde_rama_representativa(features, ramas_set, peak_cell_keys)
    if len(troncal_pts) < 2:
        troncal_pts = [
            (float(origen["lat"]), float(origen["lon"])),
            (float(bifurcacion["lat"]), float(bifurcacion["lon"])),
        ]
    length_m = _longitud_polyline_m(troncal_pts)
    origen = {**origen, "lat": troncal_pts[0][0], "lon": troncal_pts[0][1]}
    bifurcacion = {**bifurcacion, "lat": troncal_pts[-1][0], "lon": troncal_pts[-1][1]}

    cnt = int(bifurcacion["rama_count"])
    pct = int(round(100 * cnt / total)) if total else 0
    if pct >= 65 or cnt >= max(12, int(total * 0.45)):
        prioridad = "critica"
        score = 95
    elif pct >= 35 or cnt >= max(6, int(total * 0.2)):
        prioridad = "alta"
        score = 78
    else:
        prioridad = "media"
        score = 58

    ramas_list = list(bifurcacion["ramas"])
    ramas_short = ramas_list[:10]
    extra = max(0, len(ramas_list) - len(ramas_short))
    motivo_extra = f" (+{extra} ramas más)" if extra else ""
    length_txt = f" Troncal compartido ≈ {int(round(length_m))} m." if length_m > 5 else ""

    zona = {
        "rank": 1,
        "tipo": "reparto",
        "lat": round(float(bifurcacion["lat"]), 6),
        "lon": round(float(bifurcacion["lon"]), 6),
        "rama_count": cnt,
        "rama_total": total,
        "rama_pct": pct,
        "ramas": ramas_short,
        "ramas_extra": extra,
        "prioridad": prioridad,
        "score": score,
        "radius_m": min(120, max(75, int(70 + peak * 0.5))),
        "troncal_length_m": int(round(length_m)),
        "motivo": (
            f"Punto de reparto: último tramo con {cnt}/{total} ramas ({pct}%) antes de "
            f"separarse en el trazado ci_op — foco probable de corte de troncal.{length_txt}"
            f"{motivo_extra}"
        ),
    }

    troncal = {
        "ok": True,
        "length_m": int(round(length_m)),
        "points": [{"lat": round(la, 6), "lon": round(lo, 6)} for la, lo in troncal_pts],
        "origen": {"lat": round(float(origen["lat"]), 6), "lon": round(float(origen["lon"]), 6)},
        "bifurcacion": {
            "lat": round(float(bifurcacion["lat"]), 6),
            "lon": round(float(bifurcacion["lon"]), 6),
        },
    }
    return [zona], troncal


def _zonas_corte_probable_desde_gis(gis: dict, ramas: list[str]) -> list[dict]:
    """Compat tests: solo la lista de zonas (un foco de reparto)."""
    zonas, _troncal = _analisis_corte_masivo_gis(gis, ramas)
    return zonas


_CI_OP_RESUMEN_KEYS = (
    "nombre_co_atc",
    "nombre_co_claro",
    "nombre_op",
    "cabecera",
    "sitio",
    "region",
    "longitud",
    "tipo",
)

_CI_OP_NOMBRE_KEYS = ("nombre_co_atc", "nombre_co_claro", "nombre_op")
_CI_OP_ATTRS_SKIP_UI = frozenset({"cabecera", "camino_rama"})


def _norm_ci_op_valor(val: Any) -> str:
    return str(val or "").strip().upper()


def _atributos_ci_op_para_ui(attrs: dict[str, str], rama: str) -> dict[str, str]:
    """Quita atributos ya visibles en cabecera o nomenclaturas redundantes."""
    if not attrs:
        return {}
    rama_n = _norm_ci_op_valor(rama)
    nombre_vals = {
        _norm_ci_op_valor(attrs[k]) for k in _CI_OP_NOMBRE_KEYS if attrs.get(k)
    }
    hide_nombres = len(nombre_vals) <= 1 and (not nombre_vals or nombre_vals == {rama_n})

    out: dict[str, str] = {}
    seen_nombre_vals: set[str] = set()
    order = list(_CI_OP_RESUMEN_KEYS) + ["camino_rama"]
    for key in order:
        if key not in attrs or key in _CI_OP_ATTRS_SKIP_UI:
            continue
        if key in _CI_OP_NOMBRE_KEYS:
            if hide_nombres:
                continue
            val_n = _norm_ci_op_valor(attrs[key])
            if val_n == rama_n or val_n in seen_nombre_vals:
                continue
            seen_nombre_vals.add(val_n)
        out[key] = attrs[key]
    for key, val in attrs.items():
        if key in out or key in _CI_OP_ATTRS_SKIP_UI or key in _CI_OP_NOMBRE_KEYS:
            continue
        out[key] = val
    return out


def _closest_point_on_polyline(
    points: list[tuple[float, float]], lat: float, lon: float
) -> tuple[float, float]:
    """Punto más cercano sobre una polilínea (lat, lon)."""
    if not points:
        return (lat, lon)
    best = points[0]
    best_d = float("inf")
    for i in range(len(points) - 1):
        la0, lo0 = points[i]
        la1, lo1 = points[i + 1]
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            pla = la0 + (la1 - la0) * t
            plo = lo0 + (lo1 - lo0) * t
            d = _haversine_m(lat, lon, pla, plo)
            if d < best_d:
                best_d = d
                best = (pla, plo)
    return best


def _puntos_trazado_desde_gis(gis: dict) -> list[tuple[float, float]]:
    if not gis.get("ok"):
        return []
    features = (gis.get("geojson") or {}).get("features") or []
    pts: list[tuple[float, float]] = []
    for feat in features:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry") or {}
        if geom.get("type") not in ("LineString", "MultiLineString"):
            continue
        for la, lo in _coords_latlon_from_geometry(geom):
            if pts and abs(pts[-1][0] - la) < 1e-9 and abs(pts[-1][1] - lo) < 1e-9:
                continue
            pts.append((la, lo))
    return pts


def _extremos_trazado_gis(
    gis: dict,
    focal_lat: float | None = None,
    focal_lon: float | None = None,
) -> dict[str, Any] | None:
    pts = _puntos_trazado_desde_gis(gis)
    if len(pts) < 2:
        if len(pts) == 1:
            la, lo = pts[0]
            return {
                "cabecera": {"lat": round(la, 6), "lon": round(lo, 6)},
                "hacia_cto": {"lat": round(la, 6), "lon": round(lo, 6)},
            }
        return None

    cab_la, cab_lo = pts[0]
    hacia_la, hacia_lo = pts[-1]

    if focal_lat is not None and focal_lon is not None:
        try:
            fla, flo = float(focal_lat), float(focal_lon)
        except (TypeError, ValueError):
            fla, flo = None, None
        if fla is not None:
            on_line = _closest_point_on_polyline(pts, fla, flo)
            hacia_la, hacia_lo = on_line
            d0 = _haversine_m(fla, flo, pts[0][0], pts[0][1])
            d1 = _haversine_m(fla, flo, pts[-1][0], pts[-1][1])
            if d0 > d1:
                cab_la, cab_lo = pts[0][0], pts[0][1]
            else:
                cab_la, cab_lo = pts[-1][0], pts[-1][1]

    return {
        "cabecera": {"lat": round(cab_la, 6), "lon": round(cab_lo, 6)},
        "hacia_cto": {"lat": round(hacia_la, 6), "lon": round(hacia_lo, 6)},
    }


def _resumen_ci_op_desde_gis(gis: dict, rama: str) -> dict[str, Any]:
    out: dict[str, Any] = {"rama": rama, "feature_count": 0, "atributos": {}}
    if not gis.get("ok"):
        return out
    features = (gis.get("geojson") or {}).get("features") or []
    trazados = [
        f
        for f in features
        if isinstance(f, dict)
        and (f.get("geometry") or {}).get("type") in ("LineString", "MultiLineString")
    ]
    out["feature_count"] = len(trazados)
    for feat in trazados:
        props = feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
        for key in _CI_OP_RESUMEN_KEYS:
            val = props.get(key)
            if val is not None and str(val).strip() and key not in out["atributos"]:
                out["atributos"][key] = str(val).strip()
        if props.get("camino_rama"):
            out["atributos"]["camino_rama"] = str(props["camino_rama"]).strip()
    out["atributos"] = _atributos_ci_op_para_ui(out["atributos"], rama)
    return out


def _planta_interna_para_consulta(
    ramas: list[str],
    gis: dict,
    *,
    focal_cto: str | None = None,
    fusion_destacar: str | None = None,
) -> dict[str, Any]:
    """Capas QGIS planta interna: ci_op + FOSC ordenadas cabecera→CTO."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    empty: dict[str, Any] = {"ok": False, "fosc": {"ok": False, "markers": []}}
    if not ramas or not gis.get("ok"):
        return empty

    rama_pri = ramas[0]
    focal_lat: float | None = None
    focal_lon: float | None = None
    if focal_cto:
        try:
            coords = consultar_cto_coordenadas_desde_sfat(focal_cto)
            if coords:
                focal_lat = coords.get("lat")
                focal_lon = coords.get("lon")
        except Exception:
            logger.debug("coords sfat CTO %s omitidas", focal_cto, exc_info=True)

    if focal_lat is None and focal_cto:
        try:
            batch = consultar_cto_coordenadas_batch([focal_cto])
            c0 = batch.get(focal_cto) if batch else None
            if c0:
                focal_lat, focal_lon = c0.get("lat"), c0.get("lon")
        except Exception:
            logger.debug("coords batch CTO %s omitidas", focal_cto, exc_info=True)

    extremos = _extremos_trazado_gis(gis, focal_lat, focal_lon)
    ci_op = _resumen_ci_op_desde_gis(gis, rama_pri)
    cab = cabecera_para_fosc(rama_pri, gis)

    try:
        fosc = consultar_fosc_ordenadas_en_rama(
            ramas,
            cabecera=cab,
            gis=gis,
            focal_lat=focal_lat,
            focal_lon=focal_lon,
        )
        if fosc.get("ok") and not (fosc.get("markers") or []) and cab:
            fosc_alt = consultar_fosc_ordenadas_en_rama(
                ramas,
                gis=gis,
                focal_lat=focal_lat,
                focal_lon=focal_lon,
                filtrar_cabecera=False,
                max_dist_traz_m=(fosc.get("max_dist_traz_m") or 100) * 1.5,
            )
            if fosc_alt.get("ok") and fosc_alt.get("markers"):
                fosc = fosc_alt
                fosc["nota"] = (
                    f"Sin FOSC con cabecera «{cab}»; se listan botellas a ≤"
                    f"{int(fosc_alt.get('max_dist_traz_m') or 0)} m del trazado (sin filtro cabecera)."
                )
        if fosc.get("ok") and not (fosc.get("markers") or []) and cab:
            fosc.setdefault(
                "hint",
                f"No hay botellas FOSC a ≤{int(fosc.get('max_dist_traz_m') or 100)} m del trazado "
                f"(cabecera «{cab}»). Revisá en QGIS o ampliá CAMINO_GIS_FOSC_MAX_DIST_TRAZ_M.",
            )
    except Exception:
        logger.exception("FOSC ordenadas falló para %s", ramas)
        fosc = {"ok": False, "markers": [], "error": "Error consultando botellas."}

    feeder: dict[str, Any] = {"ok": False}
    try:
        feeder = consultar_feeder_distribucion_planta_interna(
            ramas,
            cabecera=cab,
            focal_lat=focal_lat,
            focal_lon=focal_lon,
        )
    except Exception:
        logger.exception("Feeder distribution falló para %s", ramas)
        feeder = {"ok": False, "error": "Error consultando ci_feeder_distribution."}

    if feeder.get("ok") and fosc.get("ok") and feeder.get("fosc_144"):
        f144 = feeder["fosc_144"]
        fid_cm = (f144.get("id_cm") or "").strip()
        fid_bot = f144.get("id_botella")
        for m in fosc.get("markers") or []:
            if fid_cm and (m.get("id_cm") or "").strip() == fid_cm:
                m["feeder_144"] = True
            elif fid_bot is not None and m.get("id_botella") == fid_bot:
                m["feeder_144"] = True

    fusiones: dict[str, Any] = {"ok": False, "markers": []}
    try:
        fusiones = consultar_fusiones_verificacion_rama(
            ramas, fusion_destacar=fusion_destacar
        )
    except Exception:
        logger.exception("Fusiones verificación falló para %s", ramas)
        fusiones = {"ok": False, "markers": [], "error": "Error consultando report_fusiones."}

    if fusiones.get("ok") and feeder.get("fosc_144"):
        fosc_cm = (feeder["fosc_144"].get("id_cm") or "").strip()
        for fm in fusiones.get("markers") or []:
            if fosc_cm and (fm.get("fosc_id_cm") or "").strip() == fosc_cm:
                fm["feeder_144"] = True

    return {
        "ok": True,
        "rama": rama_pri,
        "ramas": ramas,
        "cabecera": cab or cabecera_desde_rama(rama_pri),
        "focal_cto": (focal_cto or "").strip() or None,
        "extremos": extremos,
        "ci_op": ci_op,
        "feeder": feeder,
        "fosc": fosc,
        "fusiones": fusiones,
    }


def _enriquecer_masivo_con_infra_fosc(
    ramas: list[str],
    gis: dict,
    zonas: list[dict],
) -> dict:
    """Botellas FOSC cerca del trazado + snap del punto de corte."""
    empty: dict = {"fosc": {"ok": False, "markers": []}, "snap_corte": None}
    if not ramas or not gis.get("ok"):
        return empty
    cabecera = cabecera_para_fosc(ramas[0], gis)
    if not cabecera:
        return empty
    try:
        fosc = consultar_fosc_cerca_trazado_ramas(ramas, cabecera)
    except Exception:
        logger.exception("FOSC cerca trazado falló para %s", ramas)
        fosc = {"ok": False, "markers": [], "error": "Error consultando botellas."}

    snap = None
    if zonas:
        z0 = zonas[0]
        try:
            la, lo = float(z0.get("lat")), float(z0.get("lon"))
            snap = snap_corte_a_fosc(ramas, la, lo, cabecera)
        except (TypeError, ValueError):
            snap = {"ok": False, "error": "Zona de corte sin coordenadas."}
        except Exception:
            logger.exception("Snap FOSC falló para %s", ramas)
            snap = {"ok": False, "error": "Error ajustando corte a botella."}

        if snap and snap.get("ok"):
            z0["lat_heuristica"] = z0.get("lat")
            z0["lon_heuristica"] = z0.get("lon")
            z0["lat"] = snap.get("lat")
            z0["lon"] = snap.get("lon")
            z0["snap_fosc"] = {
                k: snap.get(k)
                for k in (
                    "id_botella",
                    "id_cm",
                    "tipo",
                    "direccion",
                    "dist_traz_m",
                    "dist_snap_m",
                    "dist_corte_m",
                    "maps_url",
                    "metodo",
                )
                if snap.get(k) is not None
            }
            extra = []
            if snap.get("id_cm"):
                extra.append(f"Botella {snap['id_cm']}")
            if snap.get("direccion"):
                extra.append(str(snap["direccion"]))
            if snap.get("dist_snap_m") is not None:
                extra.append(f"≈ {snap['dist_snap_m']} m sobre troncal")
            if extra:
                z0["motivo"] = (z0.get("motivo") or "").rstrip(".") + ". Snap FOSC: " + "; ".join(extra) + "."

            snap_id = snap.get("id_botella")
            if snap_id is not None and fosc.get("markers"):
                for m in fosc["markers"]:
                    if m.get("id_botella") == snap_id:
                        m["snap_target"] = True

    return {"fosc": fosc, "snap_corte": snap}


def dashboard_camino_optico_ramas_masivo(raw_values) -> dict:
    """Consulta masiva de ramas RATC: mapa unificado + inventario + CTO compartidas."""
    ramas, invalid = _parse_rama_masivo_tokens(raw_values)
    if not ramas:
        if invalid:
            return {
                "error": "Ningún token válido (esperado código RATC, p. ej. ES01-RATC-0-000384).",
                "invalid": invalid,
            }
        return {"error": "Ingresá al menos una rama RATC (…-RATC-…)."}
    if len(ramas) > MAX_RAMAS_CAMINO_AGREGADO:
        return {
            "error": (
                f"Demasiadas ramas ({len(ramas)}) para un solo mapa "
                f"(máx. {MAX_RAMAS_CAMINO_AGREGADO}). Acotá la lista."
            ),
            "resumen": {"rama_count": len(ramas)},
        }

    ramas_data = [_rama_resumen_ligero(r) for r in ramas]
    vacias = [rd["rama"] for rd in ramas_data if rd.get("sin_inventario")]
    ctos_union = _build_ctos_union(ramas_data)
    rama_por_cto = {c["cto"]: c["ramas"] for c in ctos_union}
    rama_colors = _build_rama_colors(ramas)

    cto_markers_by_rama = _cto_markers_por_rama(ramas)
    for m in cto_markers_by_rama:
        r = m.get("rama") or ""
        pack = rama_colors.get(r) or {}
        m["color_index"] = pack.get("index", 0)
        m["color"] = pack.get("point") or "#f97316"

    cto_markers = _cto_markers_para_ramas(ramas, "")
    for m in cto_markers:
        cto_key = m.get("cto") or ""
        ramas_cto = rama_por_cto.get(cto_key, [])
        m["ramas"] = ramas_cto
        m["shared"] = len(ramas_cto) > 1

    sugerencias_medicion = _sugerir_ctos_medicion(ramas_data, ctos_union)

    try:
        gis = _gis_merge_para_ramas(ramas)
    except Exception:
        logger.exception("GIS masivo ramas falló para %s", ramas)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    zonas_corte_probable, troncal_compartido = _analisis_corte_masivo_gis(gis, ramas)
    infra_fosc = _enriquecer_masivo_con_infra_fosc(ramas, gis, zonas_corte_probable)

    ont_total = sum(int((rd.get("resumen") or {}).get("ont_count") or 0) for rd in ramas_data)
    cto_shared = sum(1 for c in ctos_union if c.get("shared"))

    return {
        "tipo": "ramas_masivo",
        "ramas": ramas_data,
        "invalid": invalid,
        "vacias": vacias,
        "resumen": {
            "rama_count": len(ramas),
            "cto_unique": len(ctos_union),
            "cto_shared": cto_shared,
            "ont_count": ont_total,
        },
        "ctos_union": ctos_union,
        "cto_markers": cto_markers,
        "cto_markers_by_rama": cto_markers_by_rama,
        "rama_colors": rama_colors,
        "sugerencias_medicion": sugerencias_medicion,
        "zonas_corte_probable": zonas_corte_probable,
        "troncal_compartido": troncal_compartido,
        "infra_fosc": infra_fosc,
        "gis": gis,
    }
