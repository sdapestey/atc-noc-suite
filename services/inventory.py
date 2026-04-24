"""Consultas de inventario (índice: ID, CTO, rama)."""
import logging
from collections import defaultdict
from datetime import date, datetime
from itertools import groupby

from db import db_cursor
from queries import QUERIES

from altiplano import obtener_potencias_por_cto

from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    calcular_ne,
    nombre_operador,
    region_desde_rama,
)

logger = logging.getLogger(__name__)


def _format_fecha_baja_ref(dt) -> str:
    """Formato legible para timestamp de bajada (naive, como viene de aux)."""
    if dt is None:
        return "—"
    if isinstance(dt, datetime):
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%d/%m/%Y")
        return dt.strftime("%d/%m/%Y %H:%M")
    if isinstance(dt, date):
        return dt.strftime("%d/%m/%Y")
    return str(dt)


def _operador_desde_operatorid_cell(op_raw) -> str:
    """operatorid en aux puede ser bigint o text; mapea con nombre_operador."""
    if op_raw is None or str(op_raw).strip() == "":
        return "—"
    s = str(op_raw).strip()
    try:
        return nombre_operador(int(s))
    except (TypeError, ValueError):
        return nombre_operador(s)


def _fecha_display_desde_textos_aux(
    cancellation_date: str | None,
    reserved_date: str | None,
    provided_date: str | None,
) -> str:
    """
    aux.bajas_de_inventario guarda fechas en columnas text (cancellation_date, etc.).
    Prioridad: cancellation_date → reserved_date → provided_date.
    """
    for raw in (cancellation_date, reserved_date, provided_date):
        if raw is None:
            continue
        t = str(raw).strip()
        if not t:
            continue
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            slice_len = min(len(t), 26)
            try:
                dt = datetime.strptime(t[:slice_len], fmt)
                return _format_fecha_baja_ref(dt)
            except ValueError:
                continue
        try:
            dt = datetime.strptime(t[:10], "%m-%d-%Y")
            return _format_fecha_baja_ref(dt)
        except ValueError:
            return t
    return "—"


_SQL_BAJAS_DE_ORDER = """
ORDER BY
    NULLIF(btrim(cancellation_date), '') DESC NULLS LAST,
    NULLIF(btrim(reserved_date), '') DESC NULLS LAST,
    NULLIF(btrim(provided_date), '') DESC NULLS LAST
LIMIT 1
"""

_BAJAS_AUX_TABLAS = frozenset({"bajas_de_inventario", "bajas_inventario"})


def _fetch_row_aux_bajas_tabla(cur, aid: str, tabla: str):
    """
    Lee aux.bajas_de_inventario o aux.bajas_inventario (mismo esquema esperado).
    Si falta cm_description, reintenta sin ella.
    Retorna (fila o None, tiene_cm_description bool).
    """
    if tabla not in _BAJAS_AUX_TABLAS:
        raise ValueError(f"tabla aux no permitida: {tabla}")
    sql_cm = f"""
                SELECT operatorid, cancellation_date, reserved_date, provided_date,
                       cto, cm_description, object_name
                FROM aux.{tabla}
                WHERE btrim(access_id) = btrim(%s)
                {_SQL_BAJAS_DE_ORDER}
                """
    try:
        cur.execute(sql_cm, (aid,))
        return cur.fetchone(), True
    except Exception:
        logger.warning(
            "%s: consulta con cm_description falló; reintento sin columna",
            tabla,
            exc_info=True,
        )
    sql_plain = f"""
                SELECT operatorid, cancellation_date, reserved_date, provided_date,
                       cto, object_name
                FROM aux.{tabla}
                WHERE btrim(access_id) = btrim(%s)
                {_SQL_BAJAS_DE_ORDER}
                """
    cur.execute(sql_plain, (aid,))
    return cur.fetchone(), False


def _fetch_row_bajas_de_inventario(cur, aid: str):
    """Ver `_fetch_row_aux_bajas_tabla`."""
    return _fetch_row_aux_bajas_tabla(cur, aid, "bajas_de_inventario")


def _fetch_row_bajas_inventario(cur, aid: str):
    """
    Mismo criterio que bajas_de_inventario, sobre aux.bajas_inventario (si existe en BD).
    Si la tabla no existe o el esquema difiere, retorna (None, False).
    """
    try:
        return _fetch_row_aux_bajas_tabla(cur, aid, "bajas_inventario")
    except Exception:
        logger.warning(
            "aux.bajas_inventario: no se pudo consultar (tabla ausente o columnas distintas)",
            exc_info=True,
        )
        return None, False


