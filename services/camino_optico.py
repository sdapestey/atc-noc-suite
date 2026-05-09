"""Dashboard prueba: camino óptico (FAT + cm_report_isp)."""
import logging
import re
from urllib.parse import quote_plus

from db import db_cursor

from .camino_gis import consultar_ci_op_por_rama, consultar_cto_coordenadas_desde_sfat
from .domain import nombre_operador
from .inventory import consultar_cto_coordenadas

logger = logging.getLogger(__name__)


def infer_camino_consulta_tipo(valor: str) -> str | None:
    """Deduce si el valor es CTO (FATC), rama (RATC) o Access ID (solo dígitos).

    Returns:
        ``cto``, ``rama``, ``access_id`` o ``None`` si no aplica.
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
    return None


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


def _cto_markers_para_ramas(cur, ramas: list[str], focal_cto: str) -> list[dict]:
    """Marcadores Leaflet: CTOs en servicio en las ramas dadas; marca la CTO buscada."""
    ramas = [r for r in ramas if r]
    focal_u = (focal_cto or "").strip().upper()
    if not ramas:
        return []
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
    markers: list[dict] = []
    for row in cur.fetchall():
        cto_id = row[0]
        if not cto_id:
            continue
        coords = consultar_cto_coordenadas(cto_id)
        source = "bajada_inventario"
        if not coords:
            coords = consultar_cto_coordenadas_desde_sfat(cto_id)
            source = "cm_sfat"
        if not coords:
            continue
        markers.append(
            {
                "cto": cto_id,
                "lat": coords["lat"],
                "lon": coords["lon"],
                "onts": int(row[1] or 0),
                "source": source,
                "focal": (str(cto_id).strip().upper() == focal_u),
            }
        )
    return markers


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
                o.invocator_system
            FROM cm.inventory_fat_occupation f
            LEFT JOIN altiplano.serial s ON s.access_id = f.access_id
            LEFT JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
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

        cto_markers = _cto_markers_para_ramas(cur, path_atcs, cto)

    try:
        gis = _gis_merge_para_ramas(path_atcs)
    except Exception:
        logger.exception("GIS CTO (ramas %s) falló", path_atcs)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    cto_maps_url = _cto_maps_url_for_fatc_location(cto)

    return {
        "tipo": "cto",
        "cto": cto,
        "cto_maps_url": cto_maps_url,
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

    cto_markers = []
    for c in ctos:
        coords = consultar_cto_coordenadas(c["cto"])
        source = "bajada_inventario"
        if not coords:
            coords = consultar_cto_coordenadas_desde_sfat(c["cto"])
            source = "cm_sfat"
        if coords:
            cto_markers.append(
                {
                    "cto": c["cto"],
                    "lat": coords["lat"],
                    "lon": coords["lon"],
                    "onts": c["onts"],
                    "source": source,
                }
            )

    try:
        gis = consultar_ci_op_por_rama(rama)
    except Exception:
        logger.exception("GIS rama falló para %s", rama)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    return {
        "tipo": "rama",
        "rama": rama,
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
                o.invocator_system
            FROM cm.inventory_fat_occupation f
            LEFT JOIN altiplano.serial s ON s.access_id = f.access_id
            LEFT JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
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
        cto_markers = _cto_markers_para_ramas(
            cur,
            ramas,
            d.get("location_description") or "",
        )

    try:
        gis = _gis_merge_para_ramas(ramas)
    except Exception:
        logger.exception("GIS Access ID (rama %s) falló", ramas)
        gis = {"ok": False, "error": "Error interno consultando geometría (ci_op)."}

    cto_maps_url = _cto_maps_url_for_fatc_location(d.get("location_description") or "")

    return {
        "tipo": "access_id",
        "detalle": d,
        "cto_maps_url": cto_maps_url,
        "cto_markers": cto_markers,
        "gis": gis,
    }
