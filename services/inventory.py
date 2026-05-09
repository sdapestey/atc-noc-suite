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

# Inventario CM: sin lectura Altiplano para estos estados de puerto FAT.
_SIN_POTENCIAS_STATUS = frozenset({"FREE", "RESERVED"})

_PARTIDO_DISPLAY_MAP = {
    "BA SAFE": "BA San Fernando",
    "BA ESCO": "BA Escobar",
    "BA SISI": "BA San Isidro",
    "BA VILO": "BA Vicente Lopez",
    "BA TIGR": "BA Tigre",
    "BA MORO": "BA Moreno",
    "BA MORE": "BA Moreno",
    # Se deja por completitud aunque hoy no aparezca en la muestra.
    "BA SMAR": "BA San Martin",
    "BA SAMA": "BA San Martin",
    "BA SANM": "BA San Martin",
}


def _sin_potencias_por_status(status) -> bool:
    return str(status or "").strip().upper() in _SIN_POTENCIAS_STATUS


def _cto_ref_desde_filas_ont(rows) -> str:
    if not rows:
        return ""
    return str(rows[0][2] or "").strip()


def _aid_clave_fila(access_id, idx: int, cto_ref: str) -> str:
    """Clave estable para DOM/API cuando `access_id` puede ser NULL (puertos FREE)."""
    if access_id is not None:
        return str(access_id)
    safe = "".join(
        ch if ch.isalnum() or ch in "-_" else "_"
        for ch in (cto_ref or "cto")
    )
    return f"nf-{safe}-{idx}"


def _ne_para_potencias_desde_filas_ont(rows) -> str:
    """Primer object_name Altiplano válido para derivar NE (potencias por CTO/rama)."""
    for r in rows:
        if _sin_potencias_por_status(r[1]):
            continue
        raw = r[4]
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or "-" not in s:
            continue
        try:
            return calcular_ne(s)
        except IndexError:
            continue
    return ""


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
    """Obtiene topología básica de un Access ID desde inventario activo.

    Args:
        access_id: Identificador numérico del servicio.

    Returns:
        Diccionario con AID, operador, estado, CTO, rama, ONT y SN.
        Retorna `None` cuando el AID no existe en inventario activo.
    """
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


def consultar_access_id_desde_alias(alias: str) -> dict | None:
    """
    Busca un acceso por alias no numérico (ej: Srvc_loc_*, RES_MT_*), case-insensitive.
    Retorna el mismo shape que consultar_access_id_estructura para reutilizar render de índice.
    """
    raw = (alias or "").strip()
    if not raw:
        return None

    # Fuente principal: alias en altiplano.serial.object_name.
    with db_cursor() as cur:
        cur.execute(QUERIES["access_id_desde_alias"], (raw,))
        row = cur.fetchone()

    # Fallback 1: alias existe directamente como access_id en aux.bajada_inventario.
    # Este caso aparece en algunos registros de Metrotel/IPLAN.
    if not row:
        detalle_bajada = consultar_access_id_detalle_desde_bajada_inventario(raw)
        if detalle_bajada:
            detalle_bajada["fuente_detalle"] = "alias_bajada_inventario"
            return detalle_bajada

    # Fallback 2: alias presente en bajada_inventario pero mapeable a inventario activo.
    if not row:
        with db_cursor() as cur:
            cur.execute(QUERIES["access_id_desde_alias_bajada"], (raw,))
            row = cur.fetchone()

    if not row:
        return None

    aid, status, cto, rama, obj_raw, obj_ui, serial_number, op_id = row
    sn = (str(serial_number).strip() if serial_number else "") or obj_ui
    return {
        "AID": str(aid),
        "OPERADOR": nombre_operador(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "ONT": obj_ui or "—",
        "SN": sn or "—",
        "TX": None,
        "RX": None,
        "fuente_detalle": "alias_inventario",
    }


def consultar_access_id_potencias(access_id):
    """Consulta TX/RX de un Access ID puntual.

    Flujo:
    1) Resuelve la estructura del AID.
    2) Busca ONT de la CTO para conocer NE/operador.
    3) Consulta Altiplano y devuelve solo la potencia del AID requerido.

    Args:
        access_id: Access ID a consultar.

    Returns:
        Dict con `AID`, `TX` y `RX` (valores numéricos o `None`).
    """
    base = consultar_access_id_estructura(access_id)
    if not base:
        return {"AID": access_id, "TX": None, "RX": None}

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (base["CTO"],))
        rows = cur.fetchall()

    if not rows:
        return {"AID": access_id, "TX": None, "RX": None}

    aid_key = str(access_id).strip()
    for r in rows:
        if str(r[0]).strip() == aid_key and _sin_potencias_por_status(r[1]):
            return {"AID": access_id, "TX": None, "RX": None}

    ne = _ne_para_potencias_desde_filas_ont(rows)
    if not ne:
        return {"AID": access_id, "TX": None, "RX": None}

    onts = [
        (str(r[0]), r[4], r[7])
        for r in rows
        if r[0] is not None and r[4] and not _sin_potencias_por_status(r[1])
    ]
    if not onts:
        return {"AID": access_id, "TX": None, "RX": None}

    potencias = obtener_potencias_por_cto(ne, onts)

    tx, rx = potencias.get(str(access_id).strip(), (None, None))
    return {"AID": access_id, "TX": tx, "RX": rx}


