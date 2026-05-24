"""Consultas de inventario (índice: ID, CTO, rama)."""
import logging
from collections import defaultdict
from typing import Any
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import groupby

from config import get_altiplano_power_cto_workers
from db import db_cursor
from psycopg2.errors import UndefinedColumn
from queries import QUERIES

from altiplano import (
    obtener_alarmas_ont_activas,
    obtener_potencias_ont,
    obtener_potencias_por_cto,
    obtener_telemetry_ont,
)

from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    calcular_ne,
    nombre_operador,
    region_desde_rama,
)

logger = logging.getLogger(__name__)


def _access_lookup_token_ok(aid: str) -> bool:
    """UUID va por otro canal; esto valida Access ID / alias (ALCL…, RES_IP_…, Srvc_loc_…)."""
    if not aid or len(aid) > 256:
        return False
    for c in aid:
        if c.isalnum() or c in "._-":
            continue
        return False
    return True


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


def _tiene_potencia_valida(tx, rx) -> bool:
    """True si TX y RX son lecturas numéricas (no DOWN / vacío)."""
    for v in (tx, rx):
        if v is None:
            return False
        if isinstance(v, (int, float)):
            continue
        s = str(v).strip()
        if not s or s == "-":
            return False
    return True


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
    if s == "0":
        return "—"
    try:
        return nombre_operador(int(s))
    except (TypeError, ValueError):
        return nombre_operador(s)


def _operator_id_efectivo_desde_bajada(b_operatorid, invocator_system) -> Any:
    """Prioriza invocator_system (inventario activo) si operatorid en aux es 0 o vacío."""
    for candidate in (invocator_system, b_operatorid):
        if candidate is None:
            continue
        s = str(candidate).strip()
        if not s or s == "0":
            continue
        try:
            return int(s)
        except (TypeError, ValueError):
            return candidate
    return None


def _object_name_raw_desde_fuentes(*candidates) -> str | None:
    for raw in candidates:
        if raw is None:
            continue
        t = str(raw).strip()
        if t:
            return t
    return None


def _object_name_ui_desde_raw(obj_raw: str | None) -> str:
    if not obj_raw:
        return ""
    return str(obj_raw).replace(":1-1", "")


def _operador_display_valido(op_label: str | None) -> bool:
    op = str(op_label or "").strip()
    return bool(op) and op not in ("0", "—", "-")


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

# None = aún no probado; True/False = esquema con o sin columna cm_description en esa tabla aux.
_AUX_BAJAS_TIENE_CM_DESC: dict[str, bool | None] = {}


def _rollback_aux_bajas_cur(cur: Any, tabla: str) -> None:
    """Tras un error SQL, PostgreSQL aborta la transacción hasta el siguiente rollback."""
    conn = getattr(cur, "connection", None)
    if conn is None:
        return
    try:
        conn.rollback()
    except Exception:
        logger.warning("%s: rollback tras error SQL no aplicado", tabla, exc_info=True)