def consultar_access_id_detalle_desde_bajada_inventario(access_id: str) -> dict | None:
    """
    Detalle tipo índice desde aux.bajada_inventario (primera fuente para búsqueda por AID).
    LEFT JOIN cm.inventory_fat_occupation para path_atc/status; LEFT JOIN altiplano.serial para SN.
    CTO en pantalla: preferir cm_description (FATC típico); si vacío, columna cto.
    """
    aid = (access_id or "").strip()
    if not aid:
        return None
    try:
        with db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    b.operatorid,
                    b.reserved_date,
                    b.provided_date,
                    b.cto,
                    b.cm_description,
                    b.object_name,
                    f.path_atc,
                    f.status,
                    s.serial_number
                FROM aux.bajada_inventario b
                LEFT JOIN cm.inventory_fat_occupation f
                  ON f.access_id::text = btrim(b.access_id)
                LEFT JOIN altiplano.serial s
                  ON s.access_id::text = btrim(b.access_id)
                WHERE btrim(b.access_id) = btrim(%s)
                ORDER BY b.reserved_date DESC NULLS LAST, b.provided_date DESC NULLS LAST
                LIMIT 1
                """,
                (aid,),
            )
            row = cur.fetchone()
    except Exception:
        logger.exception("consultar_access_id_detalle_desde_bajada_inventario")
        return None

    if not row:
        return None

    op_id, res_dt, prov_dt, cto, cm_desc, obj_raw, path_atc, fat_status, serial_number = row
    ont_ui = ""
    if obj_raw:
        ont_ui = str(obj_raw).replace(":1-1", "")
    cm_s = (cm_desc or "").strip() if cm_desc is not None else ""
    cto_display = cm_s if cm_s else ((cto or "").strip() or None)
    if not cto_display:
        cto_display = "—"
    rama_val = (path_atc or "").strip() or None
    sn = (str(serial_number).strip() if serial_number is not None else "") or "—"
    if fat_status is not None and str(fat_status).strip():
        status_disp = str(fat_status).strip()
    else:
        status_disp = "Registro aux.bajada_inventario"

    return {
        "AID": str(aid),
        "OPERADOR": nombre_operador(op_id),
        "Status": status_disp,
        "CTO": cto_display,
        "RAMA": rama_val,
        "ONT": ont_ui or "—",
        "SN": sn,
        "TX": None,
        "RX": None,
        "fuente_detalle": "bajada_inventario",
    }


def _dict_baja_desde_bajas_aux_row(row, has_cm: bool, aid: str, fuente_baja: str) -> dict:
    if has_cm:
        op_raw, canc, res_txt, prov_txt, cto, cm_description, object_name_raw = row
    else:
        op_raw, canc, res_txt, prov_txt, cto, object_name_raw = row
        cm_description = None
    ont_ui = ""
    if object_name_raw:
        ont_ui = str(object_name_raw).replace(":1-1", "")
    cm_desc = (cm_description or "").strip() if cm_description is not None else ""
    cto_ui = cm_desc if cm_desc else ((cto or "").strip() or None)
    return {
        "tipo": "baja",
        "fuente_baja": fuente_baja,
        "AID": aid,
        "OPERADOR": _operador_desde_operatorid_cell(op_raw),
        "fecha_baja_fmt": _fecha_display_desde_textos_aux(canc, res_txt, prov_txt),
        "CTO": cto_ui,
        "ONT": ont_ui or None,
    }


def consultar_access_id_baja_o_ausente(access_id: str) -> dict:
    """
    Tras no hallar fila en aux.bajada_inventario (lo hace el caller del índice):
    1) aux.bajas_de_inventario
    2) aux.bajas_inventario (mismo esquema esperado; si no existe en BD, se ignora)

    Si hay fila: tipo baja, operador/fecha/CTO/ONT y fuente_baja indicando la tabla.
    Si no hay fila en ninguna → tipo no_existe.
    """
    aid = (access_id or "").strip()
    if not aid:
        return {"tipo": "no_existe", "AID": ""}

    try:
        with db_cursor() as cur:
            row_bde, has_cm = _fetch_row_bajas_de_inventario(cur, aid)
            if row_bde:
                return _dict_baja_desde_bajas_aux_row(
                    row_bde, has_cm, aid, "bajas_de_inventario"
                )
            row_bi, has_cm_bi = _fetch_row_bajas_inventario(cur, aid)
            if row_bi:
                return _dict_baja_desde_bajas_aux_row(
                    row_bi, has_cm_bi, aid, "bajas_inventario"
                )
    except Exception:
        logger.exception(
            "consultar_access_id_baja_o_ausente: fallo aux.bajas_de_inventario / bajas_inventario"
        )

    return {"tipo": "no_existe", "AID": aid}


def consultar_access_id_estructura(access_id):
    with db_cursor() as cur:
        cur.execute(QUERIES["access_id_topologia"], (access_id,))
        row = cur.fetchone()

    if not row:
        return None

    aid, status, cto, rama, obj_raw, obj_ui, serial_number, op_id = row
    sn = (str(serial_number).strip() if serial_number else "") or obj_ui

    return {
        "AID": aid,
        "OPERADOR": nombre_operador(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "ONT": obj_ui,
        "SN": sn,
        "TX": None,
        "RX": None,
    }


def consultar_access_id_potencias(access_id):
    base = consultar_access_id_estructura(access_id)
    if not base:
        return {"AID": access_id, "TX": None, "RX": None}

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (base["CTO"],))
        rows = cur.fetchall()

    if not rows:
        return {"AID": access_id, "TX": None, "RX": None}

    ne = calcular_ne(rows[0][4])
    onts = [(str(r[0]), r[4], r[7]) for r in rows if r[4]]
    potencias = obtener_potencias_por_cto(ne, onts)

    tx, rx = potencias.get(str(access_id), (None, None))
    return {"AID": access_id, "TX": tx, "RX": rx}


def consultar_cto_estructura(cto):
    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (cto,))
        rows = cur.fetchall()

    out = []
    for r in rows:
        rama_val = r[3]
        if rama_val:
            reg = region_desde_rama(rama_val)
            principal = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)
        else:
            principal = "—"
        out.append({
            "AID": str(r[0]),
            "OPERADOR": nombre_operador(r[7]),
            "RAMA": rama_val,
            "PRINCIPAL": principal,
            "ONT": r[5],
            "SN": (str(r[6]).strip() if r[6] else "") or r[5],
            "STATUS": r[1],
            "TX": None,
            "RX": None,
        })
    return out


def _potencias_desde_filas_ont_cto(rows):
    """Filas con la misma forma que `onts_por_cto` / `onts_por_rama`."""
    if not rows:
        return []
    ne = calcular_ne(rows[0][4])
    onts = [(str(r[0]), r[4], r[7]) for r in rows if r[4]]
    potencias = obtener_potencias_por_cto(ne, onts)
    return [
        {
            "AID": str(r[0]),
            "TX": potencias.get(str(r[0]), (None, None))[0],
            "RX": potencias.get(str(r[0]), (None, None))[1],
        }
        for r in rows
    ]


def consultar_cto_potencias(cto):
    if cto is None or not str(cto).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (cto,))
        rows = cur.fetchall()

    return _potencias_desde_filas_ont_cto(rows)


def consultar_cto_coordenadas(cto):
    """
    Devuelve coordenadas de la CTO desde aux.bajada_inventario.

    Regla estable: primera fila no nula por access_id ASC.
    """
    if cto is None or not str(cto).strip():
        return None

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(b.splitter_2_lat, b.ont_lat) AS lat,
                COALESCE(b.splitter_2_lon, b.ont_lon) AS lon
            FROM cm.inventory_fat_occupation f
            JOIN aux.bajada_inventario b
              ON b.access_id::text = f.access_id::text
            WHERE f.location_description = %s
              AND f.status = 'IN SERVICE'
              AND (b.cto = %s OR b.cm_description = %s)
              AND COALESCE(b.splitter_2_lat, b.ont_lat) IS NOT NULL
              AND COALESCE(b.splitter_2_lon, b.ont_lon) IS NOT NULL
            ORDER BY f.access_id ASC
            LIMIT 1
            """,
            (str(cto).strip(), str(cto).strip(), str(cto).strip()),
        )
        row = cur.fetchone()

    if not row:
        return None

    lat, lon = row
    return {"lat": float(lat), "lon": float(lon)}


def consultar_rama_estructura(rama):
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.access_id, f.status, f.location_description,
                   s.object_name, REPLACE(s.object_name,':1-1',''),
                   s.serial_number,
                   o.invocator_system
            FROM cm.inventory_fat_occupation f
            JOIN altiplano.serial s ON s.access_id=f.access_id
            JOIN cm.inventory_olt_occupation o ON o.access_id=f.access_id
            WHERE f.path_atc=%s AND f.status='IN SERVICE'
            """,
            (rama,),
        )
        rows = cur.fetchall()

    data = defaultdict(list)
    for r in rows:
        data[r[2]].append({
            "AID": str(r[0]),
            "OPERADOR": nombre_operador(r[6]),
            "ONT": r[4],
            "SN": (str(r[5]).strip() if r[5] else "") or r[4],
            "STATUS": r[1],
            "TX": None,
            "RX": None,
        })
    return data


def consultar_rama_potencias(rama):
    if rama is None or not str(rama).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_rama"], (str(rama).strip(),))
        rows = cur.fetchall()

    if not rows:
        return []

    resultado = []
    for _cto, group in groupby(rows, key=lambda r: r[2]):
        resultado.extend(_potencias_desde_filas_ont_cto(list(group)))
    return resultado
