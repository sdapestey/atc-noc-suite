"""Consultas GIS PostGIS: trazado del camino óptico por rama en `cm` (tabla tipo `ci_op`).

Variables de entorno: `CAMINO_GIS_CM_SCHEMA`, `CAMINO_GIS_CI_OP_TABLE`,
`CAMINO_GIS_SFAT_TABLE` (puntos FAT / CTO en `cm`).
"""
from __future__ import annotations

import json
import logging
import os
import re
from decimal import Decimal
from typing import Any
from urllib.parse import quote_plus

from db import db_cursor

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _env_schema() -> str:
    s = (os.environ.get("CAMINO_GIS_CM_SCHEMA") or "cm").strip()
    return s if s else "cm"


def _env_ci_op_table() -> str:
    t = (os.environ.get("CAMINO_GIS_CI_OP_TABLE") or "ci_op").strip()
    return t if t else "ci_op"


def _env_sfat_table() -> str:
    t = (os.environ.get("CAMINO_GIS_SFAT_TABLE") or "ci_sfat_mfat_bfat").strip()
    return t if t else "ci_sfat_mfat_bfat"


def _env_fosc_table() -> str:
    t = (os.environ.get("CAMINO_GIS_FOSC_TABLE") or "ci_fosc").strip()
    return t if t else "ci_fosc"


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_fosc_max_dist_traz_m() -> float:
    """Tolerancia máx. (m) para considerar una FOSC «sobre» el trazado ci_op (no «cerca»)."""
    return _env_float("CAMINO_GIS_FOSC_MAX_DIST_TRAZ_M", 6.0)


def _env_fosc_max_snap_m() -> float:
    return _env_float("CAMINO_GIS_FOSC_MAX_SNAP_M", 200.0)


def _env_fosc_map_limit() -> int:
    try:
        return max(10, min(300, int(os.environ.get("CAMINO_GIS_FOSC_MAP_LIMIT") or "150")))
    except ValueError:
        return 150


def _env_feeder_dist_table() -> str:
    t = (os.environ.get("CAMINO_GIS_FEEDER_DIST_TABLE") or "ci_feeder_distribution").strip()
    return t if t else "ci_feeder_distribution"


def _env_feeder_max_dist_traz_m() -> float:
    return _env_float("CAMINO_GIS_FEEDER_MAX_DIST_TRAZ_M", 100.0)


def _env_feeder_fosc_corte_m() -> float:
    return _env_float("CAMINO_GIS_FEEDER_FOSC_CORTE_M", 200.0)


def _env_fusiones_table() -> str:
    t = (os.environ.get("CAMINO_GIS_FUSIONES_TABLE") or "report_fusiones").strip()
    return t if t else "report_fusiones"


def _env_fusiones_limit() -> int:
    try:
        return max(5, min(80, int(os.environ.get("CAMINO_GIS_FUSIONES_LIMIT") or "30")))
    except ValueError:
        return 30


# Código planta interna (p. ej. SF01-R1301-010 en report_fusiones / PDF de fusión).
_FUSION_PLANTA_RE = re.compile(r"^[A-Z0-9]{2,12}-R\d+-\d{3}$", re.I)


def _parse_geojson_cell(raw: object) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def cabecera_desde_rama(rama: str) -> str:
    """Sitio/cabecera (p. ej. TG02) desde código de rama (RATC, NATC, etc.)."""
    rama = (rama or "").strip()
    m = re.match(r"^([^-]+)-(?:RATC|NATC|FATC|OP)\b", rama, re.I)
    if m:
        return m.group(1).upper()
    m2 = re.match(r"^([A-Za-z0-9]+)", rama)
    return m2.group(1).upper() if m2 else ""


def _cabecera_token_desde_texto(raw: object) -> str:
    """Primer token de cabecera/sitio (p. ej. ``ES01`` desde ``ES01 - BELEN``)."""
    s = (str(raw or "")).strip()
    if not s:
        return ""
    head = re.split(r"[\s\-–/]+", s, maxsplit=1)[0].strip().upper()
    if head and re.match(r"^[A-Z0-9]{2,16}$", head):
        return head
    m = re.match(r"^([A-Z0-9]{2,12})", s.upper())
    return m.group(1) if m else ""


def cabecera_para_fosc(rama: str, gis: dict | None = None) -> str:
    """Cabecera para filtrar ``ci_fosc``: rama, atributos ci_op o prefijo del código."""
    c = cabecera_desde_rama(rama)
    if c:
        return c
    if gis and gis.get("ok"):
        for feat in (gis.get("geojson") or {}).get("features") or []:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties") if isinstance(feat.get("properties"), dict) else {}
            for key in ("cabecera", "sitio", "nombre_cabecera", "codigo_cabecera"):
                tok = _cabecera_token_desde_texto(props.get(key))
                if tok:
                    return tok
    return cabecera_desde_rama(rama)