def _fetch_row_aux_bajas_tabla(cur, aid: str, tabla: str):
    """
    Lee aux.bajas_de_inventario o aux.bajas_inventario (mismo esquema esperado).
    Si falta cm_description, reintenta sin ella y memoriza el esquema para no repetir el fallo.
    Retorna (fila o None, tiene_cm_description bool).
    """
    if tabla not in _BAJAS_AUX_TABLAS:
        raise ValueError(f"tabla aux no permitida: {tabla}")
    sql_cm = f"""
                SELECT access_id, operatorid, cancellation_date, reserved_date, provided_date,
                       cto, cm_description, object_name
                FROM aux.{tabla}
                WHERE LOWER(btrim(access_id::text)) = LOWER(btrim(%s))
                {_SQL_BAJAS_DE_ORDER}
                """
    sql_plain = f"""
                SELECT access_id, operatorid, cancellation_date, reserved_date, provided_date,
                       cto, object_name
                FROM aux.{tabla}
                WHERE LOWER(btrim(access_id::text)) = LOWER(btrim(%s))
                {_SQL_BAJAS_DE_ORDER}
                """

    use_cm = _AUX_BAJAS_TIENE_CM_DESC.get(tabla)
    if use_cm is False:
        cur.execute(sql_plain, (aid,))
        return cur.fetchone(), False
    if use_cm is True:
        cur.execute(sql_cm, (aid,))
        return cur.fetchone(), True

    try:
        cur.execute(sql_cm, (aid,))
        _AUX_BAJAS_TIENE_CM_DESC[tabla] = True
        return cur.fetchone(), True
    except UndefinedColumn as exc:
        if "cm_description" not in str(exc).lower():
            _rollback_aux_bajas_cur(cur, tabla)
            raise
        _rollback_aux_bajas_cur(cur, tabla)
        if _AUX_BAJAS_TIENE_CM_DESC.get(tabla) is not False:
            logger.info(
                "aux.%s: columna cm_description ausente; se consulta sin esa columna.",
                tabla,
            )
        _AUX_BAJAS_TIENE_CM_DESC[tabla] = False
        cur.execute(sql_plain, (aid,))
        return cur.fetchone(), False
    except Exception:
        _rollback_aux_bajas_cur(cur, tabla)
        logger.debug(
            "%s: consulta con cm_description falló; reintento sin columna",
            tabla,
        )
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


def _fetch_row_bajada_inventario_detalle(cur, aid: str):
    """Una fila de aux.bajada_inventario + joins (mismo SELECT que el índice)."""
    cur.execute(
        """
                SELECT
                    b.access_id,
                    b.operatorid,
                    b.reserved_date,
                    b.provided_date,
                    b.cto,
                    b.cm_description,
                    b.object_name,
                    f.path_atc,
                    f.status,
                    s.serial_number,
                    s.object_name,
                    COALESCE(
                        NULLIF(o.invocator_system, 0),
                        b_hist.operatorid,
                        NULLIF(b.operatorid, 0)
                    ) AS invocator_system
                FROM aux.bajada_inventario b
                LEFT JOIN cm.inventory_fat_occupation f
                  ON LOWER(btrim(f.access_id::text)) = LOWER(btrim(b.access_id::text))
                LEFT JOIN altiplano.serial s
                  ON LOWER(btrim(s.access_id::text)) = LOWER(btrim(b.access_id::text))
                LEFT JOIN cm.inventory_olt_occupation o
                  ON LOWER(btrim(o.access_id::text)) = LOWER(btrim(b.access_id::text))
                LEFT JOIN LATERAL (
                    SELECT
                        CASE
                            WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                            THEN trim(b2.operatorid::text)::bigint
                            ELSE NULL
                        END AS operatorid
                    FROM aux.bajada_inventario b2
                    WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(b.access_id::text))
                      AND trim(b2.operatorid::text) ~ '^[0-9]+$'
                      AND trim(b2.operatorid::text) <> '0'
                    ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
                    LIMIT 1
                ) b_hist ON true
                WHERE LOWER(btrim(b.access_id::text)) = LOWER(btrim(%s))
                ORDER BY b.reserved_date DESC NULLS LAST, b.provided_date DESC NULLS LAST
                LIMIT 1
                """,
        (aid,),
    )
    return cur.fetchone()


def _dict_detalle_desde_bajada_inventario_row(row, aid: str) -> dict:
    """Arma el dict de detalle índice a partir de la fila de `_fetch_row_bajada_inventario_detalle`."""
    (
        row_aid,
        op_id,
        res_dt,
        prov_dt,
        cto,
        cm_desc,
        obj_raw,
        path_atc,
        fat_status,
        serial_number,
        serial_object_name,
        invocator_system,
    ) = row
    aid_canon = (str(row_aid).strip() if row_aid is not None else "") or aid
    obj_effective = _object_name_raw_desde_fuentes(serial_object_name, obj_raw)
    ont_ui = _object_name_ui_desde_raw(obj_effective)
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
    op_eff = _operator_id_efectivo_desde_bajada(op_id, invocator_system)

    return {
        "AID": aid_canon,
        "OPERADOR": _operador_desde_operatorid_cell(op_eff),
        "Status": status_disp,
        "CTO": cto_display,
        "RAMA": rama_val,
        "ONT": ont_ui or "—",
        "SN": sn,
        "TX": None,
        "RX": None,
        "fuente_detalle": "bajada_inventario",
    }


