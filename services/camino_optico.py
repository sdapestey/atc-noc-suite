"""Dashboard prueba: camino óptico (FAT + cm_report_isp)."""
import logging
import re
from urllib.parse import quote_plus

from db import db_cursor

from .camino_gis import consultar_ci_op_por_rama, consultar_cto_coordenadas_desde_sfat
from .dashboard_olt import dashboard_olts
from .domain import (
    nombre_operador,
    lt_desde_object_name,
    natural_sort_key_str,
    principal_y_sitio_desde_olt,
    region_desde_rama,
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
)
from .inventory import consultar_cto_coordenadas, consultar_cto_direccion_postal

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
    if "RATC" in u:
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
    for step in pasos_equipo or []:
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
    }


def dashboard_camino_optico_rama(rama):
    """Consulta vista agregada por rama para Camino Óptico.

    Args:
        rama: Identificador RATC.

    Returns:
        Dict con conteos (CTO/ONT), lista de CTOs y tramo ISP.
    """
    rama = (rama or "").strip()
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
    }


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
    }
