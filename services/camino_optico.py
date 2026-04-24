"""Dashboard prueba: camino óptico (FAT + cm_report_isp)."""
from urllib.parse import quote_plus

from db import db_cursor

from .domain import nombre_operador
from .inventory import consultar_cto_coordenadas


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
    """Una fila reciente de cm_report_isp por sistema óptico (rama)."""
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


def dashboard_camino_optico_cto(cto):
    """ONT de la CTO + camino hacia sitio (FAT + report ISP por rama)."""
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
            WHERE f.location_description = %s AND f.status = 'IN SERVICE'
            ORDER BY f.access_id
            """,
            (cto,),
        )
        rows = cur.fetchall()
        colnames = [d[0] for d in cur.description]
        if not rows:
            return {"error": "Sin ONT en servicio para esa CTO", "cto": cto}

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
    }


def dashboard_camino_optico_rama(rama):
    """Conteo CTO / ONT por rama + listado de CTOs + tramo ISP."""
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

    return {
        "tipo": "rama",
        "rama": rama,
        "resumen": {
            "cto_count": int(cto_count or 0),
            "ont_count": int(ont_count or 0),
        },
        "ctos": ctos,
        "camino_isp": isp,
    }


def dashboard_camino_optico_access_id(access_id):
    """Una ONT: detalle FAT + tramo ISP."""
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

    cto_maps_url = _cto_maps_url_for_fatc_location(d.get("location_description") or "")

    return {
        "tipo": "access_id",
        "detalle": d,
        "cto_maps_url": cto_maps_url,
    }