def _enrich_detalle_con_inventario_activo(det: dict, aid: str) -> dict:
    """Completa operador/ONT/SN desde inventario FAT cuando aux.bajada_inventario viene incompleto."""
    try:
        fat = consultar_access_id_estructura(aid)
    except Exception:
        logger.exception("_enrich_detalle_con_inventario_activo")
        return det
    if not fat:
        return det
    if not _operador_display_valido(det.get("OPERADOR")):
        fat_op = fat.get("OPERADOR")
        if _operador_display_valido(fat_op):
            det["OPERADOR"] = fat_op
    ont = str(det.get("ONT") or "").strip()
    if ont in ("", "—"):
        det["ONT"] = fat.get("ONT") or det["ONT"]
    sn = str(det.get("SN") or "").strip()
    if sn in ("", "—") and fat.get("SN"):
        det["SN"] = fat["SN"]
    rama = det.get("RAMA")
    if not (rama and str(rama).strip()):
        det["RAMA"] = fat.get("RAMA")
    st = str(det.get("Status") or "").strip()
    if st == "Registro aux.bajada_inventario" and fat.get("Status"):
        det["Status"] = fat["Status"]
    return det


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
            row = _fetch_row_bajada_inventario_detalle(cur, aid)
    except Exception:
        logger.exception("consultar_access_id_detalle_desde_bajada_inventario")
        return None

    if not row:
        return None

    det = _dict_detalle_desde_bajada_inventario_row(row, aid)
    return _enrich_detalle_con_inventario_activo(det, det["AID"])


def _dict_baja_desde_bajas_aux_row(row, has_cm: bool, aid: str, fuente_baja: str) -> dict:
    if has_cm:
        access_canon, op_raw, canc, res_txt, prov_txt, cto, cm_description, object_name_raw = row
    else:
        access_canon, op_raw, canc, res_txt, prov_txt, cto, object_name_raw = row
        cm_description = None
    aid_out = (str(access_canon).strip() if access_canon is not None else "") or aid
    ont_ui = ""
    if object_name_raw:
        ont_ui = str(object_name_raw).replace(":1-1", "")
    cm_desc = (cm_description or "").strip() if cm_description is not None else ""
    cto_ui = cm_desc if cm_desc else ((cto or "").strip() or None)
    return {
        "tipo": "baja",
        "fuente_baja": fuente_baja,
        "AID": aid_out,
        "OPERADOR": _operador_desde_operatorid_cell(op_raw),
        "fecha_baja_fmt": _fecha_display_desde_textos_aux(canc, res_txt, prov_txt),
        "CTO": cto_ui,
        "ONT": ont_ui or None,
    }


def _consultar_access_id_baja_o_ausente_con_cursor(cur, aid: str) -> dict:
    """Misma resolución que ``consultar_access_id_baja_o_ausente`` usando un cursor ya abierto."""
    row_bde, has_cm = _fetch_row_bajas_de_inventario(cur, aid)
    if row_bde:
        return _dict_baja_desde_bajas_aux_row(row_bde, has_cm, aid, "bajas_de_inventario")
    row_bi, has_cm_bi = _fetch_row_bajas_inventario(cur, aid)
    if row_bi:
        return _dict_baja_desde_bajas_aux_row(row_bi, has_cm_bi, aid, "bajas_inventario")
    return {"tipo": "no_existe", "AID": aid}


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
            return _consultar_access_id_baja_o_ausente_con_cursor(cur, aid)
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
        return _consultar_access_id_estructura_con_cursor(cur, access_id)


