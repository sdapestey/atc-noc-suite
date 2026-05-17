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