def _dedupe_fosc_markers(markers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Una entrada por ``id_cm`` (o ``id_botella``), conservando el orden cabecera → CTO."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in markers:
        id_cm = (m.get("id_cm") or "").strip().upper()
        id_bot = m.get("id_botella")
        key = id_cm if id_cm else (f"#{id_bot}" if id_bot is not None else "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(dict(m))
    removed = max(0, len(markers) - len(out))
    for i, m in enumerate(out, 1):
        m["orden"] = i
    return out, removed


_FOSC_CM_ID_RE = re.compile(r"^.+-FOSC-.+$", re.I)


def es_id_fosc_cm(valor: str) -> bool:
    """True si el token parece id de botella ConnectMaster (``…-FOSC-…``)."""
    return bool(_FOSC_CM_ID_RE.match((valor or "").strip()))


def _lookup_ci_fosc_meta(cur, schema: str, fosc_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not fosc_id or not _table_exists(cur, schema, "ci_fosc"):
        return out
    cols = set(_list_data_columns(cur, schema, "ci_fosc"))
    want = [
        c
        for c in ("direccion", "nombre_atc", "partido_despliegue", "cabecera", "id_botella")
        if c in cols
    ]
    if "id_cm" not in cols or not want:
        return out
    sel = ", ".join(_quote_ident(c) for c in want)
    cur.execute(
        f"""
        SELECT {sel}
        FROM {_quote_ident(schema)}.{_quote_ident("ci_fosc")}
        WHERE id_cm = %s LIMIT 1
        """,
        (fosc_id,),
    )
    row = cur.fetchone()
    if not row:
        return out
    for i, c in enumerate(want):
        out[c] = str(row[i]).strip() if row[i] is not None else ""
    return out


def _componente_cm_desde_filas(fullname_a: object, fullname_b: object) -> str:
    """Componente visible en CM (prefiere ``component_fullname_a`` en feeder/FEL)."""
    for raw in (fullname_a, fullname_b):
        head = (str(raw or "")).split(">")[0].strip()
        if not head:
            continue
        u = head.upper()
        if any(t in u for t in ("FEL", "DSL", "CATC", "FOSC")):
            return head
    for raw in (fullname_a, fullname_b):
        head = (str(raw or "")).split(">")[0].strip()
        if head:
            return head
    return ""


_FATC3_ALIAS_RE = re.compile(r"^[A-Z]{2}[0-9]+-FATC-3-", re.I)


def _es_etiqueta_alias_cm(etiqueta: str) -> bool:
    return bool(_FATC3_ALIAS_RE.match((etiqueta or "").strip()))


def _alias_visible_cm(etiqueta: str, nombre_atc: str) -> str:
    """Alias como en CM: FATC-3 en etiqueta; fusión con/sin ``nombre_atc``."""
    etiq = (etiqueta or "").strip()
    nom = (nombre_atc or "").strip()
    if _es_etiqueta_alias_cm(etiq):
        return etiq
    if nom and nom.upper() != etiq.upper():
        return nom
    if es_codigo_fusion_planta(etiq):
        return "Sin alias"
    return nom or etiq or "Sin alias"


def consultar_fosc_camino_logico_rama(rama: str) -> dict[str, Any]:
    """Camino lógico de la rama en ``report_fusiones`` (botellas + fusiones), como ConnectMaster."""
    rama = (rama or "").strip()
    if not rama:
        return {"ok": False, "error": "Rama vacía.", "markers": []}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida.", "markers": []}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table}.",
                "markers": [],
            }
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT
                f.location_description,
                MIN(f.location_name) AS location_name,
                MIN(f.location_type) AS location_type,
                MIN(f.location_status) AS location_status,
                MIN(f.geo_y) AS lat,
                MIN(f.geo_x) AS lon,
                MIN(f.phgr_id) AS phgr_id,
                MIN(f.physical_path) AS physical_path,
                COUNT(*)::int AS filas,
                (array_agg(
                  COALESCE(
                    CASE WHEN split_part(f.component_fullname_a, '>', 1) ~* 'FEL|DSL'
                      THEN split_part(f.component_fullname_a, '>', 1) END,
                    CASE WHEN split_part(f.component_fullname_b, '>', 1) ~* 'FEL|DSL'
                      THEN split_part(f.component_fullname_b, '>', 1) END
                  )
                  ORDER BY
                    CASE WHEN f.description_b IS NOT NULL AND TRIM(f.description_b) <> '' THEN 0 ELSE 1 END,
                    CASE WHEN f.splice = 'EMPALME' THEN 0 WHEN f.splice = 'CONTINUIDAD' THEN 1 ELSE 2 END,
                    f.phgr_id NULLS LAST
                ))[1] AS componente,
                (array_agg(f.description_a
                  ORDER BY CASE WHEN f.component_fullname_a ILIKE '%%FEL%%' THEN 0 ELSE 1 END))[1]
                  AS cable_a,
                (array_agg(f.subcategory_a
                  ORDER BY CASE WHEN f.component_fullname_a ILIKE '%%FEL%%' THEN 0 ELSE 1 END))[1]
                  AS subcat_a,
                MIN(f.splice) AS splice,
                MIN(cf.id_botella) AS id_botella
            FROM {schema_q}.{table_q} f
            LEFT JOIN {_quote_ident(schema)}.{_quote_ident("ci_fosc")} cf
              ON cf.id_cm = f.location_name
            WHERE f.path_atc = %s
              AND f.location_description IS NOT NULL
              AND TRIM(f.location_description) <> ''
              AND (
                f.location_description ~ '^[A-Z]{{2}}[0-9]+-FATC-3-'
                OR f.location_description ~ '^[A-Za-z0-9]{{2,12}}-R[0-9]+-[0-9]{{3}}$'
              )
            GROUP BY f.location_description
            ORDER BY
              MIN(CASE
                WHEN f.component_fullname_a ILIKE '%%FEL1%%'
                  OR f.component_fullname_b ILIKE '%%FEL1%%' THEN 1
                WHEN f.component_fullname_a ILIKE '%%FEL2%%'
                  OR f.component_fullname_b ILIKE '%%FEL2%%' THEN 2
                WHEN f.component_fullname_a ILIKE '%%FEL3%%'
                  OR f.component_fullname_b ILIKE '%%FEL3%%' THEN 3
                WHEN f.component_fullname_b ILIKE '%%DSL%%' THEN 4
                ELSE 5
              END),
              MAX(NULLIF(
                regexp_replace(
                  split_part(split_part(COALESCE(f.component_fullname_a, ''), '>', 1), '-', 7),
                  '[^0-9]', '', 'g'
                ),
                ''
              )::int) DESC NULLS LAST,
              MIN(cf.id_botella) NULLS LAST,
              f.location_description
            """,
            (rama,),
        )
        rows = cur.fetchall()

    markers: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        etiqueta = (row[0] or "").strip()
        if not etiqueta:
            continue
        id_cm = (row[1] or "").strip()
        es_fusion = es_codigo_fusion_planta(etiqueta)
        lat = lon = None
        try:
            if row[4] is not None and row[5] is not None:
                lat = round(float(row[4]), 6)
                lon = round(float(row[5]), 6)
        except (TypeError, ValueError):
            lat = lon = None
        componente = (row[9] or "").strip() if row[9] else _componente_cm_desde_filas("", "")
        mk: dict[str, Any] = {
            "orden": i,
            "etiqueta": etiqueta,
            "id_cm": id_cm,
            "tipo": (row[2] or ("Fusión" if es_fusion else "FOSC")).strip(),
            "estado": (row[3] or "").strip(),
            "componente": componente,
            "cable": (row[10] or "").strip() if row[10] else "",
            "subcategory": (row[11] or "").strip() if row[11] else "",
            "splice": (row[12] or "").strip() if row[12] else "",
            "lat": lat,
            "lon": lon,
            "phgr_id": row[6],
            "physical_path": (row[7] or "").strip() if row[7] else "",
            "filas_reporte": int(row[8] or 0),
            "camino_logico": True,
            "es_fusion": es_fusion,
            "fusion_id": etiqueta if es_fusion else None,
            "fosc_id_cm": id_cm if es_id_fosc_cm(id_cm) else "",
            "fuera_trazado": True,
        }
        if lat is not None and lon is not None:
            mk["maps_url"] = f"https://www.google.com/maps?q={lat},{lon}"
        try:
            if row[13] is not None:
                mk["id_botella"] = int(row[13])
        except (TypeError, ValueError):
            pass
        markers.append(mk)

    if markers:
        with db_cursor() as cur:
            for mk in markers:
                fid = (mk.get("id_cm") or "").strip()
                if not fid:
                    continue
                meta = _lookup_ci_fosc_meta(cur, schema, fid)
                nom = (meta.get("nombre_atc") or "").strip()
                mk["alias"] = _alias_visible_cm(mk.get("etiqueta") or "", nom)
                if meta.get("direccion"):
                    mk["direccion"] = meta["direccion"]
                if nom and _es_etiqueta_alias_cm(mk.get("etiqueta") or ""):
                    mk["fosc_alias"] = nom
                elif nom and not es_codigo_fusion_planta(mk.get("etiqueta") or ""):
                    mk["fosc_alias"] = nom
                if not mk.get("id_botella") and meta.get("id_botella"):
                    try:
                        mk["id_botella"] = int(meta["id_botella"])
                    except (TypeError, ValueError):
                        pass

    return {
        "ok": True,
        "rama": rama,
        "markers": markers,
        "fuente": "report_fusiones",
        "cabecera_filtrada": True,
        "nota": (
            "Camino lógico ConnectMaster (report_fusiones): botellas FATC-3 y fusiones "
            "de verificación con componente y estado."
        ),
    }


def consultar_fosc_detalle_interno(fosc_id: str, *, rama: str | None = None) -> dict[str, Any]:
    """Árbol interno de la botella: feeder, FOSC y bandejas splice (como árbol CM)."""
    fosc_id = (fosc_id or "").strip()
    rama = (rama or "").strip() or None
    if not es_id_fosc_cm(fosc_id):
        return {"ok": False, "error": "Id de FOSC inválido."}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida."}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {"ok": False, "error": f"No existe {schema}.{table}."}
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT DISTINCT description_a, subcategory_a
            FROM {schema_q}.{table_q}
            WHERE location_name = %s
              AND description_a IS NOT NULL
              AND description_a <> ''
              AND (
                subcategory_a ILIKE '%%FEEDER%%'
                OR subcategory_a ILIKE '%%BACKHAUL%%'
                OR description_a ILIKE '%%CATC%%'
              )
            ORDER BY description_a
            """,
            (fosc_id,),
        )
        feeders = [
            {"label": (r[0] or "").strip(), "subcategory": (r[1] or "").strip()}
            for r in cur.fetchall()
            if (r[0] or "").strip()
        ]
        cur.execute(
            f"""
            SELECT DISTINCT component_name_a
            FROM {schema_q}.{table_q}
            WHERE location_name = %s
              AND component_name_a ILIKE '%%SPLICE TRAY%%'
            ORDER BY component_name_a
            """,
            (fosc_id,),
        )
        trays = []
        for (tray_name,) in cur.fetchall():
            tray = (tray_name or "").strip()
            if not tray:
                continue
            filas_rama = None
            if rama:
                cur.execute(
                    f"""
                    SELECT COUNT(*)::int
                    FROM {schema_q}.{table_q}
                    WHERE location_name = %s
                      AND component_name_a = %s
                      AND path_atc = %s
                    """,
                    (fosc_id, tray, rama),
                )
                filas_rama = int(cur.fetchone()[0] or 0)
            trays.append(
                {
                    "tray": tray,
                    "filas_circuito": filas_rama,
                }
            )
        meta = _lookup_ci_fosc_meta(cur, schema, fosc_id)
        cur.execute(
            f"""
            SELECT MAX(usedby), MAX(location_fullname), MAX(location_status), MAX(owner)
            FROM {schema_q}.{table_q}
            WHERE location_name = %s
            """,
            (fosc_id,),
        )
        h = cur.fetchone() or (None, None, None, None)

    return {
        "ok": True,
        "fosc_id": fosc_id,
        "rama": rama,
        "alias": meta.get("nombre_atc") or (h[0] or "").strip() or fosc_id,
        "location_fullname": (h[1] or "").strip(),
        "status": (h[2] or "").strip(),
        "owner": (h[3] or "").strip(),
        "direccion": meta.get("direccion") or "",
        "feeders": feeders,
        "trays": trays,
    }


def _normalize_fosc_direccion(val: Any) -> str:
    """Quita direcciones vacías o placeholders tipo 'None, None' de CM."""
    s = str(val or "").strip()
    if not s or s == "-":
        return ""
    parts = [p.strip() for p in s.split(",")]
    if parts and all(not p or p.lower() in ("none", "null") for p in parts):
        return ""
    return s


def _fosc_row_to_marker(row: tuple, colnames: list[str]) -> dict[str, Any]:
    rec = dict(zip(colnames, row))
    lat = rec.get("lat")
    lon = rec.get("lon")
    if lat is None or lon is None:
        return {}
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return {}
    dist_traz = rec.get("dist_traz_m")
    try:
        dist_traz_f = round(float(dist_traz), 1) if dist_traz is not None else None
    except (TypeError, ValueError):
        dist_traz_f = None
    direccion = _normalize_fosc_direccion(rec.get("direccion"))
    return {
        "id_botella": rec.get("id_botella"),
        "tipo": (rec.get("tipo") or "FOSC").strip(),
        "id_cm": (rec.get("id_cm") or "").strip(),
        "direccion": direccion,
        "lat": round(la, 6),
        "lon": round(lo, 6),
        "dist_traz_m": dist_traz_f,
    }


def consultar_fosc_cerca_trazado_ramas(
    ramas: list[str],
    cabecera: str | None = None,
    *,
    max_dist_traz_m: float | None = None,
    limit: int | None = None,
    filtrar_cabecera: bool = False,
) -> dict[str, Any]:
    """Botellas (FOSC) sobre el trazado ci_op de las ramas (≤ tolerancia de encastre en m)."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    if not ramas:
        return {"ok": False, "error": "Sin ramas.", "markers": []}
    cab = (cabecera or cabecera_desde_rama(ramas[0])).strip().upper()
    if filtrar_cabecera and not cab:
        return {"ok": False, "error": "No se pudo inferir cabecera.", "markers": []}

    schema = _env_schema()
    table = _env_fosc_table()
    max_dist = max_dist_traz_m if max_dist_traz_m is not None else _env_fosc_max_dist_traz_m()
    lim = limit if limit is not None else _env_fosc_map_limit()

    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla FOSC inválida.", "markers": []}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_FOSC_TABLE).",
                "markers": [],
            }
        geom_col = _geometry_column(cur, schema, table)
        if not geom_col:
            return {"ok": False, "error": "Sin geometría en capa FOSC.", "markers": []}

        cols = set(_list_data_columns(cur, schema, table))
        if "cabecera" not in cols:
            return {"ok": False, "error": "Capa FOSC sin columna cabecera.", "markers": []}

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        geom_q = _quote_ident(geom_col)
        op_col = None
        ci_op_table = _env_ci_op_table()
        ci_op_cols = set(_list_data_columns(cur, schema, ci_op_table))
        for c in ("nombre_co_atc", "nombre_co_claro", "nombre_op"):
            if c in ci_op_cols:
                op_col = c
                break
        if not op_col:
            return {"ok": False, "error": "ci_op sin columna de rama.", "markers": []}

        op_q = _quote_ident(op_col)
        ci_op_q = _quote_ident(ci_op_table)
        cabecera_clause = "AND f.cabecera = %s" if filtrar_cabecera and cab else ""

        sql = f"""
            WITH traz AS (
                SELECT ST_LineMerge(ST_Union(o.{geom_q}::geometry)) AS g
                FROM {schema_q}.{ci_op_q} o
                WHERE o.{op_q} = ANY(%s)
            ),
            fosc_near AS (
                SELECT
                    f.id_botella,
                    f.tipo,
                    f.id_cm,
                    f.direccion,
                    ST_Y(f.{geom_q}::geometry) AS lat,
                    ST_X(f.{geom_q}::geometry) AS lon,
                    ST_Distance(
                        f.{geom_q}::geography,
                        (SELECT g FROM traz)::geography
                    ) AS dist_traz_m
                FROM {schema_q}.{table_q} f
                WHERE f.{geom_q} IS NOT NULL
                  AND (SELECT g FROM traz) IS NOT NULL
                  {cabecera_clause}
                  AND ST_DWithin(
                      f.{geom_q}::geography,
                      (SELECT g FROM traz)::geography,
                      %s
                  )
            )
            SELECT * FROM fosc_near
            ORDER BY dist_traz_m ASC
            LIMIT %s
        """
        params: tuple[Any, ...] = (ramas,)
        if filtrar_cabecera and cab:
            params = params + (cab,)
        params = params + (max_dist, lim)
        try:
            cur.execute(sql, params)
        except Exception as exc:
            logger.exception("consultar_fosc_cerca_trazado_ramas falló")
            return {"ok": False, "error": f"Error SQL FOSC: {str(exc)[:400]}", "markers": []}

        colnames = [d[0] for d in (cur.description or [])]
        markers = []
        for row in cur.fetchall():
            m = _fosc_row_to_marker(row, colnames)
            if m:
                markers.append(m)

    markers, deduped = _dedupe_fosc_markers(markers)
    result: dict[str, Any] = {
        "ok": True,
        "cabecera": cab or None,
        "cabecera_filtrada": bool(filtrar_cabecera and cab),
        "table": f"{schema}.{table}",
        "max_dist_traz_m": max_dist,
        "markers": markers,
    }
    if deduped:
        result["deduplicadas"] = deduped
    return result


def consultar_fosc_ordenadas_en_rama(
    ramas: list[str],
    *,
    cabecera: str | None = None,
    gis: dict | None = None,
    focal_lat: float | None = None,
    focal_lon: float | None = None,
    max_dist_traz_m: float | None = None,
    limit: int | None = None,
    filtrar_cabecera: bool = False,
) -> dict[str, Any]:
    """Botellas FOSC sobre el trazado ci_op de la(s) rama(s), ordenadas cabecera → CTO."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    if not ramas:
        return {"ok": False, "error": "Sin ramas.", "markers": []}

    cab = (cabecera or cabecera_para_fosc(ramas[0], gis)).strip().upper()
    if filtrar_cabecera and not cab:
        return {"ok": False, "error": "No se pudo inferir cabecera para FOSC.", "markers": []}

    use_focal = focal_lat is not None and focal_lon is not None
    try:
        f_la, f_lo = (float(focal_lat), float(focal_lon)) if use_focal else (0.0, 0.0)
    except (TypeError, ValueError):
        use_focal = False
        f_la, f_lo = 0.0, 0.0

    schema = _env_schema()
    table = _env_fosc_table()
    max_dist = max_dist_traz_m if max_dist_traz_m is not None else _env_fosc_max_dist_traz_m()
    lim = limit if limit is not None else min(80, _env_fosc_map_limit())

    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla FOSC inválida.", "markers": []}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table}.",
                "markers": [],
            }
        geom_col = _geometry_column(cur, schema, table)
        if not geom_col:
            return {"ok": False, "error": "Sin geometría FOSC.", "markers": []}

        cols = set(_list_data_columns(cur, schema, table))
        if "cabecera" not in cols:
            return {"ok": False, "error": "Capa FOSC sin columna cabecera.", "markers": []}

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        geom_q = _quote_ident(geom_col)
        ci_op_table = _env_ci_op_table()
        ci_op_cols = set(_list_data_columns(cur, schema, ci_op_table))
        op_col = None
        for c in ("nombre_co_atc", "nombre_co_claro", "nombre_op"):
            if c in ci_op_cols:
                op_col = c
                break
        if not op_col:
            return {"ok": False, "error": "ci_op sin columna de rama.", "markers": []}

        op_q = _quote_ident(op_col)
        ci_op_q = _quote_ident(ci_op_table)

        orient_sql = ""
        if use_focal:
            orient_sql = """
            traz_oriented AS (
                SELECT CASE
                    WHEN ST_Distance(
                        ST_StartPoint(g)::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) > ST_Distance(
                        ST_EndPoint(g)::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    )
                    THEN ST_Reverse(g)
                    ELSE g
                END AS g
                FROM traz_line
            ),
            """
            extra_params_end = (f_lo, f_la, f_lo, f_la)
        else:
            orient_sql = """
            traz_oriented AS (
                SELECT g FROM traz_line
            ),
            """
            extra_params_end = ()

        cabecera_clause = "AND f.cabecera = %s" if filtrar_cabecera and cab else ""

        sql = f"""
            WITH traz_raw AS (
                SELECT ST_LineMerge(ST_UnaryUnion(ST_Collect(o.{geom_q}::geometry))) AS g
                FROM {schema_q}.{ci_op_q} o
                WHERE o.{op_q} = ANY(%s)
            ),
            traz_line AS (
                SELECT
                    CASE
                        WHEN g IS NULL THEN NULL
                        WHEN ST_GeometryType(g) = 'ST_LineString' THEN g
                        WHEN ST_GeometryType(g) = 'ST_MultiLineString' THEN (
                            SELECT d.geom
                            FROM ST_Dump(g) AS d
                            WHERE ST_GeometryType(d.geom) = 'ST_LineString'
                            ORDER BY ST_Length(d.geom::geography) DESC
                            LIMIT 1
                        )
                        ELSE ST_LineMerge(ST_CollectionExtract(g, 2))
                    END AS g
                FROM traz_raw
            ),
            {orient_sql}
            traz AS (
                SELECT g
                FROM traz_oriented
                WHERE g IS NOT NULL
                  AND ST_GeometryType(g) = 'ST_LineString'
                LIMIT 1
            ),
            fosc_near AS (
                SELECT
                    f.id_botella,
                    f.tipo,
                    f.id_cm,
                    f.direccion,
                    ST_Y(f.{geom_q}::geometry) AS lat,
                    ST_X(f.{geom_q}::geometry) AS lon,
                    ST_Distance(
                        f.{geom_q}::geography,
                        t.g::geography
                    ) AS dist_traz_m,
                    ST_LineLocatePoint(t.g, f.{geom_q}::geometry) AS frac_linea,
                    ST_LineLocatePoint(t.g, f.{geom_q}::geometry)
                        * ST_Length(t.g::geography) AS dist_cabecera_m
                FROM {schema_q}.{table_q} f
                CROSS JOIN traz t
                WHERE f.{geom_q} IS NOT NULL
                  AND t.g IS NOT NULL
                  {cabecera_clause}
                  AND ST_DWithin(
                      f.{geom_q}::geography,
                      t.g::geography,
                      %s
                  )
            )
            SELECT * FROM fosc_near
            ORDER BY frac_linea ASC NULLS LAST, dist_traz_m ASC
            LIMIT %s
        """
        params: tuple[Any, ...] = (ramas,)
        if use_focal:
            params = params + extra_params_end
        if filtrar_cabecera and cab:
            params = params + (cab,)
        params = params + (max_dist, lim)

        try:
            cur.execute(sql, params)
        except Exception as exc:
            logger.exception("consultar_fosc_ordenadas_en_rama falló")
            fallback = consultar_fosc_cerca_trazado_ramas(
                ramas,
                cab or cabecera_para_fosc(ramas[0], gis) or None,
                max_dist_traz_m=max_dist,
                limit=lim,
                filtrar_cabecera=filtrar_cabecera,
            )
            if not fallback.get("ok"):
                return {
                    "ok": False,
                    "error": f"Error SQL FOSC ordenadas: {str(exc)[:400]}",
                    "markers": [],
                }
            markers_fb = []
            for i, m in enumerate(fallback.get("markers") or [], start=1):
                markers_fb.append({**m, "orden": i, "frac_linea": None, "dist_cabecera_m": None})
            return {
                "ok": True,
                "cabecera": cab or None,
                "cabecera_filtrada": bool(filtrar_cabecera and cab),
                "markers": markers_fb,
                "max_dist_traz_m": max_dist,
                "nota": "Orden aproximado (sin ST_LineLocatePoint sobre el trazado).",
            }

        colnames = [d[0] for d in (cur.description or [])]
        markers: list[dict[str, Any]] = []
        orden = 0
        for row in cur.fetchall():
            m = _fosc_row_to_marker(row, colnames)
            if not m:
                continue
            orden += 1
            rec = dict(zip(colnames, row))
            try:
                frac = float(rec.get("frac_linea") or 0)
            except (TypeError, ValueError):
                frac = 0.0
            try:
                dist_cab = round(float(rec.get("dist_cabecera_m") or 0), 1)
            except (TypeError, ValueError):
                dist_cab = None
            m["orden"] = orden
            m["frac_linea"] = round(frac, 4)
            m["dist_cabecera_m"] = dist_cab
            m["maps_url"] = f"https://www.google.com/maps?q={m['lat']},{m['lon']}"
            markers.append(m)

    markers, deduped = _dedupe_fosc_markers(markers)
    result: dict[str, Any] = {
        "ok": True,
        "cabecera": cab or None,
        "cabecera_filtrada": bool(filtrar_cabecera and cab),
        "markers": markers,
        "max_dist_traz_m": max_dist,
    }
    if deduped:
        result["deduplicadas"] = deduped
    return result