def _consultar_access_id_estructura_con_cursor(cur, access_id) -> dict | None:
    cur.execute(QUERIES["access_id_topologia"], (access_id,))
    row = cur.fetchone()

    if not row:
        return None

    aid, status, cto, rama, obj_raw, obj_ui, serial_number, op_id = row
    sn = (str(serial_number).strip() if serial_number else "") or obj_ui

    return {
        "AID": aid,
        "OPERADOR": _operador_desde_operatorid_cell(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "ONT": obj_ui,
        "SN": sn,
        "TX": None,
        "RX": None,
    }


def clasificar_access_id_bajada_bajas_fat_cur(cur, access_id: str) -> dict[str, str]:
    """
    Una transacción: bajada_inventario → bajas aux → inventario FAT (misma lógica que el índice).

    Retorna claves: access_id, tabla_aux (aux.bajada_inventario | aux.bajas_* | ninguna),
    bajada_inventario, bajas_tabla, inventario_fat_activo, ubicacion_resumen.
    """
    aid = (access_id or "").strip()
    if not aid:
        return {
            "access_id": "",
            "tabla_aux": "ninguna",
            "bajada_inventario": "no",
            "bajas_tabla": "no",
            "inventario_fat_activo": "no",
            "ubicacion_resumen": "ninguna",
        }

    try:
        row_b = _fetch_row_bajada_inventario_detalle(cur, aid)
    except Exception:
        logger.exception("clasificar_access_id_bajada_bajas_fat_cur: aux.bajada_inventario")
        row_b = None

    en_bajada = row_b is not None
    fuente_bajas = ""
    if not en_bajada:
        try:
            b = _consultar_access_id_baja_o_ausente_con_cursor(cur, aid)
        except Exception:
            logger.exception("clasificar_access_id_bajada_bajas_fat_cur: bajas aux")
            b = {"tipo": "no_existe"}
        if b.get("tipo") == "baja":
            fuente_bajas = str(b.get("fuente_baja") or "")

    try:
        en_fat = _consultar_access_id_estructura_con_cursor(cur, aid) is not None
    except Exception:
        logger.exception("clasificar_access_id_bajada_bajas_fat_cur: access_id_topologia")
        en_fat = False

    if en_bajada:
        ubicacion = "bajada_inventario"
        tabla_aux = "aux.bajada_inventario"
    elif fuente_bajas:
        ubicacion = fuente_bajas
        tabla_aux = f"aux.{fuente_bajas}"
    else:
        ubicacion = "ninguna"
        tabla_aux = "ninguna"

    return {
        "access_id": aid,
        "tabla_aux": tabla_aux,
        "bajada_inventario": "si" if en_bajada else "no",
        "bajas_tabla": fuente_bajas if fuente_bajas else ("-" if en_bajada else "no"),
        "inventario_fat_activo": "si" if en_fat else "no",
        "ubicacion_resumen": ubicacion,
    }


def resolver_target_ont_connection_por_access_id(access_id: str) -> dict:
    """
    Arma el prefijo/target para consultar un intent ``ont-connection`` en el NBI cuando solo se
    conoce el Access ID.

    El RESTCONF de Altiplano indexa por ``target`` (location#VNO#gpon), no por access-id; esta
    función usa inventario ATC (``object_name`` en ``altiplano.serial`` y ``invocator_system``
    en ocupación OLT) para derivar el mismo string que muestra la UI de Altiplano.

    Returns:
        Dict con ``ok`` True y ``device_name_for_query`` listo para ``buscar_intents_*``, u
        ``ok`` False y ``message`` explicando el motivo.
    """
    from altiplano import normalizar_object_name

    aid = (access_id or "").strip()
    if not _access_lookup_token_ok(aid):
        return {
            "ok": False,
            "message": "Identificador de acceso inválido.",
        }

    obj_raw = None
    obj_ui = None
    op_id = None
    status = None
    cto = None
    rama = None

    try:
        with db_cursor() as cur:
            cur.execute(QUERIES["access_id_topologia"], (aid,))
            row = cur.fetchone()
            if row:
                _aid, status, cto, rama, obj_raw, obj_ui, _serial, op_id = row

            # FAT sin fila o sin serial: muchos AID siguen en altiplano.serial / bajada aunque
            # ya no estén en ocupación FAT (estado Not present / borrado en IBN).
            if not obj_raw or not str(obj_raw).strip():
                cur.execute(QUERIES["access_id_serial_y_olt"], (aid,))
                r2 = cur.fetchone()
                if r2 and r2[0] and str(r2[0]).strip():
                    obj_raw = r2[0]
                    obj_ui = r2[1]
                    if op_id is None:
                        op_id = r2[2]

            if not obj_raw or not str(obj_raw).strip():
                cur.execute(QUERIES["access_id_bajada_object"], (aid,))
                r3 = cur.fetchone()
                if r3 and r3[0] and str(r3[0]).strip():
                    obj_raw = r3[0]
                    obj_ui = str(r3[0]).replace(":1-1", "")
                    if op_id is None and r3[1] is not None:
                        op_id = r3[1]

            # Alias no numéricos (prefijo de object_name en serial; mismas columnas que topología).
            if not obj_raw or not str(obj_raw).strip():
                cur.execute(QUERIES["access_id_desde_alias"], (aid,))
                row_alias = cur.fetchone()
                if row_alias:
                    _aid, status, cto, rama, obj_raw, obj_ui, _serial, op_id = row_alias

            if not obj_raw or not str(obj_raw).strip():
                cur.execute(QUERIES["access_id_desde_alias_bajada"], (aid,))
                row_baj = cur.fetchone()
                if row_baj:
                    _aid, status, cto, rama, obj_raw, obj_ui, _serial, op_id = row_baj
    except Exception:
        logger.exception("resolver_target_ont_connection_por_access_id")
        return {
            "ok": False,
            "message": "Error consultando inventario ATC.",
        }

    if not obj_raw or not str(obj_raw).strip():
        return {
            "ok": False,
            "message": "Access ID no encontrado en inventario ATC.",
        }

    normalized = normalizar_object_name(str(obj_raw).strip())
    try:
        vno_int = int(op_id) if op_id is not None else None
    except (TypeError, ValueError):
        vno_int = None

    # Una sola consulta NBI si tenemos slice (invocator); si no, ``buscar`` barrerá VNO.
    device_name_for_query = normalized
    suggested_target = None
    if vno_int is not None:
        suggested_target = f"{normalized}#{vno_int}#gpon"
        device_name_for_query = suggested_target

    return {
        "ok": True,
        "device_name_for_query": device_name_for_query,
        "device_location_prefix": normalized,
        "suggested_target": suggested_target,
        "invocator_system": op_id,
        "object_name_raw": str(obj_raw).strip(),
        "cto": cto,
        "rama": rama,
        "status": status,
        "object_name_ui": obj_ui,
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


def _resolver_object_name_operator_potencias(
    access_id: str, cto: str | None = None
) -> tuple[str | None, int | None]:
    """
    ``object_name`` y ``operator_id`` para Altiplano.

    Inventario activo a veces tiene ``object_name`` NULL; en ese caso usa
    ``aux.bajada_inventario``.
    """
    aid_s = (access_id or "").strip()
    if not aid_s:
        return None, None

    cto_s = (cto or "").strip()
    if cto_s:
        with db_cursor() as cur:
            cur.execute(QUERIES["onts_por_cto"], (cto_s,))
            for r in cur.fetchall():
                if r[0] is None or str(r[0]).strip() != aid_s:
                    continue
                if r[4]:
                    return str(r[4]).strip(), r[7]
                break

    try:
        with db_cursor() as cur:
            row = _fetch_row_bajada_inventario_detalle(cur, aid_s)
    except Exception:
        logger.exception("_resolver_object_name_operator_potencias bajada")
        return None, None
    if row:
        obj = _object_name_raw_desde_fuentes(
            row[10] if len(row) > 10 else None,
            row[6] if len(row) > 6 else None,
        )
        if obj:
            op_eff = _operator_id_efectivo_desde_bajada(
                row[1] if len(row) > 1 else None,
                row[11] if len(row) > 11 else None,
            )
            return obj, op_eff
    return None, None


def cambiar_admin_status_access_id(
    access_id: str,
    operador: str,
    admin_status: str,
    *,
    object_name: str | None = None,
    nbi_username: str | None = None,
    nbi_password: str | None = None,
) -> dict:
    """Lock/unlock admin de la ONT (prender/apagar) resolviendo object_name desde inventario."""
    from altiplano import cambiar_admin_status_ont

    aid = str(access_id or "").strip()
    if not aid:
        return {"ok": False, "message": "Access ID requerido"}

    status = str(admin_status or "").strip().upper()
    if status not in ("LOCKED", "UNLOCKED"):
        return {"ok": False, "message": "admin_status debe ser LOCKED o UNLOCKED"}

    obj = (str(object_name or "").strip() if object_name else "") or None
    op_id = None
    if not obj:
        base = consultar_access_id_estructura(aid)
        cto = base.get("CTO") if base else None
        if base and _sin_potencias_por_status(base.get("Status")):
            return {
                "ok": False,
                "message": "ONT en estado FREE/RESERVED (sin lock admin en Altiplano)",
            }
        obj, op_id = _resolver_object_name_operator_potencias(aid, cto)
    else:
        base = consultar_access_id_estructura(aid)
        if base:
            _, op_id = _resolver_object_name_operator_potencias(aid, base.get("CTO"))
        else:
            with db_cursor() as cur:
                row = _fetch_row_bajada_inventario_detalle(cur, aid)
            if row:
                op_id = row[1]

    if not obj:
        return {"ok": False, "message": "No se encontró object_name para el Access ID"}

    return cambiar_admin_status_ont(
        aid,
        obj,
        operador,
        status,
        nbi_username=nbi_username,
        nbi_password=nbi_password,
    )


def cambiar_pon_admin_access_id(
    access_id: str,
    operador: str,
    admin_status: str,
    *,
    object_name: str | None = None,
    nbi_username: str | None = None,
    nbi_password: str | None = None,
) -> dict:
    """Lock/unlock ChannelPartition PON (bajar/subir puerto) vía EMA INP."""
    from altiplano import cambiar_admin_status_pon

    aid = str(access_id or "").strip()
    if not aid:
        return {"ok": False, "message": "Access ID requerido"}

    status = str(admin_status or "").strip().upper()
    if status not in ("LOCKED", "UNLOCKED"):
        return {"ok": False, "message": "admin_status debe ser LOCKED o UNLOCKED"}

    obj = (str(object_name or "").strip() if object_name else "") or None
    if not obj:
        base = consultar_access_id_estructura(aid)
        cto = base.get("CTO") if base else None
        if base and _sin_potencias_por_status(base.get("Status")):
            return {
                "ok": False,
                "message": "ONT en estado FREE/RESERVED (sin PON en Altiplano)",
            }
        obj, _op_id = _resolver_object_name_operator_potencias(aid, cto)

    if not obj:
        return {"ok": False, "message": "No se encontró object_name para el Access ID"}

    return cambiar_admin_status_pon(
        aid,
        obj,
        operador,
        status,
        nbi_username=nbi_username,
        nbi_password=nbi_password,
    )


def consultar_access_id_potencias(access_id):
    """Consulta TX/RX y SN (Expected Serial Number en Altiplano) de un Access ID puntual.

    Flujo:
    1) Resuelve AID (inventario activo o solo aux.bajada_inventario).
    2) Obtiene ``object_name`` (inventario o bajada si en activo viene NULL).
    3) Consulta Altiplano (RESTCONF + API EMA / AC INP como la GUI).

    Args:
        access_id: Access ID a consultar.

    Returns:
        Dict con `AID`, `TX`, `RX` y `SN` (Expected Serial Number vía EMA si está disponible).
    """
    aid_in = str(access_id or "").strip()
    base = consultar_access_id_estructura(access_id)
    if base:
        aid_canon = str(base["AID"]).strip()
        if _sin_potencias_por_status(base.get("Status")):
            return {
                "AID": aid_canon,
                "TX": None,
                "RX": None,
                "SN": None,
                "ALARMAS": [],
                "alarmas_label": None,
                "NV_STATUS": None,
            }
        cto = base.get("CTO")
    else:
        aid_canon = aid_in
        cto = None

    obj, op_id = _resolver_object_name_operator_potencias(aid_canon, cto)
    if not obj or op_id is None:
        return {
            "AID": aid_canon or access_id,
            "TX": None,
            "RX": None,
            "SN": None,
            "ALARMAS": [],
            "alarmas_label": None,
            "NV_STATUS": None,
        }

    telem = obtener_telemetry_ont(aid_canon, obj, op_id)
    tx = telem.get("tx")
    rx = telem.get("rx")
    out = {
        "AID": aid_canon,
        "TX": tx,
        "RX": rx,
        "SN": telem.get("sn"),
    }
    out["ALARMAS"] = obtener_alarmas_ont_activas(aid_canon, obj, op_id)
    if out["ALARMAS"]:
        out["alarmas_label"] = None
    elif _tiene_potencia_valida(tx, rx):
        out["alarmas_label"] = "Sin Alarmas"
    else:
        out["alarmas_label"] = None
    n_alarms = 0
    if out.get("alarmas_label") != "Sin Alarmas":
        al = out.get("ALARMAS")
        n_alarms = len(al) if isinstance(al, list) else 0
    health = telem.get("health") or None
    oper = telem.get("oper") or None
    if not health and str(oper or "").strip().upper() == "UP":
        health = "Healthy"
    from altiplano import (
        _channel_partition_name_from_object_name,
        _pon_index_from_object_name,
    )

    pon_idx = telem.get("pon_index") or _pon_index_from_object_name(obj)
    cpart = telem.get("channel_partition") or _channel_partition_name_from_object_name(
        obj
    )
    out["NV_STATUS"] = {
        "health": health,
        "health_ts": telem.get("health_ts") or None,
        "oper": oper,
        "admin": telem.get("admin") or None,
        "pon_admin": telem.get("pon_admin") or None,
        "pon_index": pon_idx,
        "channel_partition": cpart,
        "alarms_active": n_alarms,
    }
    if op_id is not None:
        op_label = _operador_desde_operatorid_cell(op_id)
        if _operador_display_valido(op_label):
            out["OPERADOR"] = op_label
    return out


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


def _potencias_desde_grupos_cto_paralelo(rows) -> list[dict]:
    """Agrupa filas por CTO y consulta Altiplano en paralelo (varios CTO por RAMA)."""
    if not rows:
        return []
    grupos = [list(g) for _, g in groupby(rows, key=lambda r: r[2])]
    if len(grupos) <= 1:
        return _potencias_desde_filas_ont_cto(grupos[0]) if grupos else []

    max_workers = min(len(grupos), get_altiplano_power_cto_workers())
    resultado: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_potencias_desde_filas_ont_cto, grp) for grp in grupos
        ]
        for fut in as_completed(futures):
            try:
                resultado.extend(fut.result())
            except Exception:
                logger.exception("potencias paralelo por CTO")
    return resultado


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


