"""Consultas de inventario (índice: ID, CTO, rama)."""
import logging
from collections import defaultdict
from typing import Any
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import get_altiplano_power_cto_workers
from db import db_cursor
from psycopg2.errors import UndefinedColumn
from queries import QUERIES

from altiplano import (
    obtener_alarmas_ont_activas,
    obtener_potencias_por_cto,
    obtener_telemetry_ont,
    obtener_ultima_alarma_ont,
    ultima_alarma_ont_payload,
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


def _is_nfc_tag_token(token: str) -> bool:
    """TAG NFC de CTO: hexadecimal (10–16 caracteres), sin espacios ni guiones."""
    s = (token or "").strip()
    if len(s) < 10 or len(s) > 16 or s.isdigit():
        return False
    for c in s:
        if c in "0123456789abcdefABCDEF":
            continue
        return False
    return True


# Inventario CM: sin lectura Altiplano para estos estados de puerto FAT.
# Nota: ``RESERVED`` puede tener PON asignada; para consultas puntuales por
# Access ID se permiten potencias/alarmas incluso en ese estado. El set global
# se mantiene solo para FREE y los callers que necesiten tratar RESERVED como
# "sin lectura" deben manejarlo de forma explícita.
_SIN_POTENCIAS_STATUS = frozenset({"FREE"})

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


def _nfc_tag_display(val) -> str | None:
    """TAG NFC de inventario FAT (cm.inventory_fat_occupation.nfc_tag_id)."""
    if val is None:
        return None
    s = str(val).strip()
    return s or None


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
                    f.nfc_tag_id,
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
        nfc_tag_id,
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
        "TAG_NFC": _nfc_tag_display(nfc_tag_id),
        "ONT": ont_ui or "—",
        "SN": sn,
        "TX": None,
        "RX": None,
        "fuente_detalle": "bajada_inventario",
    }


def _fetch_inp_hit_por_access_id(aid: str) -> dict | None:
    """Intent ont-connection en INP para un Access ID (device + target #VNO#gpon)."""
    aid_s = (aid or "").strip()
    if not aid_s:
        return None
    try:
        from altiplano import resolver_ont_connection_inp_por_access_id

        return resolver_ont_connection_inp_por_access_id(aid_s)
    except Exception:
        logger.exception("_fetch_inp_hit_por_access_id aid=%s", aid_s)
        return None


def _altiplano_vno_target(inp_hit: dict | None) -> str | None:
    if not inp_hit:
        return None
    tgt = (inp_hit.get("target") or inp_hit.get("location_slice_pon") or "").strip()
    return tgt if tgt and "#" in tgt else None


def _hsi_from_tasa_match_row(row: dict) -> dict | None:
    """HSI desde fila NBI normalizada (``tasa_hsi``) o ``intent-specific-data`` crudo."""
    if not isinstance(row, dict):
        return None
    hsi = row.get("tasa_hsi")
    if isinstance(hsi, dict) and hsi:
        return dict(hsi)
    from altiplano import _hsi_from_ibn_row

    parsed = _hsi_from_ibn_row(row)
    return parsed or None


def _fetch_tasa_composite_detail(
    operator: str | None,
    device_prefix: str | None,
    access_id: str | None = None,
) -> dict | None:
    """Target ``tasa-composite`` y perfiles HSI en el NBI TASA."""
    op = str(operator or "").strip().upper()
    prefix = str(device_prefix or "").strip()
    if op != "TASA" or not prefix:
        return None
    try:
        from altiplano import (
            _target_head,
            buscar_ont_connection_operador_por_target_exact,
            fetch_tasa_composite_hsi_nbi,
        )

        head = _target_head(prefix) or prefix
        search = buscar_ont_connection_operador_por_target_exact(
            op,
            head,
            access_id=(access_id or "").strip() or None,
        )
        if not search.get("ok"):
            return None
        hits: list[dict] = []
        seen: set[str] = set()
        for row in search.get("matches") or []:
            if not isinstance(row, dict):
                continue
            it = str(row.get("intent_type") or row.get("intent-type") or "").strip().lower()
            if it != "tasa-composite":
                continue
            tgt = (row.get("target") or row.get("location_slice_pon") or "").strip()
            if not tgt or tgt in seen:
                continue
            seen.add(tgt)
            hsi = _hsi_from_tasa_match_row(row)
            if not hsi:
                hsi = fetch_tasa_composite_hsi_nbi(op, tgt)
            hits.append({"target": tgt, "tasa_hsi": hsi})
        if not hits:
            return None
        if len(hits) == 1:
            out: dict = {"target": hits[0]["target"]}
            if hits[0].get("tasa_hsi"):
                out["tasa_hsi"] = hits[0]["tasa_hsi"]
            return out
        return {
            "target": " · ".join(h["target"] for h in hits),
            "multiple": True,
        }
    except Exception:
        logger.exception("_fetch_tasa_composite_detail op=%s prefix=%s", op, prefix)
        return None