def consultar_feeder_distribucion_planta_interna(
    ramas: list[str],
    *,
    cabecera: str | None = None,
    gis: dict | None = None,
    focal_lat: float | None = None,
    focal_lon: float | None = None,
    pelos_feeder: int = 144,
    max_dist_traz_m: float | None = None,
) -> dict[str, Any]:
    """Feeder FO144: superposición ``ci_feeder_distribution`` + ``ci_op`` (paso PDF QGIS)."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    if not ramas:
        return {"ok": False, "error": "Sin ramas."}

    cab = (cabecera or cabecera_para_fosc(ramas[0], gis)).strip().upper()
    if not cab:
        return {"ok": False, "error": "Sin cabecera para feeder."}

    use_focal = focal_lat is not None and focal_lon is not None
    try:
        f_la, f_lo = (float(focal_lat), float(focal_lon)) if use_focal else (None, None)
    except (TypeError, ValueError):
        use_focal = False
        f_la, f_lo = None, None

    schema = _env_schema()
    feeder_table = _env_feeder_dist_table()
    max_dist = max_dist_traz_m if max_dist_traz_m is not None else _env_feeder_max_dist_traz_m()
    max_fosc = _env_feeder_fosc_corte_m()

    if not _validate_ident(schema, feeder_table):
        return {"ok": False, "error": "Tabla feeder inválida."}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, feeder_table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{feeder_table} (CAMINO_GIS_FEEDER_DIST_TABLE).",
            }
        feeder_geom_col = _geometry_column(cur, schema, feeder_table)
        if not feeder_geom_col:
            return {"ok": False, "error": "Sin geometría en feeder distribution."}

        ci_op_table = _env_ci_op_table()
        ci_op_cols = set(_list_data_columns(cur, schema, ci_op_table))
        op_col = next(
            (c for c in ("nombre_co_atc", "nombre_co_claro", "nombre_op") if c in ci_op_cols),
            None,
        )
        if not op_col:
            return {"ok": False, "error": "ci_op sin columna de rama."}

        fosc_table = _env_fosc_table()
        fosc_geom_col = (
            _geometry_column(cur, schema, fosc_table) if _table_exists(cur, schema, fosc_table) else None
        )

        schema_q = _quote_ident(schema)
        feeder_q = _quote_ident(feeder_table)
        f_geom_q = _quote_ident(feeder_geom_col)
        op_q = _quote_ident(op_col)
        ci_op_q = _quote_ident(ci_op_table)

        orient_cte = (
            """
            traz_oriented AS (
                SELECT CASE
                    WHEN ST_Distance(
                        ST_StartPoint(g)::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    ) > ST_Distance(
                        ST_EndPoint(g)::geography,
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                    )
                    THEN ST_Reverse(g)
                    ELSE g
                END AS g
                FROM traz_line
            ),
            """
            if use_focal and f_la is not None
            else """
            traz_oriented AS (SELECT g FROM traz_line),
            """
        )

        fosc_cte = ""
        fosc_cte_comma = ""
        fosc_select = """
                NULL::bigint AS fosc_id_botella,
                NULL::text AS fosc_id_cm,
                NULL::text AS fosc_tipo,
                NULL::text AS fosc_direccion,
                NULL::double precision AS fosc_lat,
                NULL::double precision AS fosc_lon,
                NULL::double precision AS fosc_dist_corte_m"""
        fosc_join = ""
        if fosc_geom_col and _validate_ident(schema, fosc_table):
            fosc_q = _quote_ident(fosc_table)
            fg_q = _quote_ident(fosc_geom_col)
            fosc_cte_comma = ","
            fosc_cte = f"""
            fosc144 AS (
                SELECT
                    fo.id_botella,
                    fo.tipo,
                    fo.id_cm,
                    fo.direccion,
                    ST_Y(fo.{fg_q}::geometry) AS lat,
                    ST_X(fo.{fg_q}::geometry) AS lon,
                    ST_Distance(fo.{fg_q}::geography, c.pt::geography) AS dist_corte_m
                FROM {schema_q}.{fosc_q} fo
                CROSS JOIN corte c
                WHERE fo.cabecera = %s
                  AND fo.{fg_q} IS NOT NULL
                  AND c.pt IS NOT NULL
                  AND ST_DWithin(fo.{fg_q}::geography, c.pt::geography, %s)
                ORDER BY dist_corte_m ASC
                LIMIT 1
            )"""
            fosc_select = """
                fo.id_botella AS fosc_id_botella,
                fo.id_cm AS fosc_id_cm,
                fo.tipo AS fosc_tipo,
                fo.direccion AS fosc_direccion,
                fo.lat AS fosc_lat,
                fo.lon AS fosc_lon,
                fo.dist_corte_m AS fosc_dist_corte_m"""
            fosc_join = "LEFT JOIN fosc144 fo ON true"

        sql = f"""
            WITH traz_raw AS (
                SELECT ST_LineMerge(ST_UnaryUnion(ST_Collect(o.{f_geom_q}::geometry))) AS g
                FROM {schema_q}.{ci_op_q} o
                WHERE o.{op_q} = ANY(%s)
            ),
            traz_line AS (
                SELECT CASE
                    WHEN g IS NULL THEN NULL
                    WHEN ST_GeometryType(g) = 'ST_LineString' THEN g
                    WHEN ST_GeometryType(g) = 'ST_MultiLineString' THEN (
                        SELECT d.geom FROM ST_Dump(g) AS d
                        WHERE ST_GeometryType(d.geom) = 'ST_LineString'
                        ORDER BY ST_Length(d.geom::geography) DESC LIMIT 1
                    )
                    ELSE ST_LineMerge(ST_CollectionExtract(g, 2))
                END AS g
                FROM traz_raw
            ),
            {orient_cte}
            traz AS (
                SELECT g FROM traz_oriented
                WHERE g IS NOT NULL AND ST_GeometryType(g) = 'ST_LineString'
                LIMIT 1
            ),
            node AS (SELECT ST_StartPoint(g) AS p, g AS op_line FROM traz),
            ranked AS (
                SELECT
                    f.id_cable, f.nombre_atc, f.tipo, f.cantidad_pelos, f.geom AS fgeom,
                    ST_Length(f.geom::geography) AS len_m,
                    ST_Length(ST_Intersection(f.geom, n.op_line)::geography) AS shared_m,
                    ST_AsGeoJSON(f.geom)::json AS geojson,
                    CASE
                        WHEN f.cantidad_pelos = %s THEN 1
                        WHEN f.tipo ILIKE '%%FEEDER%%' AND f.cantidad_pelos >= %s THEN 2
                        ELSE 3
                    END AS prio_pelos
                FROM {schema_q}.{feeder_q} f
                CROSS JOIN node n
                WHERE f.cabecera = %s AND f.geom IS NOT NULL AND n.op_line IS NOT NULL
                  AND ST_DWithin(f.geom::geography, n.op_line::geography, %s)
                  AND ST_Length(ST_Intersection(f.geom, n.op_line)::geography) > 5
            ),
            best AS (
                SELECT * FROM ranked
                ORDER BY prio_pelos ASC, shared_m DESC NULLS LAST, len_m DESC
                LIMIT 1
            ),
            shared AS (
                SELECT ST_LineMerge(ST_Intersection(fgeom, op_line)) AS g FROM best, node
            ),
            shared_oriented AS (
                SELECT CASE
                    WHEN g IS NULL OR ST_IsEmpty(g) THEN NULL
                    WHEN ST_Distance(ST_StartPoint(g)::geography, (SELECT p FROM node)::geography)
                         <= ST_Distance(ST_EndPoint(g)::geography, (SELECT p FROM node)::geography)
                    THEN g ELSE ST_Reverse(g)
                END AS g FROM shared
            ),
            corte AS (
                SELECT ST_EndPoint(g) AS pt FROM shared_oriented
                WHERE g IS NOT NULL AND ST_GeometryType(g) = 'ST_LineString'
            ){fosc_cte_comma}
            {fosc_cte}
            SELECT
                b.id_cable, b.nombre_atc, b.tipo, b.cantidad_pelos,
                b.len_m, b.shared_m, b.geojson,
                ST_Y(c.pt) AS cut_lat, ST_X(c.pt) AS cut_lon,
                ST_Length((SELECT g FROM shared_oriented)::geography) AS shared_len_m,
                {fosc_select}
            FROM best b
            LEFT JOIN corte c ON true
            {fosc_join}
        """

        params: list[Any] = [ramas]
        if use_focal and f_la is not None:
            params.extend([f_lo, f_la, f_lo, f_la])
        params.extend([pelos_feeder, pelos_feeder, cab, max_dist])
        if fosc_geom_col:
            params.extend([cab, max_fosc])

        try:
            cur.execute(sql, tuple(params))
        except Exception as exc:
            logger.exception("consultar_feeder_distribucion_planta_interna falló")
            return {"ok": False, "error": f"Error SQL feeder: {str(exc)[:400]}"}

        row = cur.fetchone()
        if not row:
            return {
                "ok": False,
                "error": "Sin feeder que se superponga al trazado ci_op cerca del nodo (cabecera).",
                "cabecera": cab,
                "max_dist_traz_m": max_dist,
            }

        colnames = [d[0] for d in (cur.description or [])]
        rec = dict(zip(colnames, row))
        geo = _parse_geojson_cell(rec.get("geojson"))
        features = []
        if geo:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "capa": "feeder_distribution",
                        "nombre_atc": rec.get("nombre_atc"),
                        "cantidad_pelos": rec.get("cantidad_pelos"),
                        "tipo": rec.get("tipo"),
                    },
                    "geometry": geo,
                }
            )

        cut_lat = rec.get("cut_lat")
        cut_lon = rec.get("cut_lon")
        corte = None
        if cut_lat is not None and cut_lon is not None:
            try:
                la, lo = float(cut_lat), float(cut_lon)
                corte = {
                    "lat": round(la, 6),
                    "lon": round(lo, 6),
                    "maps_url": f"https://www.google.com/maps?q={la},{lo}",
                    "motivo": (
                        "Fin del tramo común feeder + ci_op desde cabecera "
                        "(donde el alimentador deja de coincidir con el camino óptico)."
                    ),
                }
            except (TypeError, ValueError):
                corte = None

        fosc144 = None
        if rec.get("fosc_lat") is not None and rec.get("fosc_lon") is not None:
            try:
                fla, flo = float(rec["fosc_lat"]), float(rec["fosc_lon"])
                fosc144 = {
                    "id_botella": rec.get("fosc_id_botella"),
                    "id_cm": (rec.get("fosc_id_cm") or "").strip(),
                    "tipo": (rec.get("fosc_tipo") or "FOSC").strip(),
                    "direccion": (rec.get("fosc_direccion") or "").strip(),
                    "lat": round(fla, 6),
                    "lon": round(flo, 6),
                    "dist_corte_m": round(float(rec.get("fosc_dist_corte_m") or 0), 1),
                    "maps_url": f"https://www.google.com/maps?q={fla},{flo}",
                }
            except (TypeError, ValueError):
                fosc144 = None

        try:
            len_m = round(float(rec.get("len_m") or 0), 1)
        except (TypeError, ValueError):
            len_m = None
        try:
            shared_m = round(float(rec.get("shared_m") or 0), 1)
        except (TypeError, ValueError):
            shared_m = None

        feeder = {
            "id_cable": rec.get("id_cable"),
            "nombre_atc": (rec.get("nombre_atc") or "").strip(),
            "tipo": (rec.get("tipo") or "").strip(),
            "cantidad_pelos": rec.get("cantidad_pelos"),
            "length_m": len_m,
            "shared_m": shared_m,
        }

        return {
            "ok": True,
            "table": f"{schema}.{feeder_table}",
            "cabecera": cab,
            "pelos_feeder": pelos_feeder,
            "max_dist_traz_m": max_dist,
            "feeder": feeder,
            "geojson": {"type": "FeatureCollection", "features": features},
            "corte_feeder": corte,
            "fosc_144": fosc144,
            "motivo": (
                f"Feeder «{feeder.get('nombre_atc') or '?'}» "
                f"({feeder.get('cantidad_pelos') or '?'} pelos) superpuesto "
                f"≈ {shared_m or '?'} m al ci_op."
            ),
        }


def es_codigo_fusion_planta(valor: str) -> bool:
    """True si el token parece fusión de planta (``SF01-R1301-010``)."""
    return bool(_FUSION_PLANTA_RE.match((valor or "").strip().upper()))


def _fosc_id_desde_component_fullname(raw: object) -> str:
    s = (str(raw or "")).strip()
    if not s:
        return ""
    head = s.split(">")[0].strip()
    if "FOSC" in head.upper():
        return head
    return ""


def _fosc_id_desde_fila_fusion(location_name: object, component_fullname_b: object) -> str:
    """FOSC de la fila: ``location_name`` (CM) o cabecera de ``component_fullname_b``."""
    loc = (str(location_name or "")).strip()
    if es_id_fosc_cm(loc):
        return loc
    return _fosc_id_desde_component_fullname(component_fullname_b)


def _enriquecer_fosc_alias_en_markers(
    markers: list[dict[str, Any]], schema: str
) -> None:
    """Agrega ``fosc_alias`` (``ci_fosc.nombre_atc``, ej. SF01-FATC-3-002759)."""
    ids = sorted({(m.get("fosc_id_cm") or "").strip() for m in markers} - {""})
    if not ids:
        return
    alias_by_id: dict[str, str] = {}
    with db_cursor() as cur:
        for fosc_id in ids:
            meta = _lookup_ci_fosc_meta(cur, schema, fosc_id)
            alias = (meta.get("nombre_atc") or "").strip()
            if alias:
                alias_by_id[fosc_id] = alias
    for mk in markers:
        fid = (mk.get("fosc_id_cm") or "").strip()
        if fid and fid in alias_by_id:
            mk["fosc_alias"] = alias_by_id[fid]


def _rama_tail_desde_fusion(codigo: str) -> str | None:
    """``SF01-R1301-010`` → sufijo de rama ``001301`` (segmento R1301)."""
    m = _FUSION_PLANTA_RE.match((codigo or "").strip().upper())
    if not m:
        return None
    seg_m = re.search(r"-R(\d+)-", codigo, re.I)
    if not seg_m:
        return None
    try:
        return f"{int(seg_m.group(1)):06d}"
    except ValueError:
        return None


def resolver_rama_desde_fusion_planta(codigo: str) -> dict[str, Any]:
    """Resuelve ``SF01-R1301-010`` → rama operativa ``SF01-RATC-…`` vía ``report_fusiones``."""
    codigo = (codigo or "").strip().upper()
    if not es_codigo_fusion_planta(codigo):
        return {"ok": False, "error": "Formato de fusión inválido (ej. SF01-R1301-010)."}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida."}

    rama_tail = _rama_tail_desde_fusion(codigo)

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_FUSIONES_TABLE).",
            }
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        if rama_tail:
            cur.execute(
                f"""
                SELECT path_atc, COUNT(*)::int AS n
                FROM {schema_q}.{table_q}
                WHERE location_description = %s
                  AND path_atc IS NOT NULL
                  AND path_atc ILIKE '%%-RATC-%%'
                  AND path_atc ILIKE %s
                GROUP BY path_atc
                ORDER BY n DESC, path_atc
                LIMIT 5
                """,
                (codigo, f"%-{rama_tail}"),
            )
            ratc_hint = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
            if ratc_hint:
                return {
                    "ok": True,
                    "rama": ratc_hint[0],
                    "fusion_id": codigo,
                    "ramas_alt": ratc_hint[1:],
                    "nota": (
                        f"Rama inferida por segmento R{int(rama_tail)} del código de fusión. "
                        "Si el ticket indica otra rama RATC, buscala directamente."
                    ),
                }

        cur.execute(
            f"""
            SELECT path_atc, COUNT(*)::int AS n
            FROM {schema_q}.{table_q}
            WHERE location_description = %s
              AND path_atc IS NOT NULL
              AND TRIM(path_atc) <> ''
              AND path_atc ILIKE '%%-RATC-%%'
            GROUP BY path_atc
            ORDER BY n DESC, path_atc
            LIMIT 5
            """,
            (codigo,),
        )
        ratc = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
        if ratc:
            nota = None
            if len(ratc) > 1:
                nota = (
                    f"Varias ramas RATC comparten la fusión «{codigo}»; "
                    f"se abre «{ratc[0]}». Si el incidente es otra rama, buscala por código RATC."
                )
            return {"ok": True, "rama": ratc[0], "fusion_id": codigo, "ramas_alt": ratc[1:], "nota": nota}

        cur.execute(
            f"""
            SELECT DISTINCT path_atc
            FROM {schema_q}.{table_q}
            WHERE location_description = %s
              AND path_atc IS NOT NULL
              AND TRIM(path_atc) <> ''
            ORDER BY path_atc
            LIMIT 3
            """,
            (codigo,),
        )
        otros = [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
        if otros:
            return {
                "ok": True,
                "rama": otros[0],
                "fusion_id": codigo,
                "nota": "Sin rama RATC; se usa path_atc del reporte de fusiones.",
            }

    return {
        "ok": False,
        "error": f"No hay rama asociada a la fusión «{codigo}» en report_fusiones.",
    }


def consultar_fusiones_verificacion_rama(
    ramas: list[str],
    *,
    fusion_destacar: str | None = None,
) -> dict[str, Any]:
    """Puntos de verificación planta interna (``report_fusiones``) para la rama caída."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    if not ramas:
        return {"ok": False, "error": "Sin ramas.", "markers": []}

    schema = _env_schema()
    table = _env_fusiones_table()
    lim = _env_fusiones_limit()
    destacar = (fusion_destacar or "").strip().upper() or None

    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida.", "markers": []}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table}.",
                "markers": [],
            }
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        try:
            cur.execute(
                f"""
                SELECT DISTINCT ON (f.location_description)
                    f.location_description,
                    f.path_atc,
                    f.location_name,
                    f.component_fullname_b,
                    f.splice,
                    f.geo_y AS lat,
                    f.geo_x AS lon
                FROM {schema_q}.{table_q} f
                WHERE f.path_atc = ANY(%s)
                  AND f.location_description IS NOT NULL
                  AND f.location_description ~ '^[A-Za-z0-9]{{2,12}}-R[0-9]+-[0-9]{{3}}$'
                  AND f.geo_x IS NOT NULL
                  AND f.geo_y IS NOT NULL
                ORDER BY f.location_description, f.splice NULLS LAST
                LIMIT %s
                """,
                (ramas, lim),
            )
        except Exception as exc:
            logger.exception("consultar_fusiones_verificacion_rama falló")
            return {"ok": False, "error": f"Error SQL fusiones: {str(exc)[:400]}", "markers": []}

        rows = cur.fetchall()
        if not rows and destacar:
            try:
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (f.location_description)
                        f.location_description,
                        f.path_atc,
                        f.location_name,
                        f.component_fullname_b,
                        f.splice,
                        f.geo_y AS lat,
                        f.geo_x AS lon
                    FROM {schema_q}.{table_q} f
                    WHERE f.location_description = %s
                      AND f.geo_x IS NOT NULL
                      AND f.geo_y IS NOT NULL
                    ORDER BY f.location_description, f.splice NULLS LAST
                    LIMIT 1
                    """,
                    (destacar,),
                )
                rows = cur.fetchall()
            except Exception:
                rows = []

    markers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        fusion_id = (row[0] or "").strip().upper()
        if not fusion_id or fusion_id in seen:
            continue
        seen.add(fusion_id)
        try:
            la, lo = float(row[5]), float(row[6])
        except (TypeError, ValueError, IndexError):
            continue
        if abs(la) > 90 or abs(lo) > 180:
            continue
        fosc_id = _fosc_id_desde_fila_fusion(row[2] if len(row) > 2 else "", row[3] if len(row) > 3 else "")
        mk = {
            "fusion_id": fusion_id,
            "path_atc": (row[1] or "").strip(),
            "fosc_id_cm": fosc_id,
            "splice": (row[4] or "").strip() if len(row) > 4 else "",
            "lat": round(la, 6),
            "lon": round(lo, 6),
            "maps_url": f"https://www.google.com/maps?q={la},{lo}",
            "destacar": destacar == fusion_id if destacar else False,
            "fuera_trazado": True,
        }
        markers.append(mk)

    markers.sort(key=lambda m: m.get("fusion_id") or "")
    if destacar:
        for m in markers:
            m["destacar"] = m.get("fusion_id") == destacar
        if not any(m.get("destacar") for m in markers):
            with db_cursor() as cur2:
                if _table_exists(cur2, schema, table):
                    schema_q = _quote_ident(schema)
                    table_q = _quote_ident(table)
                    cur2.execute(
                        f"""
                        SELECT DISTINCT ON (location_description)
                            location_description, path_atc, location_name, component_fullname_b,
                            splice, geo_y, geo_x
                        FROM {schema_q}.{table_q}
                        WHERE location_description = %s
                          AND geo_x IS NOT NULL AND geo_y IS NOT NULL
                        LIMIT 1
                        """,
                        (destacar,),
                    )
                    extra = cur2.fetchone()
                    if extra:
                        try:
                            la, lo = float(extra[5]), float(extra[6])
                            markers.insert(
                                0,
                                {
                                    "fusion_id": destacar,
                                    "path_atc": (extra[1] or "").strip(),
                                    "fosc_id_cm": _fosc_id_desde_fila_fusion(extra[2], extra[3]),
                                    "splice": (extra[4] or "").strip(),
                                    "lat": round(la, 6),
                                    "lon": round(lo, 6),
                                    "maps_url": f"https://www.google.com/maps?q={la},{lo}",
                                    "destacar": True,
                                    "fuera_trazado": True,
                                },
                            )
                        except (TypeError, ValueError):
                            pass

    _enriquecer_fosc_alias_en_markers(markers, schema)

    return {
        "ok": True,
        "table": f"{schema}.{table}",
        "markers": markers,
        "count": len(markers),
        "fusion_destacar": destacar,
        "motivo": (
            "Puntos de fusión / verificación en campo (report_fusiones), "
            "pueden estar fuera del trazado ci_op."
        ),
    }


def snap_corte_a_fosc(
    ramas: list[str],
    cut_lat: float,
    cut_lon: float,
    cabecera: str | None = None,
    *,
    max_dist_traz_m: float | None = None,
    max_snap_m: float | None = None,
) -> dict[str, Any]:
    """Ajusta el punto de corte a la botella FOSC más cercana sobre el trazado."""
    ramas = [str(r).strip() for r in (ramas or []) if str(r).strip()]
    try:
        la, lo = float(cut_lat), float(cut_lon)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Coordenadas de corte inválidas."}
    if not ramas:
        return {"ok": False, "error": "Sin ramas."}

    cabecera = (cabecera or cabecera_desde_rama(ramas[0])).strip().upper()
    if not cabecera:
        return {"ok": False, "error": "Sin cabecera."}

    schema = _env_schema()
    table = _env_fosc_table()
    max_traz = max_dist_traz_m if max_dist_traz_m is not None else _env_fosc_max_dist_traz_m()
    max_snap = max_snap_m if max_snap_m is not None else _env_fosc_max_snap_m()

    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla FOSC inválida."}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {"ok": False, "error": f"No existe {schema}.{table}."}
        geom_col = _geometry_column(cur, schema, table)
        if not geom_col:
            return {"ok": False, "error": "Sin geometría FOSC."}

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        geom_q = _quote_ident(geom_col)
        op_col = None
        ci_op_table = _env_ci_op_table()
        ci_op_cols = set(_list_data_columns(cur, schema, ci_op_table))
        for c in ("nombre_co_atc", "nombre_co_claro", "nombre_op"):
            if c in ci_op_cols:
                op_col = c
                break
        if not op_col:
            return {"ok": False, "error": "ci_op sin columna de rama."}

        op_q = _quote_ident(op_col)
        ci_op_q = _quote_ident(ci_op_table)

        sql = f"""
            WITH traz AS (
                SELECT ST_LineMerge(ST_Union(o.{geom_q}::geometry)) AS g
                FROM {schema_q}.{ci_op_q} o
                WHERE o.{op_q} = ANY(%s)
            ),
            corte AS (
                SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326) AS p
            ),
            on_line AS (
                SELECT ST_ClosestPoint(t.g, c.p) AS p_line
                FROM traz t, corte c
                WHERE t.g IS NOT NULL
            ),
            candidatas AS (
                SELECT
                    f.id_botella,
                    f.tipo,
                    f.id_cm,
                    f.direccion,
                    ST_Y(f.{geom_q}::geometry) AS lat,
                    ST_X(f.{geom_q}::geometry) AS lon,
                    ST_Distance(
                        f.{geom_q}::geography,
                        (SELECT g FROM traz)::geography
                    ) AS dist_traz_m,
                    ST_Distance(
                        f.{geom_q}::geography,
                        (SELECT p_line FROM on_line)::geography
                    ) AS dist_snap_m,
                    ST_Distance(
                        f.{geom_q}::geography,
                        (SELECT p FROM corte)::geography
                    ) AS dist_corte_m
                FROM {schema_q}.{table_q} f
                WHERE f.cabecera = %s
                  AND f.{geom_q} IS NOT NULL
                  AND (SELECT g FROM traz) IS NOT NULL
                  AND (SELECT p_line FROM on_line) IS NOT NULL
                  AND ST_DWithin(
                      f.{geom_q}::geography,
                      (SELECT g FROM traz)::geography,
                      %s
                  )
                  AND ST_DWithin(
                      f.{geom_q}::geography,
                      (SELECT p_line FROM on_line)::geography,
                      %s
                  )
            )
            SELECT * FROM candidatas
            ORDER BY dist_snap_m ASC, dist_corte_m ASC
            LIMIT 1
        """
        try:
            cur.execute(sql, (ramas, lo, la, cabecera, max_traz, max_snap))
        except Exception as exc:
            logger.exception("snap_corte_a_fosc falló")
            return {"ok": False, "error": f"Error SQL snap: {str(exc)[:400]}"}

        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "Sin botella FOSC cercana al troncal en el radio configurado."}

        colnames = [d[0] for d in (cur.description or [])]
        rec = dict(zip(colnames, row))
        marker = _fosc_row_to_marker(row, colnames)
        if not marker:
            return {"ok": False, "error": "Botella sin coordenadas válidas."}

        try:
            dist_snap = round(float(rec.get("dist_snap_m") or 0), 1)
            dist_corte = round(float(rec.get("dist_corte_m") or 0), 1)
        except (TypeError, ValueError):
            dist_snap, dist_corte = None, None

        out = {
            "ok": True,
            "metodo": "fosc_sobre_troncal",
            **marker,
            "dist_snap_m": dist_snap,
            "dist_corte_m": dist_corte,
            "maps_url": (
                f"https://www.google.com/maps?q={marker['lat']},{marker['lon']}"
            ),
        }
        return out


def _validate_ident(schema: str, name: str) -> bool:
    if not schema or not name:
        return False
    return bool(_ID_RE.match(schema) and _ID_RE.match(name))


def _quote_ident(name: str) -> str:
    if not _ID_RE.match(name):
        raise ValueError("identificador inválido")
    return '"' + name.replace('"', '""') + '"'


def _table_exists(cur, schema: str, table: str) -> bool:
    if not _validate_ident(schema, table):
        return False
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return cur.fetchone() is not None


def _list_data_columns(cur, schema: str, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    return [r[0] for r in cur.fetchall()]


def _geometry_column(cur, schema: str, table: str) -> str | None:
    try:
        cur.execute(
            """
            SELECT f_geometry_column
            FROM public.geometry_columns
            WHERE f_table_schema = %s AND f_table_name = %s
            LIMIT 1
            """,
            (schema, table),
        )
        row = cur.fetchone()
        if row and row[0] and _ID_RE.match(str(row[0])):
            return str(row[0])
    except Exception:
        logger.debug("geometry_columns no disponible o sin fila para %s.%s", schema, table)

    cols = set(_list_data_columns(cur, schema, table))
    for guess in ("geom", "shape", "wkb_geometry", "the_geom", "geometry"):
        if guess in cols:
            return guess
    return None


def _geometry_srid(cur, schema: str, table: str, geom_col: str) -> int | None:
    """SRID registrado en `geometry_columns` para la columna (si existe)."""
    if not _validate_ident(schema, table) or not _ID_RE.match(geom_col):
        return None
    try:
        cur.execute(
            """
            SELECT srid
            FROM public.geometry_columns
            WHERE f_table_schema = %s AND f_table_name = %s AND f_geometry_column = %s
            LIMIT 1
            """,
            (schema, table, geom_col),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:
        logger.debug("No se pudo leer srid para %s.%s.%s", schema, table, geom_col)
    return None


def _env_assume_srid() -> int | None:
    raw = (os.environ.get("CAMINO_GIS_ASSUME_SRID") or "").strip()
    if raw.isdigit():
        n = int(raw)
        return n if n > 0 else None
    return None


def _as_geojson_sql_fragment(geom_q: str, cur, schema: str, table: str, geom_col: str) -> str:
    """Expresión SQL: GeoJSON en WGS84 (lon, lat) para Leaflet."""
    cast = f"{geom_q}::geometry"
    srid = _geometry_srid(cur, schema, table, geom_col)
    assume = _env_assume_srid()

    if srid is not None and srid not in (0, 4326):
        expr = f"ST_Transform({cast}, 4326)"
    elif assume is not None and assume not in (4326,):
        expr = f"ST_Transform(ST_SetSRID({cast}, {assume}), 4326)"
    else:
        expr = cast

    return f"ST_AsGeoJSON({expr})::text AS __gj"


def _maybe_swap_lat_lon_in_geojson(geom: Any) -> Any:
    """Corrige pares (lat, lon) guardados como (x, y) en WGS84 · región AR/cono sur.

    GeoJSON exige [lon, lat]. Si el primer valor cae en banda latitud y el segundo en
    longitud típica de Argentina, se invierte el par.
    """
    if not isinstance(geom, dict):
        return geom

    def fix_pt(pt: Any) -> Any:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return pt
        try:
            a, b = float(pt[0]), float(pt[1])
        except (TypeError, ValueError):
            return pt
        # Valores en metros (proyectados) no tocar
        if abs(a) > 180 or abs(b) > 180 or abs(a) > 90 and abs(b) > 90:
            return [a, b]
        lat_band = -56 <= a <= -20
        lon_band = -74 <= b <= -40
        if lat_band and lon_band:
            return [b, a]
        return [a, b]

    def walk_coords(coords: Any, depth: int) -> Any:
        if depth == 0:
            return fix_pt(coords)
        if isinstance(coords, list):
            return [walk_coords(c, depth - 1) for c in coords]
        return coords

    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not gtype or coords is None:
        return geom

    depth_by_type = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }
    depth = depth_by_type.get(str(gtype))
    if depth is not None:
        geom = dict(geom)
        geom["coordinates"] = walk_coords(coords, depth)
    return geom


def _json_safe_prop(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, memoryview):
        return None
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return None
    return val


def _rows_to_feature_collection(
    cur,
    schema: str,
    table: str,
    where_sql: str,
    params: tuple[Any, ...],
) -> dict[str, Any]:
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Parámetros de tabla inválidos."}

    if not _table_exists(cur, schema, table):
        return {
            "ok": False,
            "error": (
                f"No existe la tabla {schema}.{table}. "
                "Ajustá CAMINO_GIS_CI_OP_TABLE si el nombre difiere."
            ),
        }

    geom_col = _geometry_column(cur, schema, table)
    if not geom_col:
        return {
            "ok": False,
            "error": (
                f"No se detectó columna de geometría en {schema}.{table} "
                "(¿PostGIS instalado y tablas registradas?)."
            ),
        }

    cols = _list_data_columns(cur, schema, table)
    if geom_col not in cols:
        return {"ok": False, "error": "Columna de geometría inconsistente."}

    prop_cols = [c for c in cols if c != geom_col]
    if not prop_cols:
        return {"ok": False, "error": "La tabla no tiene columnas de atributos."}

    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    geom_q = _quote_ident(geom_col)
    select_list = ", ".join(_quote_ident(c) for c in prop_cols)
    gj_sql = _as_geojson_sql_fragment(geom_q, cur, schema, table, geom_col)
    select_list += f", {gj_sql}"

    sql = (
        f"SELECT {select_list} FROM {schema_q}.{table_q} WHERE {where_sql} LIMIT 200"
    )

    try:
        cur.execute(sql, params)
    except Exception as exc:
        logger.info(
            "camino_gis: reintento sin ST_Transform en %s.%s (%s)", schema, table, exc
        )
        select_list_fallback = ", ".join(_quote_ident(c) for c in prop_cols)
        select_list_fallback += f", ST_AsGeoJSON({geom_q}::geometry)::text AS __gj"
        sql_fb = (
            f"SELECT {select_list_fallback} FROM {schema_q}.{table_q} "
            f"WHERE {where_sql} LIMIT 200"
        )
        try:
            cur.execute(sql_fb, params)
        except Exception as exc2:
            logger.exception("camino_gis query falló en %s.%s", schema, table)
            msg = str(exc2).strip()
            if "st_asgeojson" in msg.lower() or "function" in msg.lower():
                return {
                    "ok": False,
                    "error": (
                        "PostGIS no disponible o geometría no soportada para ST_AsGeoJSON. "
                        f"Detalle: {msg[:500]}"
                    ),
                }
            return {"ok": False, "error": f"Error SQL: {msg[:500]}"}

    colnames = [d[0] for d in (cur.description or [])]
    features: list[dict[str, Any]] = []
    for row in cur.fetchall():
        rec = dict(zip(colnames, row))
        gj = rec.pop("__gj", None)
        if not gj:
            continue
        try:
            geom = json.loads(gj)
        except (json.JSONDecodeError, TypeError):
            continue
        geom = _maybe_swap_lat_lon_in_geojson(geom)
        props = {
            k: _json_safe_prop(v)
            for k, v in rec.items()
            if v is not None and _json_safe_prop(v) is not None
        }
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    out: dict[str, Any] = {
        "ok": True,
        "geojson": {"type": "FeatureCollection", "features": features},
        "table": f"{schema}.{table}",
        "geom_column": geom_col,
    }
    srid = _geometry_srid(cur, schema, table, geom_col)
    if srid is not None:
        out["geom_srid"] = srid
    return out


def consultar_ci_op_por_rama(rama: str) -> dict[str, Any]:
    """Filtra la capa configurada (p. ej. `ci_op`) por nombre_co_claro / nombre_co_atc / nombre_op."""
    rama = (rama or "").strip()
    if not rama:
        return {"ok": False, "error": "Rama vacía"}

    schema = _env_schema()
    table = _env_ci_op_table()

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_CI_OP_TABLE).",
            }
        cols = set(_list_data_columns(cur, schema, table))

        conds = []
        params: list[Any] = []
        if "nombre_co_claro" in cols:
            conds.append(f"{_quote_ident('nombre_co_claro')} = %s")
            params.append(rama)
        if "nombre_co_atc" in cols:
            conds.append(f"{_quote_ident('nombre_co_atc')} = %s")
            params.append(rama)
        if not conds and "nombre_op" in cols:
            conds.append(f"{_quote_ident('nombre_op')} = %s")
            params.append(rama)

        if not conds:
            return {
                "ok": False,
                "error": (
                    f"En {schema}.{table} no hay columnas nombre_co_claro / nombre_co_atc / nombre_op. "
                    "Revisá CAMINO_GIS_CI_OP_TABLE o el esquema."
                ),
            }

        where_sql = "(" + " OR ".join(conds) + ")"
        out = _rows_to_feature_collection(cur, schema, table, where_sql, tuple(params))
        if out.get("ok") and out.get("geojson"):
            for feat in out["geojson"].get("features") or []:
                if not isinstance(feat, dict):
                    continue
                props = feat.get("properties")
                if not isinstance(props, dict):
                    props = {}
                    feat["properties"] = props
                props["camino_rama"] = rama
        return out


def consultar_cto_coordenadas_desde_sfat(cto: str) -> dict[str, float] | None:
    """Lat/lon de una CTO (FATC) desde la capa de puntos en `cm` (QGIS: `ci_sfat_mfat_bfat`).

    Usa columnas de atributo `latitud` / `longitud` (o sinónimos) y filtra por
    `nombre_cliente`, `nombre_atc` o `nombre_produto`.
    """
    cto = (cto or "").strip()
    if not cto:
        return None

    schema = _env_schema()
    table = _env_sfat_table()

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return None
        cols = set(_list_data_columns(cur, schema, table))

        lat_c = next((c for c in ("latitud", "latitude", "lat") if c in cols), None)
        lon_c = next((c for c in ("longitud", "longitude", "lon") if c in cols), None)
        if not lat_c or not lon_c:
            return None

        name_cols = [c for c in ("nombre_cliente", "nombre_atc", "nombre_produto") if c in cols]
        if not name_cols:
            return None

        wheres = [f"{_quote_ident(c)} = %s" for c in name_cols]
        where_sql = "(" + " OR ".join(wheres) + ")"
        params = tuple(cto for _ in name_cols)

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        sql = (
            f"SELECT {_quote_ident(lat_c)}, {_quote_ident(lon_c)} "
            f"FROM {schema_q}.{table_q} WHERE {where_sql} LIMIT 1"
        )
        try:
            cur.execute(sql, params)
        except Exception:
            logger.debug("consultar_cto_coordenadas_desde_sfat falló para %s", cto, exc_info=True)
            return None
        row = cur.fetchone()

    if not row or row[0] is None or row[1] is None:
        return None
    try:
        return {"lat": float(row[0]), "lon": float(row[1])}
    except (TypeError, ValueError):
        return None