def consultar_cto_potencias_cached(cto):
    """Potencias CTO con TTL (dashboards); consultas en vivo sin caché usan ``consultar_cto_potencias``."""
    from config import get_dashboard_rama_power_cache_seconds

    from .dashboard_cache import get_cached_cto_potencias

    cto_norm = str(cto or "").strip()
    if not cto_norm:
        return []
    return get_cached_cto_potencias(
        get_dashboard_rama_power_cache_seconds(),
        cto_norm,
        lambda: consultar_cto_potencias(cto_norm),
    )


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


def consultar_cto_coordenadas_batch(ctos: list[str]) -> dict[str, dict]:
    """Coordenadas de varias CTO en una consulta (misma regla que ``consultar_cto_coordenadas``)."""
    cleaned = sorted({str(c).strip() for c in (ctos or []) if c and str(c).strip()})
    if not cleaned:
        return {}
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (f.location_description)
                f.location_description AS cto,
                COALESCE(b.splitter_2_lat, b.ont_lat) AS lat,
                COALESCE(b.splitter_2_lon, b.ont_lon) AS lon
            FROM cm.inventory_fat_occupation f
            JOIN aux.bajada_inventario b
              ON b.access_id::text = f.access_id::text
            WHERE f.location_description = ANY(%s)
              AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
              AND (b.cto = f.location_description OR b.cm_description = f.location_description)
              AND COALESCE(b.splitter_2_lat, b.ont_lat) IS NOT NULL
              AND COALESCE(b.splitter_2_lon, b.ont_lon) IS NOT NULL
            ORDER BY f.location_description, f.access_id ASC
            """,
            (cleaned,),
        )
        rows = cur.fetchall()
    out: dict[str, dict] = {}
    for cto, lat, lon in rows:
        if cto is None or lat is None or lon is None:
            continue
        out[str(cto)] = {"lat": float(lat), "lon": float(lon)}
    return out


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
                   COALESCE(o.invocator_system, b_aid.operatorid)
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

    return _potencias_desde_grupos_cto_paralelo(rows)


def _ont_key_desde_fila_inventario(row) -> str:
    obj_raw = row[4]
    if not obj_raw:
        return ""
    s = str(obj_raw).strip()
    if ":1-1" in s:
        s = s.split(":1-1", 1)[-1]
    parts = s.split("-")
    return parts[-1].strip() if parts else ""


def _altiplano_potencias_por_ont_desde_filas_cto(rows) -> list[dict]:
    """Una CTO: Altiplano en paralelo por ONT (`obtener_potencias_por_cto`)."""
    if not rows:
        return []
    cto_ref = _cto_ref_desde_filas_ont(rows)
    ne = _ne_para_potencias_desde_filas_ont(rows)
    potencias: dict[str, tuple] = {}
    if ne:
        onts = [
            (str(r[0]), r[4], r[7])
            for r in rows
            if r[0] is not None and r[4] and not _sin_potencias_por_status(r[1])
        ]
        if onts:
            potencias = obtener_potencias_por_cto(ne, onts)
    out: list[dict] = []
    for idx, r in enumerate(rows):
        aid_key = _aid_clave_fila(r[0], idx, cto_ref)
        raw_id = r[0]
        ont_key = _ont_key_desde_fila_inventario(r)
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


def _altiplano_potencias_grupos_cto_paralelo(rows) -> list[dict]:
    """Varias CTO en la misma RAMA: consulta Altiplano en paralelo (como `consultar_rama_potencias`)."""
    if not rows:
        return []
    grupos = [list(g) for _, g in groupby(rows, key=lambda r: r[2])]
    if len(grupos) <= 1:
        return _altiplano_potencias_por_ont_desde_filas_cto(grupos[0]) if grupos else []

    max_workers = min(len(grupos), get_altiplano_power_cto_workers())
    resultado: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_altiplano_potencias_por_ont_desde_filas_cto, grp) for grp in grupos
        ]
        for fut in as_completed(futures):
            try:
                resultado.extend(fut.result())
            except Exception:
                logger.exception("historico altiplano paralelo por CTO")
    return resultado


def consultar_rama_potencias_altiplano_por_ont(rama: str) -> list[dict]:
    """TX/RX en vivo vía Altiplano, misma agrupación por CTO que `consultar_rama_potencias`.

    Varias CTO en la RAMA se consultan en paralelo; dentro de cada CTO las ONT van en
    paralelo (`obtener_potencias_por_cto`). Sin target en
    `_ALTIPLANO_POWER_TARGETS_BY_OPERATOR_ID`, la ONT queda con `rx_dbm` / `tx_dbm` en null.
    """
    if rama is None or not str(rama).strip():
        return []

    with db_cursor() as cur:
        cur.execute(QUERIES["onts_por_rama"], (str(rama).strip(),))
        rows = cur.fetchall()

    return _altiplano_potencias_grupos_cto_paralelo(rows)