def _fetch_tasa_composite_target(
    operator: str | None,
    device_prefix: str | None,
    access_id: str | None = None,
) -> str | None:
    detail = _fetch_tasa_composite_detail(operator, device_prefix, access_id)
    return detail.get("target") if detail else None


def _operator_label_potencias(
    op_id: int | str | None, base: dict | None
) -> str | None:
    if op_id is not None:
        label = _operador_desde_operatorid_cell(op_id)
        if _operador_display_valido(label):
            return label
    if base and _operador_display_valido(base.get("OPERADOR")):
        return str(base.get("OPERADOR") or "").strip()
    return None


def _altiplano_vno_payload(
    inp_hit: dict | None,
    *,
    operator: str | None = None,
    access_id: str | None = None,
) -> dict:
    vno = _altiplano_vno_target(inp_hit)
    device = ""
    if inp_hit:
        device = str(
            inp_hit.get("inp_device_name")
            or inp_hit.get("object_name_ui")
            or inp_hit.get("object_name")
            or ""
        ).strip()
    tasa_detail = _fetch_tasa_composite_detail(operator, device or vno, access_id)
    tasa = tasa_detail.get("target") if tasa_detail else None
    out = {
        "ALTIPLANO_VNO": vno,
        "ALTIPLANO_TASA_COMPOSITE": tasa,
    }
    if tasa_detail and tasa_detail.get("tasa_hsi"):
        out["ALTIPLANO_TASA_HSI"] = tasa_detail["tasa_hsi"]
    if tasa_detail and tasa_detail.get("multiple"):
        out["ALTIPLANO_TASA_COMPOSITE_MULTIPLE"] = True
    return out


def _live_altiplano_device_y_expected_sn(
    aid: str,
    *,
    object_name_pg: str | None = None,
    operator_id_pg: int | None = None,
    inp_hit: dict | None = None,
) -> tuple[str | None, str | None, int | None]:
    """
    Device name (INP ``search-intents``) y Expected Serial en vivo.

    Returns:
        ``(object_name, sn, operator_id)``; cada campo puede ser ``None`` si Altiplano no responde.
    """
    aid_s = (aid or "").strip()
    if not aid_s:
        return None, None, None
    try:
        from altiplano import (
            _fetch_expected_sn_live,
            _ne_from_object_name_raw,
            resolver_ont_connection_inp_por_access_id,
        )

        if inp_hit is None:
            inp_hit = resolver_ont_connection_inp_por_access_id(aid_s)
        op_id = operator_id_pg
        if inp_hit:
            obj = (
                inp_hit.get("object_name_ui") or inp_hit.get("object_name") or ""
            ).strip()
            op_inp = inp_hit.get("operator_id")
            if op_inp is not None:
                op_id = op_inp
            if not obj:
                return None, None, op_id
            ne = _ne_from_object_name_raw(obj)
            sn = _fetch_expected_sn_live(aid_s, obj, op_id, ne=ne) if ne else None
            return obj, sn, op_id

        obj_pg = (str(object_name_pg).strip() if object_name_pg else "") or ""
        if not obj_pg:
            return None, None, op_id
        ne = _ne_from_object_name_raw(obj_pg)
        sn = _fetch_expected_sn_live(aid_s, obj_pg, op_id, ne=ne) if ne else None
        return None, sn, op_id
    except Exception:
        logger.exception("_live_altiplano_device_y_expected_sn aid=%s", aid_s)
        return None, None, operator_id_pg