def consultar_cto_estructura(cto):
    """Devuelve inventario de una CTO (estados IN SERVICE, RESERVED y FREE).

    Args:
        cto: Identificador FATC de la CTO.

    Returns:
        Lista de ONTs con metadatos de operador, rama, SN y estado.
    """
    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_cto"], (cto,))
        rows = cur.fetchall()

    cto_ref = str(cto or "").strip()
    out = []
    for idx, r in enumerate(rows):
        rama_val = r[3]
        if rama_val:
            reg = region_desde_rama(rama_val)
            principal = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)
        else:
            principal = "—"
        st_u = str(r[1] or "").strip().upper()
        aid_key = _aid_clave_fila(r[0], idx, cto_ref)
        out.append({
            "AID": aid_key,
            "OPERADOR": "-" if st_u == "FREE" else nombre_operador(r[7]),
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
    cto_ref = _cto_ref_desde_filas_ont(rows)
    ne = _ne_para_potencias_desde_filas_ont(rows)
    potencias = {}
    if ne:
        onts = [
            (str(r[0]), r[4], r[7])
            for r in rows
            if r[0] is not None and r[4] and not _sin_potencias_por_status(r[1])
        ]
        if onts:
            potencias = obtener_potencias_por_cto(ne, onts)
    out = []
    for idx, r in enumerate(rows):
        aid_key = _aid_clave_fila(r[0], idx, cto_ref)
        raw_id = r[0]
        if _sin_potencias_por_status(r[1]):
            tx = rx = None
        elif raw_id is not None:
            tx, rx = potencias.get(str(raw_id), (None, None))
        else:
            tx = rx = None
        out.append({"AID": aid_key, "TX": tx, "RX": rx})
    return out


def consultar_cto_potencias(cto):
    """Devuelve TX/RX de todas las ONT de una CTO.

    Args:
        cto: CTO FATC.

    Returns:
        Lista de dicts `{AID, TX, RX}`. Lista vacía si no hay datos.
    """
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
              AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
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


def consultar_cto_direccion_postal(cto: str) -> str | None:
    """Devuelve dirección postal estimada de la CTO desde `cm.ci_sfat_mfat_bfat`.

    Prioriza match por `nombre_cliente` (más consistente con `location_description`)
    y luego `nombre_atc`.
    """
    cto_norm = (cto or "").strip()
    if not cto_norm:
        return None

    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                NULLIF(btrim(s.direccion), '') AS direccion,
                NULLIF(btrim(s.partido_despliegue), '') AS partido,
                CASE
                    WHEN s.nombre_cliente = %s THEN 0
                    WHEN s.nombre_atc = %s THEN 1
                    ELSE 9
                END AS prio
            FROM cm.ci_sfat_mfat_bfat s
            WHERE (s.nombre_cliente = %s OR s.nombre_atc = %s)
              AND NULLIF(btrim(s.direccion), '') IS NOT NULL
            ORDER BY prio ASC
            LIMIT 1
            """,
            (cto_norm, cto_norm, cto_norm, cto_norm),
        )
        row = cur.fetchone()

    if not row:
        return None
    direccion, partido, _prio = row
    if not direccion:
        return None
    dir_norm = " ".join(str(direccion).replace(",", " ").split())

    partido_norm = str(partido or "").strip()
    if partido_norm:
        partido_norm = _PARTIDO_DISPLAY_MAP.get(partido_norm.upper(), partido_norm)
        return f"{dir_norm} ({partido_norm})"
    return dir_norm


def consultar_rama_estructura(rama):
    """ONTs por CTO para una rama (IN SERVICE, RESERVED y FREE).

    Args:
        rama: Identificador RATC.

    Returns:
        `defaultdict(list)` donde cada clave es una CTO y el valor
        es una lista de ONTs con sus metadatos.
    """
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT f.access_id, f.status, f.location_description,
                   s.object_name, REPLACE(COALESCE(s.object_name, ''), ':1-1', ''),
                   s.serial_number,
                   o.invocator_system
            FROM cm.inventory_fat_occupation f
            LEFT JOIN altiplano.serial s ON s.access_id = f.access_id
            LEFT JOIN cm.inventory_olt_occupation o ON o.access_id = f.access_id
            WHERE f.path_atc = %s
              AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
            """,
            (rama,),
        )
        rows = cur.fetchall()

    rama_norm = str(rama or "").strip()
    reg = region_desde_rama(rama_norm)
    principal_sitio = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)

    por_cto = defaultdict(list)
    for r in rows:
        por_cto[r[2]].append(r)

    data = defaultdict(list)
    for cto_key, lst in por_cto.items():
        cto_ref = str(cto_key or "").strip()
        for idx, r in enumerate(lst):
            st_u = str(r[1] or "").strip().upper()
            aid_key = _aid_clave_fila(r[0], idx, cto_ref)
            data[cto_key].append({
                "AID": aid_key,
                "OPERADOR": "-" if st_u == "FREE" else nombre_operador(r[6]),
                "PRINCIPAL": principal_sitio,
                "RAMA": rama_norm,
                "ONT": r[4],
                "SN": (str(r[5]).strip() if r[5] else "") or r[4],
                "STATUS": r[1],
                "TX": None,
                "RX": None,
            })
    return data


def consultar_rama_potencias(rama):
    """Devuelve TX/RX de todas las ONT de una rama.

    Args:
        rama: Identificador RATC.

    Returns:
        Lista de registros `{AID, TX, RX}` consolidada por CTO.
    """
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


def consultar_rama_potencias_altiplano_por_ont(rama: str) -> list[dict]:
    """TX/RX en vivo vía Altiplano, misma agrupación por CTO que `consultar_rama_potencias`.

    Por CTO se llama a `obtener_potencias_por_cto` (worker pool en altiplano).
    Si `operator_id` no tiene target en el mapa de Altiplano (`_ALTIPLANO_POWER_TARGETS_BY_OPERATOR_ID` en `altiplano.py`),
    esa ONT no obtiene lectura y se devuelve `rx_dbm` / `tx_dbm` en null.
    """
    if rama is None or not str(rama).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_rama"], (str(rama).strip(),))
        rows = cur.fetchall()

    out: list[dict] = []
    for _cto, group in groupby(rows, key=lambda r: r[2]):
        grp = list(group)
        ne = _ne_para_potencias_desde_filas_ont(grp)
        onts = [
            (str(r[0]), r[4], r[7])
            for r in grp
            if r[0] is not None and r[4] and not _sin_potencias_por_status(r[1])
        ]
        potencias = obtener_potencias_por_cto(ne, onts) if ne and onts else {}
        cto_ref = str(grp[0][2] or "").strip()
        for idx, r in enumerate(grp):
            aid_key = _aid_clave_fila(r[0], idx, cto_ref)
            raw_id = r[0]
            obj_raw = r[4]
            ont_key = str(obj_raw).split("-")[-1] if obj_raw else ""
            if _sin_potencias_por_status(r[1]):
                tx, rx = None, None
            elif raw_id is not None:
                tx, rx = potencias.get(str(raw_id), (None, None))
            else:
                tx, rx = None, None
            out.append({
                "aid": aid_key,
                "ont_key": ont_key,
                "rx_dbm": None if rx is None else float(rx),
                "tx_dbm": None if tx is None else float(tx),
            })
    return out