def _priorizar_altiplano_en_detalle(det: dict) -> dict:
    """ONT y SN en vivo (Altiplano); si no hay lectura, conserva valores Postgres del detalle."""
    if not det:
        return det
    st = str(det.get("Status") or "").strip().upper()
    if st in _SIN_POTENCIAS_STATUS:
        return det
    aid = str(det.get("AID") or "").strip()
    if not aid:
        return det
    obj_pg = str(det.get("ONT") or "").strip()
    if obj_pg in ("", "—"):
        obj_pg = ""
    obj_live, sn_live, _op = _live_altiplano_device_y_expected_sn(aid, object_name_pg=obj_pg or None)
    if obj_live:
        det["ONT"] = obj_live
    if sn_live:
        det["SN"] = sn_live
    return det


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
    if not det.get("TAG_NFC") and fat.get("TAG_NFC"):
        det["TAG_NFC"] = fat["TAG_NFC"]
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
    det = _enrich_detalle_con_inventario_activo(det, det["AID"])
    return _priorizar_altiplano_en_detalle(det)


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

    aid, status, cto, rama, obj_raw, obj_ui, serial_number, op_id, nfc_tag_id = row
    sn = (str(serial_number).strip() if serial_number else "") or obj_ui

    return {
        "AID": aid,
        "OPERADOR": _operador_desde_operatorid_cell(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "TAG_NFC": _nfc_tag_display(nfc_tag_id),
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

    aid, status, cto, rama, obj_raw, obj_ui, serial_number, op_id, nfc_tag_id = row
    sn = (str(serial_number).strip() if serial_number else "") or obj_ui
    return {
        "AID": str(aid),
        "OPERADOR": nombre_operador(op_id),
        "Status": status,
        "CTO": cto,
        "RAMA": rama,
        "TAG_NFC": _nfc_tag_display(nfc_tag_id),
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
    if not obj:
        base = consultar_access_id_estructura(aid)
        cto = base.get("CTO") if base else None
        if base and _sin_potencias_por_status(base.get("Status")):
            return {
                "ok": False,
                "message": "ONT en estado FREE/RESERVED (sin lock admin en Altiplano)",
            }
        obj, _ = _resolver_object_name_operator_potencias(aid, cto)

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


def _ont_normalize_for_compare(name: str) -> str:
    """Forma canónica para comparar ONT Postgres vs Altiplano."""
    from altiplano import normalizar_object_name

    s = normalizar_object_name((name or "").strip())
    if ":1-1" in s:
        s = s.replace(":1-1", "")
    return s.strip()


def _ont_postgres_para_compare(
    aid_canon: str, cto: str | None, base: dict | None, obj_pg: str | None = None
) -> str:
    """Device name según inventario ATC (Postgres / bajada)."""
    if obj_pg and str(obj_pg).strip():
        return _ont_normalize_for_compare(str(obj_pg))
    obj, _op = _resolver_object_name_operator_potencias(aid_canon, cto)
    if obj:
        return _ont_normalize_for_compare(str(obj))
    if base:
        ont = str(base.get("ONT") or "").strip()
        if ont and ont not in ("—", "-"):
            return ont
    return ""


def _ont_altiplano_para_compare(inp_hit: dict | None) -> str:
    if not inp_hit:
        return ""
    return (
        inp_hit.get("object_name_ui") or inp_hit.get("object_name") or ""
    ).strip()


def _ont_compare_payload(ont_pg: str, ont_alt: str) -> dict:
    """Campos ``ONT_POSTGRES`` / ``ONT_ALTIPLANO`` / ``ONT_MATCH`` para la UI de consulta."""
    pg = (ont_pg or "").strip()
    alt = (ont_alt or "").strip()
    pg_n = _ont_normalize_for_compare(pg) if pg else ""
    alt_n = _ont_normalize_for_compare(alt) if alt else ""
    match = bool(pg_n and alt_n and pg_n == alt_n)
    return {
        "ONT_POSTGRES": pg or None,
        "ONT_ALTIPLANO": alt or None,
        "ONT_MATCH": match,
        "ONT": alt or pg or None,
    }


def consultar_access_id_potencias(access_id):
    """Consulta TX/RX y SN (Expected Serial Number en Altiplano) de un Access ID puntual.

    Flujo:
    1) Resuelve AID (inventario activo o aux.bajada_inventario) para fallback Postgres.
    2) Device name y Expected SN en vivo: INP ``search-intents`` + intent/EMA operador.
    3) TX/RX y alarmas sobre la ONT Altiplano; si no hay SN/ONT en vivo, usa Postgres.

    Args:
        access_id: Access ID a consultar.

    Returns:
        Dict con `AID`, `TX`, `RX`, `SN`, `ONT` (Altiplano si existe) y comparación Postgres.
    """
    aid_in = str(access_id or "").strip()
    base = consultar_access_id_estructura(access_id)
    base_sn = ""
    if base:
        aid_canon = str(base["AID"]).strip()
        base_sn = (str(base.get("SN")).strip() if base.get("SN") else "") or ""
        status = str(base.get("Status") or "").strip().upper()
        cto = base.get("CTO")
    else:
        aid_canon = aid_in
        cto = None
        status = ""

    obj_pg, op_id_pg = _resolver_object_name_operator_potencias(aid_canon, cto)
    inp_hit = None if status == "FREE" else _fetch_inp_hit_por_access_id(aid_canon)
    obj_live, sn_live, op_id_live = _live_altiplano_device_y_expected_sn(
        aid_canon,
        object_name_pg=obj_pg,
        operator_id_pg=op_id_pg,
        inp_hit=inp_hit,
    )

    ont_pg = _ont_postgres_para_compare(aid_canon, cto, base, obj_pg)
    ont_alt = _ont_altiplano_para_compare(inp_hit)
    ont_fields = _ont_compare_payload(ont_pg, ont_alt)

    # Puertos FREE no tienen PON en Altiplano → no se consulta ni telemetry ni alarmas.
    # Para RESERVED se permite lectura completa (potencias, SN y alarmas).
    op_label = _operator_label_potencias(op_id_live or op_id_pg, base)

    if status == "FREE":
        return {
            "AID": aid_canon,
            "TX": None,
            "RX": None,
            "SN": None,
            "ALARMAS": [],
            "ULTIMA_ALARMA": None,
            "alarmas_label": None,
            "NV_STATUS": None,
            **ont_fields,
            **_altiplano_vno_payload(inp_hit, operator=op_label, access_id=aid_canon),
        }

    obj = obj_live or obj_pg
    op_id = op_id_live if op_id_live is not None else op_id_pg
    if not obj or op_id is None:
        return {
            "AID": aid_canon or access_id,
            "TX": None,
            "RX": None,
            "SN": None,
            "ALARMAS": [],
            "ULTIMA_ALARMA": None,
            "alarmas_label": None,
            "NV_STATUS": None,
            **ont_fields,
            **_altiplano_vno_payload(inp_hit, operator=op_label, access_id=aid_canon),
        }

    telem = obtener_telemetry_ont(aid_canon, obj, op_id)
    tx = telem.get("tx")
    rx = telem.get("rx")
    out = {
        "AID": aid_canon,
        "TX": tx,
        "RX": rx,
        # SN: Expected Serial en vivo; Postgres solo si Altiplano no devuelve lectura.
        "SN": telem.get("sn") or sn_live or base_sn or None,
        **ont_fields,
        **_altiplano_vno_payload(inp_hit, operator=op_label, access_id=aid_canon),
    }
    from altiplano import filter_alarmas_para_ont

    live_sn = out.get("SN")
    ld_reason = telem.get("onu_last_down_reason")
    ld_ts = telem.get("onu_last_down_ts")
    ema_onu_ausente = False
    if not ld_reason and obj:
        from altiplano import _fetch_ema_oper_admin_inp, _ne_from_object_name_raw

        ne_val = _ne_from_object_name_raw(obj)
        if ne_val:
            inp_ld = _fetch_ema_oper_admin_inp(
                aid_canon,
                obj,
                ne_val,
                operator_name=op_label,
            )
            ld_reason = inp_ld.get("onu_last_down_reason")
            ld_ts = inp_ld.get("onu_last_down_ts")
            ema_onu_ausente = bool(inp_ld.get("ema_onu_ausente_en_pon"))
    out["ALARMAS"] = filter_alarmas_para_ont(
        obtener_alarmas_ont_activas(aid_canon, obj, op_id),
        str(live_sn).strip() if live_sn else None,
        obj,
    )
    out["ULTIMA_ALARMA"] = ultima_alarma_ont_payload(
        obtener_ultima_alarma_ont(aid_canon, obj, op_id),
        live_sn=str(live_sn).strip() if live_sn else None,
        onu_last_down_reason=ld_reason,
        onu_last_down_ts=ld_ts or telem.get("health_ts"),
        ema_onu_ausente_en_pon=ema_onu_ausente,
        object_name_raw=obj,
    )
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
        op_live = _operador_desde_operatorid_cell(op_id)
        if _operador_display_valido(op_live):
            out["OPERADOR"] = op_live
            if op_live != op_label:
                out.update(
                    _altiplano_vno_payload(
                        inp_hit, operator=op_live, access_id=aid_canon
                    )
                )
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


def _potencias_desde_grupos_cto_paralelo(rows, *, carga_masiva: bool = False) -> list[dict]:
    """Agrupa filas por CTO y consulta Altiplano en paralelo (varios CTO por RAMA)."""
    if not rows:
        return []
    por_cto: dict[str, list] = defaultdict(list)
    for row in rows:
        por_cto[str(row[2])].append(row)
    grupos = list(por_cto.values())
    if len(grupos) <= 1:
        return _potencias_desde_filas_ont_cto(grupos[0], carga_masiva=carga_masiva) if grupos else []

    max_workers = min(len(grupos), get_altiplano_power_cto_workers(carga_masiva=carga_masiva))
    resultado: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_potencias_desde_filas_ont_cto, grp, carga_masiva=carga_masiva)
            for grp in grupos
        ]
        for fut in as_completed(futures):
            try:
                resultado.extend(fut.result())
            except Exception:
                logger.exception("potencias paralelo por CTO")
    return resultado


def _potencias_desde_filas_ont_cto(rows, *, carga_masiva: bool = False):
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
            potencias = obtener_potencias_por_cto(ne, onts, carga_masiva=carga_masiva)
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


def consultar_cto_potencias(cto, *, carga_masiva: bool = False):
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

    return _potencias_desde_filas_ont_cto(rows, carga_masiva=carga_masiva)


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


def consultar_cto_tag_nfc(cto: str) -> str | None:
    """TAG NFC de la CTO desde ``cm.inventory_fat_occupation.nfc_tag_id``."""
    cto_norm = (cto or "").strip()
    if not cto_norm:
        return None
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT btrim(f.nfc_tag_id::text)
            FROM cm.inventory_fat_occupation f
            WHERE f.location_description = %s
              AND f.nfc_tag_id IS NOT NULL
              AND btrim(f.nfc_tag_id::text) <> ''
            LIMIT 1
            """,
            (cto_norm,),
        )
        row = cur.fetchone()
    return _nfc_tag_display(row[0] if row else None)


def consultar_cto_tag_nfc_batch(ctos: list[str]) -> dict[str, str | None]:
    """TAG NFC por CTO (``location_description``) en una sola consulta."""
    cleaned = list(dict.fromkeys(str(c or "").strip() for c in (ctos or []) if str(c or "").strip()))
    if not cleaned:
        return {}
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (f.location_description)
                btrim(f.location_description),
                btrim(f.nfc_tag_id::text)
            FROM cm.inventory_fat_occupation f
            WHERE f.location_description = ANY(%s)
              AND f.nfc_tag_id IS NOT NULL
              AND btrim(f.nfc_tag_id::text) <> ''
            ORDER BY f.location_description
            """,
            (cleaned,),
        )
        rows = cur.fetchall()
    out = {cto: None for cto in cleaned}
    for loc, nfc in rows:
        if loc:
            out[str(loc).strip()] = _nfc_tag_display(nfc)
    return out


def consultar_cto_desde_tag_nfc(nfc: str) -> str | None:
    """Resuelve la CTO (``location_description``) asociada a un TAG NFC."""
    nfc_norm = _nfc_tag_display(nfc)
    if not nfc_norm:
        return None
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT btrim(f.location_description)
            FROM cm.inventory_fat_occupation f
            WHERE btrim(f.nfc_tag_id::text) ILIKE %s
              AND btrim(COALESCE(f.location_description, '')) <> ''
            ORDER BY 1
            LIMIT 1
            """,
            (nfc_norm,),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    return str(row[0]).strip() or None


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


def consultar_rama_potencias(rama, *, carga_masiva: bool = False):
    """Devuelve TX/RX de todas las ONT de una rama.

    Args:
        rama: Identificador RATC.
        carga_masiva: Si True, limita paralelismo Altiplano (consulta masiva / ``/potencias/batch``).

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

    return _potencias_desde_grupos_cto_paralelo(rows, carga_masiva=carga_masiva)


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
    por_cto: dict[str, list] = defaultdict(list)
    for row in rows:
        por_cto[str(row[2])].append(row)
    grupos = list(por_cto.values())
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
