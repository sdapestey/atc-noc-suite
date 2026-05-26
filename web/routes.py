"""Registro de rutas HTTP de la aplicación Flask.

Este módulo concentra la capa web: parsea requests, valida entradas,
invoca servicios y devuelve templates o JSON según corresponda.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import re
import unicodedata
from uuid import uuid4

from config import Config, get_consulta_potencias_batch_workers

from flask import Response, current_app, g, jsonify, redirect, render_template, request, session, url_for

logger = logging.getLogger(__name__)
from urllib.parse import quote_plus

from altiplano import (
    _access_id_match_mode_for_inp_consult,
    actualizar_required_network_state_nbi,
    actualizar_required_network_state_ont_connection_inp,
    actualizar_tasa_composite_profiles_nbi,
    tasa_composite_profile_suggestions_nbi,
    borrar_intent_nbi,
    reinyectar_tasa_composite_nbi,
    build_consulta_create_prefill,
    enriquecer_consulta_con_operador,
    obtener_token_entorno_nbi,
    corregir_dependencias_l1_y_alinear_intent_inp,
    inp_advanced_filters_active_aligned_blocked,
    parse_l1_scheduler_missing_ont_connection,
    sincronizar_intent_nbi,
    sincronizar_intent_ont_connection_inp,
)
from db import ensure_db_connection_ready, healthcheck_db
from services.domain import (
    OPERADORES,
    canonical_operador_consulta,
    resumen_semaforo_desde_rx_values,
    sort_operadores_consulta,
    split_index_query_tokens,
)
from services import (
    ALLOWED_HISTORICO_DAYS,
    cambiar_sn_ont,
    consultar_access_id_desde_alias,
    consultar_access_id_baja_o_ausente,
    consultar_access_id_detalle_desde_bajada_inventario,
    cambiar_admin_status_access_id,
    consultar_access_id_potencias,
    consultar_cto_coordenadas,
    consultar_cto_coordenadas_batch,
    consultar_cto_direccion_postal,
    consultar_cto_estructura,
    consultar_cto_potencias,
    consultar_cto_potencias_cached,
    consultar_dashboard_rama,
    inventario_dashboard_rama,
    consultar_rama_estructura,
    consultar_rama_potencias,
    consultar_ci_op_por_rama,
    dashboard_camino_optico_access_id,
    dashboard_camino_optico_cto,
    dashboard_camino_optico_equipo,
    dashboard_camino_optico_lt,
    dashboard_camino_optico_rama,
    dashboard_camino_optico_sitio,
    gis_payload_para_lt,
    infer_camino_consulta_tipo,
    dashboard_calidad_aids_inconsistencia_datos,
    dashboard_calidad_dtv_sin_serial,
    dashboard_calidad_fat_nfc_duplicados_tabla,
    dashboard_calidad_fat_sin_nfc_tabla,
    dashboard_calidad_inventario_conciliacion,
    dashboard_calidad_inventario_hallazgos,
    dashboard_calidad_inventario_historico,
    dashboard_calidad_inventario_resumen,
    dashboard_calidad_inventario_resumen_general,
    dashboard_calidad_inventario_estadisticas,
    dashboard_olts,
    dashboard_rama_bundle,
    buscar_intents_ont_connection_inp,
    crear_ont_connection_intent,
    estructura_dashboard_lt,
    export_dashboard_olts_csv,
    export_dashboard_ramas_csv,
    export_csv_potencias_historico_rama,
    export_dashboard_calidad_inventario_csv,
    export_index_csv_filename,
    export_index_query_csv,
    consultar_potencias_altiplano_ahora_rama,
    consultar_potencias_historico_rama,
)
from services.inp_borrado_cascade import borrar_inp_con_cascada_vno
from services.tasa_postman_catalog import build_tasa_vno_wizard_context
from services.tasa_postman_execute import execute_tasa_postman_api
from services.camino_gis import consultar_cto_coordenadas_desde_sfat
from services.inventory import resolver_target_ont_connection_por_access_id, _access_lookup_token_ok

_ALTIPLANO_INTENT_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
# Access ID numérico o alfanumérico (ALCL…, RES_IP_…, Srvc_loc_…, etc.)
_ALTIPLANO_BY_ID_ACCESS_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,256}$")
ALTIPLANO_BORRADO_LOTE_MAX_ITEMS = 300

_ALTIPLANO_UI_LOGIN_FAIL_MSG = (
    "Usuario o contraseña incorrectos. Verificá las credenciales de Altiplano."
)


def _extract_altiplano_ui_credentials(data: dict) -> tuple[str, str | None]:
    """Usuario/contraseña enviados desde popups de consulta (lock ONT, cambio SN)."""
    user = (
        data.get("altiplano_user")
        or data.get("username")
        or data.get("nbi_user")
        or ""
    )
    user = str(user).strip()
    pwd = data.get("altiplano_password")
    if pwd is None:
        pwd = data.get("password")
    if pwd is not None and not isinstance(pwd, str):
        pwd = str(pwd)
    return user, pwd


def _nbi_entorno_for_operador(operador: str) -> str:
    """Entorno NBI usado para validar credenciales según operador comercial."""
    op = (operador or "").strip().upper()
    if op in ("TASA", "DIRECTV", "METROTEL", "IPLAN", "ATC", "SION"):
        return op
    return "INP"


def _validate_altiplano_ui_credentials(entorno_nbi: str, username: str, password) -> tuple[dict, int] | None:
    """
    Valida login REST contra Altiplano. None si OK; si no, (payload_json, http_status).
    """
    if not username or password is None or str(password) == "":
        return (
            {"ok": False, "message": "Usuario y contraseña de Altiplano requeridos"},
            400,
        )
    token = obtener_token_entorno_nbi(
        entorno_nbi,
        username,
        password,
        force_refresh=True,
    )
    if not token:
        return ({"ok": False, "message": _ALTIPLANO_UI_LOGIN_FAIL_MSG}, 401)
    return None

# Consulta INP (dashboard): solo device ``BA_OLTA_…`` (prefijo o ``…#VNO#gpon``) o Access ID, no ambos.
_INP_CONSULTA_DEVICE_PREFIX = "BA_OLTA_"


def _inp_consulta_device_name_valid(dn: str) -> bool:
    """True si el criterio device cumple el formato aceptado en consulta INP (head ``BA_OLTA_``)."""
    s = (dn or "").strip()
    if not s:
        return False
    head = s.split("#", 1)[0].strip()
    if len(head) <= len(_INP_CONSULTA_DEVICE_PREFIX):
        return False
    return head.upper().startswith(_INP_CONSULTA_DEVICE_PREFIX)


def _inp_consulta_remap_ba_olta_from_by_id(device_name: str, by_id: str) -> tuple[str, str]:
    """Promueve a ``device_name`` un target/prefijo BA_OLTA enviado solo en ``by_id`` (API / pegado)."""
    dn = (device_name or "").strip()
    bid = (by_id or "").strip()
    if bid and not dn and _inp_consulta_device_name_valid(bid) and _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(bid):
        return bid, ""
    return dn, bid


def classify_inp_consulta_query(raw: str) -> tuple[str, str, str | None]:
    """
    Clasifica un único criterio de consulta INP en (device_name, by_id, error).

    Target con ``#`` o prefijo ``BA_OLTA_`` → device; resto alfanumérico → Access ID.
    """
    s = unicodedata.normalize("NFKC", (raw or "").strip())
    if not s:
        return "", "", None
    if _ALTIPLANO_INTENT_UUID_RE.match(s):
        return (
            "",
            "",
            "La consulta solo admite Access ID o device/target; "
            "no uses el UUID del intent en este campo.",
        )
    if "#" in s:
        return s, "", None
    if _inp_consulta_device_name_valid(s):
        return s, "", None
    if _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(s):
        return "", s, None
    return (
        "",
        "",
        "Indicá un device ``BA_OLTA_…`` (o target ``…#VNO#gpon``) o un Access ID "
        "(dígitos o identificador alfanumérico).",
    )


def _normalize_inp_device_by_id_fields_from_request(data: dict) -> tuple[str, str]:
    """NFKC + strip; target en ``by_id`` → ``device_name``; con target completo ignora ``by_id`` inválido (no UUID/token)."""
    device_name = unicodedata.normalize("NFKC", (data.get("device_name") or "").strip())
    by_id = unicodedata.normalize("NFKC", (data.get("by_id") or data.get("id") or "").strip())
    if by_id and "#" in by_id:
        if not device_name:
            device_name = by_id
        by_id = ""
    if device_name and "#" in device_name and by_id:
        if not (
            _ALTIPLANO_INTENT_UUID_RE.match(by_id)
            or _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(by_id)
        ):
            by_id = ""
    return device_name, by_id


def _parse_access_id_for_borrado(by_id: str) -> tuple[str | None, str | None]:
    """Resuelve el campo Access ID para borrado (no admite UUID)."""
    if _ALTIPLANO_INTENT_UUID_RE.match(by_id):
        return None, (
            "No se admite UUID en borrado; indicá solo Access ID o device name "
            "(prefijo o target completo)."
        )
    if _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(by_id):
        return by_id, None
    return None, (
        "El Access ID debe ser dígitos o identificador alfanumérico "
        "(letras, números, _, -, .)"
    )


def _borrar_ont_connection_desde_campos(
    sess_token: str,
    device_name: str,
    by_id: str,
    *,
    svlan: str | None = None,
) -> dict:
    """Cascada VNO (TASA) y luego borrado INP ont-connection. ``device_name`` y ``by_id`` ya stripados."""
    if by_id:
        _access_filter, err = _parse_access_id_for_borrado(by_id)
        if err:
            return {"ok": False, "message": err}

    if not device_name and not by_id:
        return {
            "ok": False,
            "message": "Indicá device name (prefijo o target) y/o Access ID",
        }

    return borrar_inp_con_cascada_vno(
        sess_token,
        device_name,
        by_id,
        svlan=svlan,
    )


def _enrich_consulta_inp_no_match(
    out: dict,
    *,
    access_filter: str | None,
    device_name: str | None,
    inventory_resolution: dict | None,
    has_advanced_filters: bool = False,
) -> dict:
    """Mensaje y prefill de alta cuando la consulta INP no devolvió intents."""
    if not out.get("ok") or out.get("matches"):
        return out
    if has_advanced_filters or out.get("search_source") == "gui-search-intents-advanced":
        if not out.get("create_prefill") and ((device_name or "").strip() or (access_filter or "").strip()):
            prefill = build_consulta_create_prefill(
                device_query=device_name,
                access_id=access_filter,
                inventory_resolution=inventory_resolution,
            )
            if prefill:
                out["create_prefill"] = prefill
        return out
    by_access = bool((access_filter or "").strip()) and not (device_name or "").strip()
    if by_access:
        out["message"] = "No existe ese Access ID en Altiplano"
        out["consulta_criterion"] = "access_id"
    else:
        out["message"] = "No existe ese Device Name en Altiplano"
        out["consulta_criterion"] = "device_name"
    out["no_match"] = True
    out["suggest_create"] = True
    if not out.get("create_prefill"):
        prefill = build_consulta_create_prefill(
            device_query=device_name,
            access_id=access_filter,
            inventory_resolution=inventory_resolution,
        )
        if prefill:
            out["create_prefill"] = prefill
    return out


def _vno_mutacion_from_request(data: dict) -> dict | None:
    """
    Mutación directa en NBI operador (pestaña VNO): ``target`` + ``intent_type`` + ``operator``.
    """
    scope = (data.get("scope") or data.get("consulta_scope") or "").strip().lower()
    op = (data.get("operator") or data.get("entorno_nbi") or "").strip().upper()
    if scope != "vno" and not (op and op != "INP"):
        return None
    if not op:
        op = "TASA"
    target = (data.get("target") or data.get("device_name") or "").strip()
    intent_type = (data.get("intent_type") or data.get("intent-type") or "").strip()
    if not target:
        return {
            "error": (
                {"ok": False, "message": "Target requerido para acción en VNO", "matches": []},
                400,
            )
        }
    if not intent_type:
        return {
            "error": (
                {
                    "ok": False,
                    "message": "intent_type requerido (ont, ont-connection, tasa-composite, …)",
                    "matches": [],
                },
                400,
            )
        }
    return {"operator": op, "target": target, "intent_type": intent_type, "vno": True}


def _inp_intent_mutacion_context(data: dict) -> dict:
    """
    Parsea device/target, Access ID o UUID de intent (mutaciones / API) y resolución inventario ATC
    cuando solo viene Access ID. La consulta ``consultar-intent`` no admite UUID; las mutaciones sí.
    """
    device_name, by_id = _normalize_inp_device_by_id_fields_from_request(data)
    intent_uuid = None
    access_filter = None
    if by_id:
        if _ALTIPLANO_INTENT_UUID_RE.match(by_id):
            intent_uuid = by_id
        elif _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(by_id):
            access_filter = by_id
        else:
            return {
                "error": (
                    {
                        "ok": False,
                        "message": (
                            "El campo ID debe ser UUID de intent o Access ID "
                            "(dígitos o identificador alfanumérico: letras, números, _, -, .). "
                            "Si querés filtrar por target, usá device_name con el prefijo o target completo "
                            "(…#VNO#gpon), no en by_id."
                        ),
                        "matches": [],
                    },
                    400,
                )
            }
    if not device_name and not by_id:
        return {
            "error": (
                {
                    "ok": False,
                    "message": "Indicá device name (prefijo del target) y/o Access ID / UUID",
                    "matches": [],
                },
                400,
            )
        }
    inventory_resolution = None
    inventory_miss_fallback = False
    dn = device_name
    if access_filter and not dn:
        inv = resolver_target_ont_connection_por_access_id(access_filter)
        if inv.get("ok"):
            dn = inv["device_name_for_query"]
            inventory_resolution = {k: v for k, v in inv.items() if k != "ok"}
        else:
            inventory_miss_fallback = True
    return {
        "device_prefix": dn or None,
        "access_id": access_filter,
        "intent_uuid": intent_uuid,
        "inventory_resolution": inventory_resolution,
        "inventory_miss_fallback": inventory_miss_fallback,
    }


def _http_code_for_borrado_payload(out: dict) -> int:
    if out.get("ok"):
        return 200
    msg_err = (out.get("message") or "").lower()
    if any(
        sub in msg_err
        for sub in (
            "indicá device name",
            "access id debe ser",
            "no se admite uuid",
        )
    ):
        return 400
    code = 502
    if "se encontraron" in msg_err and "intent" in msg_err:
        code = 400
    elif "no se encontró ningún intent" in msg_err:
        code = 400
    elif "no tiene target" in msg_err:
        code = 400
    return code


def _build_google_maps_search_url(lat: float, lon: float) -> str:
    """Construye una URL de Google Maps a partir de lat/lon."""
    lat_lon = f"{lat},{lon}"
    return "https://www.google.com/maps/search/?api=1&query=" f"{quote_plus(lat_lon)}"


def _consultar_cto_coords_con_fallback(cto: str) -> dict | None:
    """Coordenadas CTO con fallback: inventario -> cm.ci_sfat_mfat_bfat."""
    coords = consultar_cto_coordenadas(cto)
    if coords:
        return coords
    try:
        return consultar_cto_coordenadas_desde_sfat(cto)
    except Exception:
        current_app.logger.warning(
            "Fallback CTO coords desde sfat falló",
            extra={"cto": cto, **_request_context_for_log()},
            exc_info=True,
        )
        return None


def _update_route_and_maps_from_result(resultado: dict, ruta: dict) -> str | None:
    """Actualiza `ruta` (AID/CTO/RAMA) desde un resultado y devuelve URL de Maps.

    Args:
        resultado: Dict con claves compatibles con el detalle de Access ID.
        ruta: Estructura mutable usada por el template (`aid`, `cto`, `rama`).

    Returns:
        URL de Google Maps para la CTO si hay coordenadas; de lo contrario, `None`.
    """
    ruta["aid"] = resultado["AID"]
    ruta["cto"] = resultado["CTO"]
    ruta["rama"] = resultado.get("RAMA")
    if not resultado.get("CTO") or resultado["CTO"] == "—":
        return None
    coords = _consultar_cto_coords_con_fallback(resultado["CTO"])
    if not coords:
        return None
    return _build_google_maps_search_url(coords["lat"], coords["lon"])


def _is_alias_identifier(value_upper: str) -> bool:
    """Indica si el valor de búsqueda tiene formato alias soportado."""
    return (
        value_upper.startswith("SRVC_LOC_")
        or value_upper.startswith("RES_MT_")
        or value_upper.startswith("RES_IP_")
    )


def _consulta_semaforo_desde_consulta(consulta: dict) -> dict:
    """Conteos RX rojo/amarillo/verde (misma regla que dashboard RAMA / CTO)."""
    empty = {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0}
    try:
        if consulta.get("resultado"):
            aid = (consulta.get("resultado") or {}).get("AID")
            if aid is None or aid == "" or aid == "—":
                return dict(empty)
            pot = consultar_access_id_potencias(str(aid).strip())
            rx = pot.get("RX") if isinstance(pot, dict) else None
            return resumen_semaforo_desde_rx_values([rx])

        ruta = consulta.get("ruta") or {}
        rama = (ruta.get("rama") or "").strip()
        if rama and consulta.get("es_rama"):
            data = consultar_dashboard_rama(rama)
            if isinstance(data, dict):
                res = data.get("__dashboard_resumen__")
                if isinstance(res, dict):
                    return {
                        "ROJAS": int(res.get("ROJAS") or 0),
                        "AMARILLAS": int(res.get("AMARILLAS") or 0),
                        "VERDES": int(res.get("VERDES") or 0),
                    }
            return dict(empty)

        cto = (ruta.get("cto") or "").strip()
        if cto:
            rx_vals = [p.get("RX") for p in (consultar_cto_potencias(cto) or [])]
            return resumen_semaforo_desde_rx_values(rx_vals)

        return dict(empty)
    except Exception:
        current_app.logger.exception("consulta índice: semáforo RX")
        return dict(empty)


def _resolve_index_consulta(token: str, *, defer_altiplano_summary: bool = False) -> dict:
    """Resuelve un token de búsqueda del índice (Access ID numérico o alfanumérico, CTO FATC, RAMA RATC o alias).

    Si ``defer_altiplano_summary`` es True, no llama a Altiplano para el resumen RX del panel;
    el cliente lo completa tras ``/potencias`` (consulta individual y masiva).
    """
    token = (token or "").strip()
    vu = token.upper()
    consulta = {
        "token": token,
        "resultado": None,
        "tabla_cto": None,
        "es_rama": False,
        "ruta": {"aid": None, "cto": None, "rama": None},
        "cto_maps_url": None,
        "cto_postal_address": None,
        "busqueda_aid": None,
    }
    if not token:
        if defer_altiplano_summary:
            consulta["semaforo_resumen"] = {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0}
            consulta["semaforo_deferred"] = True
        else:
            consulta["semaforo_resumen"] = _consulta_semaforo_desde_consulta(consulta)
            consulta["semaforo_deferred"] = False
        return consulta

    if token.isdigit():
        resultado = consultar_access_id_detalle_desde_bajada_inventario(token)
        if resultado:
            consulta["resultado"] = resultado
            consulta["cto_maps_url"] = _update_route_and_maps_from_result(resultado, consulta["ruta"])
        else:
            consulta["busqueda_aid"] = consultar_access_id_baja_o_ausente(token)

    elif "FATC" in vu:
        consulta["tabla_cto"] = consultar_cto_estructura(token)
        consulta["ruta"]["cto"] = token
        coords = _consultar_cto_coords_con_fallback(token)
        if coords:
            consulta["cto_maps_url"] = _build_google_maps_search_url(
                coords["lat"], coords["lon"]
            )

    elif "RATC" in vu:
        consulta["tabla_cto"] = consultar_rama_estructura(token)
        consulta["es_rama"] = True
        consulta["ruta"]["rama"] = token

    elif _is_alias_identifier(vu):
        resultado = consultar_access_id_desde_alias(token)
        if resultado:
            consulta["resultado"] = resultado
            consulta["cto_maps_url"] = _update_route_and_maps_from_result(resultado, consulta["ruta"])
        else:
            consulta["busqueda_aid"] = {"tipo": "no_existe", "AID": token}

    elif _access_lookup_token_ok(token) and "FATC" not in vu and "RATC" not in vu:
        resultado = consultar_access_id_detalle_desde_bajada_inventario(token)
        if resultado:
            consulta["resultado"] = resultado
            consulta["cto_maps_url"] = _update_route_and_maps_from_result(resultado, consulta["ruta"])
        else:
            consulta["busqueda_aid"] = consultar_access_id_baja_o_ausente(token)

    if consulta["ruta"].get("cto"):
        consulta["cto_postal_address"] = consultar_cto_direccion_postal(consulta["ruta"]["cto"])

    if defer_altiplano_summary:
        consulta["semaforo_resumen"] = {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0}
        consulta["semaforo_deferred"] = True
    else:
        consulta["semaforo_resumen"] = _consulta_semaforo_desde_consulta(consulta)
        consulta["semaforo_deferred"] = False
    return consulta


_CONSULTA_INDIVIDUAL_MULTI_TOKEN_MSG = (
    "En consulta individual solo se admite un Access ID, una CTO o una RAMA. "
    "Usá la pestaña «Masivo» para pegar varias líneas o varios valores separados por coma."
)


def _consulta_row_in_service(row: dict) -> bool:
    st = row.get("STATUS") if row.get("STATUS") is not None else row.get("Status")
    return str(st or "").strip().upper() == "IN SERVICE"


def count_consulta_in_service_ont_rows(rows) -> int:
    """ONT con estado IN SERVICE (misma regla que badges ONT en index.html)."""
    return sum(1 for r in (rows or []) if _consulta_row_in_service(r))


def _consulta_in_service_ont_from_tabla(tabla_cto, *, es_rama: bool) -> int:
    if not tabla_cto:
        return 0
    if es_rama:
        return sum(count_consulta_in_service_ont_rows(rows) for rows in tabla_cto.values())
    if isinstance(tabla_cto, list):
        return count_consulta_in_service_ont_rows(tabla_cto)
    return 0


def _consulta_fila_count(c: dict) -> int:
    """Filas con equipos (detalle=1, tabla CTO/RAMA=suma de ONT)."""
    if c.get("resultado"):
        return 1
    t = c.get("tabla_cto")
    if not t:
        return 0
    if c.get("es_rama"):
        return sum(len(rows) for rows in t.values())
    return len(t) if isinstance(t, list) else 0


def _consulta_section_cto_ont(c: dict) -> tuple[int, int]:
    """CTO y ONT IN SERVICE de una sección (misma lógica que badges en index.html)."""
    if c.get("resultado"):
        res = c["resultado"]
        cto = 1 if (res.get("CTO") and res.get("CTO") != "—") else 0
        ont = 1 if _consulta_row_in_service(res) else 0
        return cto, ont
    t = c.get("tabla_cto")
    if not t:
        return 0, 0
    if c.get("es_rama"):
        return len(t), _consulta_in_service_ont_from_tabla(t, es_rama=True)
    if isinstance(t, list):
        return 1, count_consulta_in_service_ont_rows(t)
    return 0, 0


def _consulta_in_service_inventory_rows(c: dict) -> list[dict]:
    """Filas inventario IN SERVICE de una sección (para totales por operador)."""
    if c.get("resultado"):
        res = c["resultado"]
        return [res] if _consulta_row_in_service(res) else []
    t = c.get("tabla_cto")
    if not t:
        return []
    if c.get("es_rama"):
        out: list[dict] = []
        for rows in t.values():
            out.extend(r for r in rows if _consulta_row_in_service(r))
        return out
    if isinstance(t, list):
        return [r for r in t if _consulta_row_in_service(r)]
    return []


def _consulta_masivo_inventory_totals(consultas: list[dict]) -> dict | None:
    """Suma CTO/ONT IN SERVICE y desglose por operador (consulta masiva, >1 token)."""
    if len(consultas) <= 1:
        return None
    cto_total = 0
    ont_total = 0
    ont_por_operador: dict[str, int] = {}
    for c in consultas:
        cto, ont = _consulta_section_cto_ont(c)
        cto_total += cto
        ont_total += ont
        for row in _consulta_in_service_inventory_rows(c):
            op_label = canonical_operador_consulta(row.get("OPERADOR"))
            if not op_label:
                continue
            ont_por_operador[op_label] = ont_por_operador.get(op_label, 0) + 1
    ops_orden = sort_operadores_consulta(ont_por_operador.keys())
    return {
        "cto": cto_total,
        "ont": ont_total,
        "ont_por_operador": [(op, ont_por_operador[op]) for op in ops_orden],
    }


def sort_consulta_operadores_chips(operadores) -> list[str]:
    """Chips de operador en Consulta: solo TASA, DirecTV, Metrotel, Iplan, ATC, SION."""
    return sort_operadores_consulta(operadores)


def operador_metric_pill_slug(operador: str) -> str:
    """Slug CSS ``olt-metric-pill--op-*`` (misma regla que dashboard-olt.js)."""
    return re.sub(r"[^a-z0-9]+", "-", (operador or "").strip().lower()).strip("-")


def _consulta_operadores_union(consultas: list[dict]) -> list[str]:
    """Unión de operadores con orden estable (para un solo toolbar con varias consultas)."""
    seen: set[str] = set()
    out: list[str] = []
    for q in consultas:
        t = q.get("tabla_cto")
        if not t or q.get("resultado"):
            continue
        if q.get("es_rama"):
            for rows in t.values():
                for r in rows:
                    op = (r or {}).get("OPERADOR")
                    if op and op not in seen:
                        seen.add(op)
                        out.append(op)
        else:
            for r in t:
                op = (r or {}).get("OPERADOR")
                if op and op not in seen:
                    seen.add(op)
                    out.append(op)
    return sort_consulta_operadores_chips(out)


def _request_context_for_log() -> dict:
    return {
        "request_id": getattr(g, "request_id", "-"),
        "path": request.path,
        "method": request.method,
    }


def _log_and_internal_error(message: str):
    current_app.logger.exception(message, extra={"context": _request_context_for_log()})
    return jsonify({"error": message, "request_id": getattr(g, "request_id", "-")}), 500


def _csv_download_response(csv_text: str, filename: str) -> Response:
    """Respuesta HTTP para descargar CSV UTF-8 con BOM."""
    return Response(
        "\ufeff" + (csv_text or ""),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _deprecated_estadisticas_json(payload, *, successor_path: str) -> Response:
    """JSON deprecado: mismo cuerpo histórico, con cabeceras RFC para migrar a inventario.json."""
    resp = jsonify(payload)
    resp.headers["Deprecation"] = "true"
    resp.headers["Link"] = f'<{successor_path}>; rel="successor-version"'
    resp.headers["Warning"] = f'299 - "Deprecated API. Use {successor_path}."'
    return resp


def register(app):
    """Registra todas las rutas HTTP en la app Flask.

    Además define constantes de negocio acotadas al contexto web
    (por ejemplo, valores fijos para intents de Altiplano).
    """
    ONT_CONNECTION_PIR_FIXED = 1000
    ONT_CONNECTION_CIR_FIXED = 35

    @app.before_request
    def attach_request_id():
        g.request_id = request.headers.get("X-Request-Id", "").strip() or str(uuid4())[:12]

    @app.before_request
    def ensure_db_ready():
        # Evita checks en assets/health y durante tests; en runtime previene 500 por conexión stale.
        if current_app.config.get("TESTING"):
            return None
        if request.path.startswith("/static/") or request.path == "/health":
            return None

        if ensure_db_connection_ready():
            return None

        message = "Base de datos no disponible temporalmente. Reintentá en unos segundos."
        is_json = (
            request.path.startswith("/api/")
            or request.path.endswith("/consultar")
            or request.path.endswith("/gis-por-lt")
            or request.path.endswith(".json")
            or request.accept_mimetypes.best == "application/json"
        )
        if is_json:
            return jsonify({"error": message, "request_id": getattr(g, "request_id", "-")}), 503
        return message, 503

    @app.route("/health")
    def health():
        payload = {"ok": True, "time": datetime.now(timezone.utc).isoformat()}
        if request.args.get("db"):
            payload["db"] = healthcheck_db()
            payload["ok"] = payload["db"]
        return jsonify(payload)

    @app.route("/dashboard")
    def dashboard_entry():
        tab = request.args.get("tab", "id").lower()
        if tab == "rama":
            return redirect(url_for("dash_rama"))
        if tab == "lt":
            return redirect(url_for("dash_olt"))
        if tab in ("camino", "camino-optico", "optico"):
            return redirect(url_for("dash_camino_optico"))
        if tab == "altiplano":
            return redirect(url_for("dash_altiplano"))
        if tab in ("historico", "potencias-historico"):
            return redirect(url_for("dash_potencias_historico"))
        if tab in ("calidad", "calidad-inventario", "estadisticas"):
            return redirect(url_for("dash_estadisticas"))
        return redirect(url_for("index"))

    @app.route("/", methods=["GET", "POST"])
    def index():
        consulta_modo = "individual"
        value_individual = ""
        value_masivo = ""
        consultas: list = []
        consulta_error = None

        if request.method == "POST":
            consulta_modo = (request.form.get("consulta_modo") or "individual").strip().lower()
            if consulta_modo not in ("individual", "masivo"):
                consulta_modo = "individual"
            if consulta_modo == "masivo":
                raw = (request.form.get("value_masivo") or "").strip()
                value_masivo = raw
            else:
                raw = (request.form.get("value") or "").strip()
                value_individual = raw

            tokens = split_index_query_tokens(raw)
            if consulta_modo == "individual":
                if len(tokens) > 1:
                    consulta_error = _CONSULTA_INDIVIDUAL_MULTI_TOKEN_MSG
                elif len(tokens) == 1:
                    consultas = [
                        _resolve_index_consulta(tokens[0], defer_altiplano_summary=True)
                    ]
            else:
                for token in tokens:
                    consultas.append(
                        _resolve_index_consulta(token, defer_altiplano_summary=True)
                    )
        elif request.args.get("modo", "").strip().lower() == "masivo":
            consulta_modo = "masivo"

        value = value_masivo if consulta_modo == "masivo" else value_individual

        if len(consultas) > 1:
            consulta_ops_merged = _consulta_operadores_union(consultas)
            consulta_row_counts = [_consulta_fila_count(c) for c in consultas]
            consulta_masivo_totals = _consulta_masivo_inventory_totals(consultas)
        else:
            consulta_ops_merged = None
            consulta_row_counts = None
            consulta_masivo_totals = None

        return render_template(
            "index.html",
            consultas=consultas,
            consulta_modo=consulta_modo,
            value_individual=value_individual,
            value_masivo=value_masivo,
            consulta_error=consulta_error,
            value=value,
            consulta_ops_merged=consulta_ops_merged,
            consulta_row_counts=consulta_row_counts,
            consulta_masivo_totals=consulta_masivo_totals,
            sort_consulta_operadores_chips=sort_consulta_operadores_chips,
            operador_metric_pill_slug=operador_metric_pill_slug,
            count_consulta_in_service_ont_rows=count_consulta_in_service_ont_rows,
        )

    def _potencias_payload_for_valor(valor: str):
        valor = (valor or "").strip()
        if not valor:
            return None
        valor_upper = valor.upper()

        if valor.isdigit():
            return consultar_access_id_potencias(valor)

        if "FATC" in valor_upper:
            return consultar_cto_potencias_cached(valor)

        if "RATC" in valor_upper:
            return consultar_rama_potencias(valor)

        if _is_alias_identifier(valor_upper):
            resolved = consultar_access_id_desde_alias(valor)
            if not resolved:
                return []
            return consultar_access_id_potencias(str(resolved.get("AID") or valor))

        if (
            _access_lookup_token_ok(valor)
            and "FATC" not in valor_upper
            and "RATC" not in valor_upper
        ):
            return consultar_access_id_potencias(valor)

        return []

    @app.route("/potencias", methods=["POST"])
    def potencias_async():
        """Endpoint AJAX de potencias para índice/rama/cto.

        Acepta un valor libre y decide automáticamente si consultar por:
        - Access ID (numérico o alfanumérico VNO, p. ej. ``fes_a5_23``)
        - CTO (FATC)
        - RAMA (RATC)
        - Alias (Srvc_loc_*, etc.)
        """
        valor = (request.form.get("value") or "").strip()
        if not valor:
            return jsonify({"error": "Parámetro value requerido"}), 400
        payload = _potencias_payload_for_valor(valor)
        if payload is None:
            return jsonify({"error": "Parámetro value requerido"}), 400
        return jsonify(payload)

    @app.route("/potencias/batch", methods=["POST"])
    def potencias_batch():
        """Varias RAMAs/CTOs/AIDs en un solo request (consulta masiva más rápida)."""
        body = request.get_json(silent=True) or {}
        values = body.get("values")
        if not isinstance(values, list):
            values = request.form.getlist("values") or []
        tokens = [str(v).strip() for v in values if str(v).strip()]
        if not tokens:
            return jsonify({"error": "values requerido (lista de tokens)"}), 400

        configured = get_consulta_potencias_batch_workers()
        # Cada RAMA/CTO usa al menos una conexión breve del pool; no superar DB_POOL_MAX.
        pool_budget = max(1, int(Config.DB_POOL_MAX) - 2)
        max_workers = max(1, min(len(tokens), configured, pool_budget))
        items: dict[str, object] = {}

        def _fetch_one(tok: str):
            try:
                payload = _potencias_payload_for_valor(tok)
                return tok, payload if payload is not None else []
            except Exception:
                logger.exception("potencias batch: fallo en token %r", tok)
                return tok, []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for tok, payload in executor.map(_fetch_one, tokens):
                items[tok] = payload

        return jsonify({"items": items})

    @app.route("/consulta/altiplano/validate", methods=["POST"])
    def consulta_altiplano_validate():
        """Valida usuario/contraseña Altiplano sin ejecutar una operación de red."""
        data = request.get_json(silent=True) or request.form
        operador = (data.get("operador") or "").strip()
        alt_user, alt_pwd = _extract_altiplano_ui_credentials(data)
        auth_err = _validate_altiplano_ui_credentials(
            _nbi_entorno_for_operador(operador), alt_user, alt_pwd
        )
        if auth_err:
            return jsonify(auth_err[0]), auth_err[1]
        return jsonify({"ok": True, "message": "Sesión Altiplano válida"})

    @app.route("/sn/cambiar", methods=["POST"])
    def cambiar_sn():
        data = request.get_json(silent=True) or request.form
        access_id = (data.get("access_id") or "").strip()
        operador = (data.get("operador") or "").strip()
        ont_target = (data.get("ont_target") or "").strip()
        new_sn = (data.get("new_sn") or "").strip()
        alt_user, alt_pwd = _extract_altiplano_ui_credentials(data)

        if not access_id:
            return jsonify({"ok": False, "message": "access_id requerido"}), 400
        if not ont_target:
            return jsonify({"ok": False, "message": "ont_target requerido"}), 400
        if not new_sn:
            return jsonify({"ok": False, "message": "new_sn requerido"}), 400

        import importlib.util
        from pathlib import Path

        _sn_path = Path(__file__).resolve().parents[1] / "services" / "sn_altiplano.py"
        _sn_spec = importlib.util.spec_from_file_location("sn_altiplano", _sn_path)
        _sn_mod = importlib.util.module_from_spec(_sn_spec)
        _sn_spec.loader.exec_module(_sn_mod)

        new_sn_norm = _sn_mod.normalize_change_sn(new_sn, operador)
        sn_fmt_err = _sn_mod.validate_ont_sn_for_altiplano(new_sn_norm)
        if sn_fmt_err:
            return jsonify({"ok": False, "message": sn_fmt_err}), 400

        auth_err = _validate_altiplano_ui_credentials(
            _nbi_entorno_for_operador(operador), alt_user, alt_pwd
        )
        if auth_err:
            return jsonify(auth_err[0]), auth_err[1]

        result = cambiar_sn_ont(
            access_id=access_id,
            operador=operador,
            ont_target=ont_target,
            new_sn=new_sn_norm,
            nbi_username=alt_user,
            nbi_password=alt_pwd,
        )
        code = 200 if result.get("ok") else 502
        return jsonify(result), code

    @app.route("/ont/admin-status", methods=["POST"])
    def cambiar_admin_status_ont_route():
        data = request.get_json(silent=True) or request.form
        access_id = (data.get("access_id") or "").strip()
        operador = (data.get("operador") or "").strip()
        object_name = (data.get("object_name") or "").strip() or None
        admin_status = (data.get("admin_status") or "").strip().upper()
        toggle = str(data.get("toggle") or "").lower() in ("1", "true", "yes")
        current = (data.get("current_admin") or "").strip().upper()
        alt_user, alt_pwd = _extract_altiplano_ui_credentials(data)

        if not access_id:
            return jsonify({"ok": False, "message": "access_id requerido"}), 400

        if toggle:
            if current == "LOCKED":
                admin_status = "UNLOCKED"
            elif current == "UNLOCKED":
                admin_status = "LOCKED"
            else:
                return jsonify(
                    {"ok": False, "message": "Estado admin actual desconocido"}
                ), 400

        if admin_status not in ("LOCKED", "UNLOCKED"):
            return jsonify(
                {"ok": False, "message": "admin_status debe ser LOCKED o UNLOCKED"}
            ), 400

        auth_err = _validate_altiplano_ui_credentials("INP", alt_user, alt_pwd)
        if auth_err:
            return jsonify(auth_err[0]), auth_err[1]

        result = cambiar_admin_status_access_id(
            access_id,
            operador,
            admin_status,
            object_name=object_name,
            nbi_username=alt_user,
            nbi_password=alt_pwd,
        )
        code = 200 if result.get("ok") else 502
        return jsonify(result), code

    @app.route("/pon/admin-status", methods=["POST"])
    def cambiar_admin_status_pon_route():
        data = request.get_json(silent=True) or request.form
        access_id = (data.get("access_id") or "").strip()
        operador = (data.get("operador") or "").strip()
        object_name = (data.get("object_name") or "").strip() or None
        admin_status = (data.get("admin_status") or "").strip().upper()
        toggle = str(data.get("toggle") or "").lower() in ("1", "true", "yes")
        current = (data.get("current_pon_admin") or "").strip().upper()
        alt_user, alt_pwd = _extract_altiplano_ui_credentials(data)

        if not access_id:
            return jsonify({"ok": False, "message": "access_id requerido"}), 400

        if toggle:
            if current == "LOCKED":
                admin_status = "UNLOCKED"
            elif current == "UNLOCKED":
                admin_status = "LOCKED"
            else:
                admin_status = "LOCKED"

        if admin_status not in ("LOCKED", "UNLOCKED"):
            return jsonify(
                {"ok": False, "message": "admin_status debe ser LOCKED o UNLOCKED"}
            ), 400

        auth_err = _validate_altiplano_ui_credentials("INP", alt_user, alt_pwd)
        if auth_err:
            return jsonify(auth_err[0]), auth_err[1]

        from services.inventory import cambiar_pon_admin_access_id

        result = cambiar_pon_admin_access_id(
            access_id,
            operador,
            admin_status,
            object_name=object_name,
            nbi_username=alt_user,
            nbi_password=alt_pwd,
        )
        code = 200 if result.get("ok") else 502
        return jsonify(result), code

    @app.route("/export/csv")
    def export_index_csv():
        value = request.args.get("value", "").strip()
        operador = (request.args.get("operador") or "").strip() or None
        data = export_index_query_csv(value, operador=operador)
        filename = export_index_csv_filename(value, operador=operador)
        return _csv_download_response(data, filename)

    @app.route("/dashboard/rama")
    def dash_rama():
        data = dashboard_rama_bundle()
        return render_template(
            "dashboard_rama.html",
            ramas=data["bloques"],
            ram_totales=data["totales"],
        )

    @app.route("/dashboard/rama/consultar", methods=["POST"])
    def dash_rama_consultar():
        rama = (request.form.get("rama") or "").strip()
        if not rama:
            return jsonify({"error": "Parámetro rama requerido"}), 400
        data = consultar_dashboard_rama(rama)
        return jsonify(data)

    @app.route("/dashboard/rama/inventario", methods=["POST"])
    def dash_rama_inventario():
        rama = (request.form.get("rama") or "").strip()
        if not rama:
            return jsonify({"error": "Parámetro rama requerido"}), 400
        data = inventario_dashboard_rama(rama)
        return jsonify(data)

    @app.route("/dashboard/rama/cto-map")
    def dash_rama_cto_map():
        """Coordenadas CTO para mapa embebido (misma regla que consultar_cto_coordenadas)."""
        cto = (request.args.get("cto") or "").strip()
        if not cto:
            return jsonify({"ok": False, "error": "Parámetro cto requerido"}), 400
        try:
            coords = _consultar_cto_coords_con_fallback(cto)
        except Exception:
            return _log_and_internal_error("consultar_cto_coordenadas failed")
        if not coords:
            return jsonify({"ok": False, "error": "Sin coordenadas para esta CTO"})
        return jsonify({"ok": True, "cto": cto, "lat": coords["lat"], "lon": coords["lon"]})

    @app.route("/dashboard/rama/cto-address")
    def dash_rama_cto_address():
        """Dirección postal de CTO (si existe en cm.ci_sfat_mfat_bfat)."""
        cto = (request.args.get("cto") or "").strip()
        if not cto:
            return jsonify({"ok": False, "error": "Parámetro cto requerido"}), 400
        try:
            addr = consultar_cto_direccion_postal(cto)
        except Exception:
            return _log_and_internal_error("consultar_cto_direccion_postal failed")
        if not addr:
            return jsonify({"ok": False, "cto": cto, "error": "Sin dirección postal para esta CTO"})
        return jsonify({"ok": True, "cto": cto, "address": addr})

    @app.route("/dashboard/rama/rama-map")
    def dash_rama_rama_map():
        """Coordenadas de todas las CTO de una RAMA (batch inventario + fallback puntual)."""
        rama = (request.args.get("rama") or "").strip()
        if not rama:
            return jsonify({"ok": False, "error": "Parámetro rama requerido"}), 400
        try:
            inv = inventario_dashboard_rama(rama)
        except Exception:
            return _log_and_internal_error("inventario_dashboard_rama failed")
        ctos_total = len(inv)
        markers = []
        sin_coord = 0
        try:
            coords_map = consultar_cto_coordenadas_batch(list(inv.keys()))
        except Exception:
            return _log_and_internal_error("consultar_cto_coordenadas_batch failed")
        for cto in sorted(inv.keys()):
            coords = coords_map.get(cto)
            if not coords:
                try:
                    coords = _consultar_cto_coords_con_fallback(cto)
                except Exception:
                    return _log_and_internal_error("consultar_cto_coordenadas failed")
            if coords:
                markers.append({"cto": cto, "lat": coords["lat"], "lon": coords["lon"]})
            else:
                sin_coord += 1
        return jsonify(
            {
                "ok": True,
                "rama": rama,
                "markers": markers,
                "ctos_total": ctos_total,
                "ctos_sin_coordenadas": sin_coord,
            }
        )

    @app.route("/dashboard/rama/export.csv")
    def export_rama_csv():
        data = export_dashboard_ramas_csv()
        return _csv_download_response(data, "dashboard_ramas.csv")

    @app.route("/dashboard/olt")
    def dash_olt():
        olts = dashboard_olts()
        return render_template("dashboard_olt.html", olts=olts)

    @app.route("/dashboard/olt/consultar", methods=["POST"])
    def dash_olt_consultar():
        lt = request.form.get("lt", "").strip()
        return jsonify(estructura_dashboard_lt(lt))

    @app.route("/dashboard/olt/export.csv")
    def export_olt_csv():
        data = export_dashboard_olts_csv()
        return _csv_download_response(data, "dashboard_olts.csv")

    @app.route("/dashboard/cto/consultar", methods=["POST"])
    def dash_cto_consultar():
        cto = (request.form.get("cto") or "").strip()
        if not cto:
            return jsonify({"error": "Parámetro cto requerido"}), 400
        return jsonify(consultar_cto_potencias_cached(cto))

    @app.route("/dashboard/camino-optico")
    def dash_camino_optico():
        return render_template("dashboard_camino_optico.html")

    def _orquestador_session_token():
        if session.get("orquestador_ok") and session.get("orquestador_inp_token"):
            return session.get("orquestador_inp_token")
        return None

    @app.route("/dashboard/altiplano")
    def dash_altiplano():
        if not _orquestador_session_token():
            return render_template("dashboard_altiplano_login.html")
        ctx = {
            "orquestador_user": (session.get("orquestador_user") or "").strip() or "—",
        }
        ctx.update(build_tasa_vno_wizard_context())
        return render_template("dashboard_altiplano.html", **ctx)

    @app.route("/dashboard/altiplano/login", methods=["POST"])
    def dash_altiplano_login():
        """Valida usuario/contraseña contra Altiplano INP y abre sesión Orquestador."""
        data = request.get_json(silent=True) or {}
        user = (data.get("username") or data.get("altiplano_user") or "").strip()
        pwd = data.get("password")
        if pwd is None:
            pwd = data.get("altiplano_password")
        if pwd is not None and not isinstance(pwd, str):
            pwd = str(pwd)
        pwd = pwd or ""
        if not user or pwd == "":
            return jsonify({"ok": False, "message": "Usuario y contraseña requeridos"}), 400

        token = obtener_token_entorno_nbi("INP", user, pwd, force_refresh=True)
        if not token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "No se pudo iniciar sesión en Altiplano. "
                            "Verificá usuario y contraseña o la conectividad de red."
                        ),
                    }
                ),
                401,
            )

        session["orquestador_ok"] = True
        session["orquestador_user"] = user
        session["orquestador_inp_token"] = token
        return jsonify({"ok": True, "message": "Sesión iniciada"})

    @app.route("/dashboard/altiplano/vno/tasa/ejecutar", methods=["POST"])
    def dash_altiplano_tasa_ejecutar():
        """Ejecuta una request del catálogo Postman TASA (NBI) con sesión Orquestador."""
        if not _orquestador_session_token():
            return jsonify({"ok": False, "message": "Sesión requerida"}), 401
        data = request.get_json(silent=True) or {}
        api_id = (data.get("api_id") or "").strip()
        raw_vars = data.get("variables")
        variables: dict[str, str] = {}
        if isinstance(raw_vars, dict):
            variables = {str(k): "" if v is None else str(v) for k, v in raw_vars.items()}
        out = execute_tasa_postman_api(api_id, variables)
        if out.get("ok"):
            return jsonify(out), 200
        msg = (out.get("message") or "").lower()
        if any(
            frag in msg
            for frag in (
                "api_id",
                "no encontrada",
                "credenciales",
                "destino nbi",
                "faltan variables",
                "url final",
                "json de cuerpo",
                "cabecera",
            )
        ):
            return jsonify(out), 400
        return jsonify(out), 502

    @app.route("/dashboard/altiplano/logout", methods=["POST"])
    def dash_altiplano_logout():
        session.pop("orquestador_ok", None)
        session.pop("orquestador_user", None)
        session.pop("orquestador_inp_token", None)
        return jsonify({"ok": True})

    @app.route("/dashboard/potencias-historico")
    def dash_potencias_historico():
        return render_template("dashboard_potencias_historico.html")

    @app.route("/dashboard/estadisticas")
    def dash_estadisticas():
        return render_template("dashboard_estadisticas.html")

    def _estadisticas_redirect_legacy(suffix: str, *, code: int = 308):
        qs = request.query_string.decode("utf-8") if request.query_string else ""
        target = f"/dashboard/estadisticas/{suffix}" + (f"?{qs}" if qs else "")
        return redirect(target, code=code)

    @app.route("/dashboard/calidad-inventario")
    @app.route("/dashboard/calidad-inventario/")
    def dash_calidad_inventario_legacy():
        return redirect(url_for("dash_estadisticas"), code=308)

    @app.route("/dashboard/estadisticas/inventario.json")
    def dash_estadisticas_inventario_json():
        days = request.args.get("days", default=90, type=int)
        try:
            payload = dashboard_calidad_inventario_resumen_general(days=days)
        except Exception:
            return _log_and_internal_error("Error interno consultando inventario (estadísticas)")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/resumen-general.json")
    def dash_calidad_inventario_resumen_general_legacy():
        return _estadisticas_redirect_legacy("inventario.json")

    @app.route("/dashboard/estadisticas/inventario/tabla.json")
    def dash_estadisticas_inventario_tabla_json():
        tipo = (request.args.get("tipo") or "").strip()
        q = (request.args.get("q") or "").strip()
        limit = request.args.get("limit", default=10, type=int)
        offset = request.args.get("offset", default=0, type=int)
        loaders = {
            "dtv_sin_serial": dashboard_calidad_dtv_sin_serial,
            "aids_inconsistencia": dashboard_calidad_aids_inconsistencia_datos,
            "fat_sin_nfc": dashboard_calidad_fat_sin_nfc_tabla,
            "fat_nfc_duplicados": dashboard_calidad_fat_nfc_duplicados_tabla,
        }
        loader = loaders.get(tipo)
        if not loader:
            return jsonify({"error": "tipo de tabla no válido"}), 400
        try:
            payload = loader(q=q, limit=limit, offset=offset)
        except Exception:
            return _log_and_internal_error("Error interno consultando tabla de inventario")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/tabla.json")
    def dash_calidad_inventario_tabla_legacy():
        return _estadisticas_redirect_legacy("inventario/tabla.json")

    @app.route("/dashboard/estadisticas/altas-bajas.json")
    def dash_estadisticas_altas_bajas_json():
        days = request.args.get("days", default=90, type=int)
        granularity = (request.args.get("granularity") or "month").strip().lower()
        operador = (request.args.get("operador") or "").strip()
        fecha = (request.args.get("fecha") or "").strip()
        try:
            payload = dashboard_calidad_inventario_estadisticas(
                days=days,
                granularity=granularity,
                operador=operador,
                fecha=fecha,
            )
        except Exception:
            return _log_and_internal_error(
                "Error interno consultando altas y bajas de inventario"
            )
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/estadisticas.json")
    def dash_calidad_inventario_estadisticas_legacy():
        return _estadisticas_redirect_legacy("altas-bajas.json")

    @app.route("/dashboard/estadisticas/reglas/resumen.json")
    def dash_estadisticas_reglas_resumen_json():
        try:
            payload = dashboard_calidad_inventario_resumen()
        except Exception:
            return _log_and_internal_error("Error interno consultando resumen de reglas")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/resumen.json")
    def dash_calidad_inventario_resumen_legacy():
        return _estadisticas_redirect_legacy("reglas/resumen.json")

    @app.route("/dashboard/estadisticas/reglas/hallazgos.json")
    def dash_estadisticas_reglas_hallazgos_json():
        regla = (request.args.get("regla") or "").strip()
        estado_base = (request.args.get("estado_base") or "").strip()
        operador = (request.args.get("operador") or "").strip()
        q = (request.args.get("q") or "").strip()
        limit = request.args.get("limit", default=50, type=int)
        offset = request.args.get("offset", default=0, type=int)
        try:
            payload = dashboard_calidad_inventario_hallazgos(
                regla=regla,
                estado_base=estado_base,
                operador=operador,
                q=q,
                limit=limit,
                offset=offset,
            )
        except Exception:
            return _log_and_internal_error("Error interno consultando hallazgos de calidad")
        return jsonify(payload)

    @app.route("/dashboard/calidad-inventario/hallazgos.json")
    def dash_calidad_inventario_hallazgos_legacy():
        return _estadisticas_redirect_legacy("reglas/hallazgos.json")

    @app.route("/dashboard/estadisticas/reglas/conciliacion.json")
    def dash_estadisticas_reglas_conciliacion_json():
        try:
            payload = dashboard_calidad_inventario_conciliacion()
        except Exception:
            return _log_and_internal_error("Error interno consultando conciliación por operador")
        return _deprecated_estadisticas_json(
            payload,
            successor_path="/dashboard/estadisticas/inventario.json",
        )

    @app.route("/dashboard/calidad-inventario/conciliacion.json")
    def dash_calidad_inventario_conciliacion_legacy():
        return _estadisticas_redirect_legacy("reglas/conciliacion.json")

    @app.route("/dashboard/estadisticas/reglas/historico.json")
    def dash_estadisticas_reglas_historico_json():
        days = request.args.get("days", default=90, type=int)
        try:
            payload = dashboard_calidad_inventario_historico(days=days)
        except Exception:
            return _log_and_internal_error("Error interno consultando histórico de conciliaciones")
        return _deprecated_estadisticas_json(
            payload,
            successor_path=f"/dashboard/estadisticas/inventario.json?days={days}",
        )

    @app.route("/dashboard/calidad-inventario/historico.json")
    def dash_calidad_inventario_historico_legacy():
        return _estadisticas_redirect_legacy("reglas/historico.json")

    @app.route("/dashboard/estadisticas/reglas/export.csv")
    def dash_estadisticas_reglas_export_csv():
        regla = (request.args.get("regla") or "").strip()
        estado_base = (request.args.get("estado_base") or "").strip()
        operador = (request.args.get("operador") or "").strip()
        q = (request.args.get("q") or "").strip()
        try:
            csv_text = export_dashboard_calidad_inventario_csv(
                regla=regla,
                estado_base=estado_base,
                operador=operador,
                q=q,
            )
        except Exception:
            return _log_and_internal_error("Error interno exportando hallazgos de calidad")
        return _csv_download_response(csv_text, "estadisticas_reglas.csv")

    @app.route("/dashboard/calidad-inventario/export.csv")
    def dash_calidad_inventario_export_legacy():
        return _estadisticas_redirect_legacy("reglas/export.csv")

    @app.route("/api/potencias-historico/<ratc>")
    def api_potencias_historico(ratc):
        days = request.args.get("days", default=30, type=int)
        try:
            payload = consultar_potencias_historico_rama(ratc, days=days)
        except Exception:
            return _log_and_internal_error("Error interno consultando historico de potencias")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 500)
            )
        return jsonify(payload)

    @app.route("/api/potencias-historico/<ratc>/consultar-ahora", methods=["POST"])
    def api_potencias_historico_consultar_ahora(ratc):
        try:
            payload = consultar_potencias_altiplano_ahora_rama(ratc)
        except Exception:
            return _log_and_internal_error("Error interno consultando Altiplano (tiempo real)")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 400)
            )
        return jsonify(payload)

    @app.route("/dashboard/potencias-historico/export.csv")
    def export_potencias_historico_csv():
        ratc = (request.args.get("ratc") or "").strip()
        days = request.args.get("days", default=30, type=int)
        if days not in ALLOWED_HISTORICO_DAYS:
            return jsonify({"error": "Parámetro days inválido. Valores permitidos: 1 (24h), 7, 15, 30"}), 400
        try:
            payload = export_csv_potencias_historico_rama(ratc, days=days)
        except Exception:
            return _log_and_internal_error("Error interno exportando historico de potencias")
        if not payload.get("ok"):
            return jsonify({"error": payload.get("error", "Error de consulta")}), int(
                payload.get("status_code", 500)
            )
        ratc_safe = re.sub(r"[^A-Za-z0-9._-]+", "_", ratc or "rama").strip("_") or "rama"
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M")
        range_tag = "24h" if days == 1 else f"{days}d"
        filename = f"potencias_historico_{ratc_safe}_{range_tag}_{ts_tag}.csv"
        return _csv_download_response(payload["csv"], filename)


    @app.route("/dashboard/altiplano/ont-connection", methods=["POST"])
    def dash_altiplano_ont_connection():
        """Crea un intent ONT Connection desde la UI de Altiplano.

        Reglas importantes:
        - `device_name` y `fiber_name` se derivan server-side.
        - PIR/CIR siempre se fuerzan con constantes internas.
        """
        data = request.get_json(silent=True) or request.form
        operador = (data.get("operador") or "").strip()
        entorno_nbi = (data.get("entorno_nbi") or "").strip()
        sitio = (data.get("sitio") or "").strip()
        device_name = (data.get("device_name") or "").strip()
        lt = (data.get("lt") or "").strip()
        pon = (data.get("pon") or "").strip()
        ont = (data.get("ont") or "").strip()
        vno = (data.get("vno") or "").strip()
        fiber_name = (data.get("fiber_name") or "").strip()
        access_id = (data.get("access_id") or "").strip()
        altiplano_user = (data.get("altiplano_user") or data.get("nbi_user") or "").strip()
        altiplano_password = data.get("altiplano_password")
        if altiplano_password is not None and not isinstance(altiplano_password, str):
            altiplano_password = str(altiplano_password)
        if sitio:
            device_name = f"BA_OLTA_{sitio}"
        if device_name and lt and pon:
            fiber_name = f"{device_name}-{lt}-{pon}"

        required = {
            "operador": operador,
            "sitio": sitio,
            "device_name": device_name,
            "lt": lt,
            "pon": pon,
            "ont": ont,
            "vno": vno,
            "fiber_name": fiber_name,
            "access_id": access_id,
        }
        for key, val in required.items():
            if not val:
                return jsonify({"ok": False, "message": f"Parámetro {key} requerido"}), 400

        sess_token = _orquestador_session_token()
        has_body_creds = bool(altiplano_user) and (
            altiplano_password is not None and str(altiplano_password) != ""
        )

        if sess_token:
            out = crear_ont_connection_intent(
                operador=operador,
                entorno_nbi=entorno_nbi or "INP",
                device_name=device_name,
                lt=lt,
                pon=pon,
                ont=ont,
                vno=vno,
                fiber_name=fiber_name,
                access_id=access_id,
                pir=ONT_CONNECTION_PIR_FIXED,
                cir=ONT_CONNECTION_CIR_FIXED,
                nbi_bearer_token=sess_token,
            )
        elif has_body_creds:
            out = crear_ont_connection_intent(
                operador=operador,
                entorno_nbi=entorno_nbi or "INP",
                device_name=device_name,
                lt=lt,
                pon=pon,
                ont=ont,
                vno=vno,
                fiber_name=fiber_name,
                access_id=access_id,
                pir=ONT_CONNECTION_PIR_FIXED,
                cir=ONT_CONNECTION_CIR_FIXED,
                nbi_username=altiplano_user or None,
                nbi_password=altiplano_password,
            )
        else:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                    }
                ),
                401,
            )
        code = 201 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/consultar-intent", methods=["POST"])
    def dash_altiplano_consultar_intent():
        """Busca intents ont-connection en INP por device ``BA_OLTA_…`` o Access ID (no UUID de intent)."""
        data = request.get_json(silent=True) or {}
        device_name, by_id = _normalize_inp_device_by_id_fields_from_request(data)
        if not (device_name or "").strip() and not (by_id or "").strip():
            q_single = unicodedata.normalize("NFKC", (data.get("query") or "").strip())
            if q_single:
                device_name, by_id, q_err = classify_inp_consulta_query(q_single)
                if q_err:
                    return (
                        jsonify({"ok": False, "message": q_err, "matches": []}),
                        400,
                    )
        device_name, by_id = _inp_consulta_remap_ba_olta_from_by_id(device_name, by_id)

        access_filter = None
        if by_id:
            if _ALTIPLANO_INTENT_UUID_RE.match(by_id):
                return (
                    jsonify(
                        {
                            "ok": False,
                            "message": (
                                "La consulta solo admite Access ID o device/target; "
                                "no uses el UUID del intent en este campo."
                            ),
                            "matches": [],
                        }
                    ),
                    400,
                )
            if _ALTIPLANO_BY_ID_ACCESS_TOKEN_RE.match(by_id):
                access_filter = by_id
            else:
                return (
                    jsonify(
                        {
                            "ok": False,
                            "message": (
                                "El Access ID debe ser dígitos o identificador alfanumérico "
                                "(letras, números, _, -, .)"
                            ),
                            "matches": [],
                        }
                    ),
                    400,
                )

        advanced_raw = data.get("advanced_filters")
        advanced_filters: dict = advanced_raw if isinstance(advanced_raw, dict) else {}
        filter_rn = advanced_filters.get("required_network_state")
        filter_al = advanced_filters.get("alignment_state")
        if filter_rn is not None and not isinstance(filter_rn, list):
            filter_rn = None
        if filter_al is not None and not isinstance(filter_al, list):
            filter_al = None
        has_advanced = bool(filter_rn or filter_al)

        if has_advanced and inp_advanced_filters_active_aligned_blocked(filter_rn, filter_al):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "La combinación Active + Aligned no está permitida en búsqueda avanzada "
                            "(demasiados resultados). Usá Misaligned, otro estado RN o prefijo device."
                        ),
                        "matches": [],
                    }
                ),
                400,
            )

        if not device_name and not by_id and not has_advanced:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Indicá **device name**, **Access ID** o al menos un filtro en "
                            "búsqueda avanzada (estados RN / alineación)."
                        ),
                        "matches": [],
                    }
                ),
                400,
            )

        if (device_name or "").strip() and (by_id or "").strip():
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "En la consulta INP indicá un solo criterio: device name "
                            "(``BA_OLTA_…`` o ``BA_OLTA_…#3001#gpon``) **o** Access ID, no ambos."
                        ),
                        "matches": [],
                    }
                ),
                400,
            )

        if (device_name or "").strip() and not _inp_consulta_device_name_valid(device_name):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "El device name debe empezar por ``BA_OLTA_`` (prefijo antes del ``#`` "
                            "o target completo tipo ``BA_OLTA_…#3001#gpon``)."
                        ),
                        "matches": [],
                    }
                ),
                400,
            )

        inventory_resolution = None
        inventory_miss_fallback = False
        inv: dict | None = None
        # Inventario ATC: solo contexto en la respuesta (suggested target, VNO, etc.).
        # No acotamos el NBI a un solo device: la GUI puede listar varios intents con el mismo Access ID.
        if access_filter and not device_name:
            inv = resolver_target_ont_connection_por_access_id(access_filter)
            if inv.get("ok"):
                inventory_resolution = {k: v for k, v in inv.items() if k != "ok"}
            else:
                inventory_miss_fallback = True

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                        "matches": [],
                    }
                ),
                401,
            )

        aid_mode = (
            _access_id_match_mode_for_inp_consult(access_filter)
            if access_filter
            else "exact"
        )
        nbi_device_prefix = (device_name or "").strip() or None
        out = buscar_intents_ont_connection_inp(
            sess_token,
            device_prefix=nbi_device_prefix,
            access_id=access_filter,
            intent_uuid=None,
            access_id_match_mode=aid_mode,
            filter_required_network_state=filter_rn,
            filter_alignment_state=filter_al,
        )
        if inventory_resolution:
            out["inventory_resolution"] = inventory_resolution
        if inventory_miss_fallback:
            out["inventory_miss_fallback"] = True
        out = _enrich_consulta_inp_no_match(
            out,
            access_filter=access_filter,
            device_name=device_name,
            inventory_resolution=inventory_resolution,
            has_advanced_filters=has_advanced,
        )
        if access_filter:
            out = enriquecer_consulta_con_operador(
                out,
                access_id=access_filter,
                inventory_resolution=inventory_resolution,
                access_id_match_mode=aid_mode,
            )
        code = 200 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/sincronizar-intent", methods=["POST"])
    def dash_altiplano_sincronizar_intent():
        """POST operación IBN equivalente a «Synchronize intent» en la GUI (un solo match)."""
        data = request.get_json(silent=True) or {}
        vno = _vno_mutacion_from_request(data)
        if vno and vno.get("error"):
            body, st = vno["error"]
            return jsonify(body), st
        if vno and vno.get("vno"):
            out = sincronizar_intent_nbi(
                vno["operator"],
                target=vno["target"],
                intent_type=vno["intent_type"],
            )
            code = 200 if out.get("ok") else 502
            if not out.get("ok"):
                code = _http_code_for_borrado_payload(out)
            return jsonify(out), code

        ctx = _inp_intent_mutacion_context(data)
        if ctx.get("error"):
            body, st = ctx["error"]
            return jsonify(body), st

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                        "matches": [],
                    }
                ),
                401,
            )

        out = sincronizar_intent_ont_connection_inp(
            sess_token,
            device_prefix=ctx["device_prefix"],
            access_id=ctx["access_id"],
            intent_uuid=ctx["intent_uuid"],
        )
        if ctx.get("inventory_resolution"):
            out["inventory_resolution"] = ctx["inventory_resolution"]
        if ctx.get("inventory_miss_fallback"):
            out["inventory_miss_fallback"] = True
        code = 200 if out.get("ok") else 502
        if not out.get("ok"):
            code = _http_code_for_borrado_payload(out)
        return jsonify(out), code

    @app.route("/dashboard/altiplano/crear-ont-connection-faltante", methods=["POST"])
    def dash_altiplano_crear_ont_connection_faltante():
        """
        Crea el intent ``ont-connection`` que falta en L1 Scheduler (mismo Access ID de la consulta).

        El puerto ONT/LT/PON/VNO se obtiene del ``error-detail`` o del mensaje de sync fallido.
        """
        data = request.get_json(silent=True) or {}
        access_id = (data.get("access_id") or data.get("by_id") or "").strip()
        if not access_id:
            return (
                jsonify({"ok": False, "message": "Access ID requerido (mismo que en la consulta)"}),
                400,
            )

        err_text = (
            data.get("error_detail")
            or data.get("message")
            or data.get("error_message")
            or ""
        ).strip()
        missing = parse_l1_scheduler_missing_ont_connection(err_text)
        if not missing:
            miss_in = data.get("missing_ont_connection")
            if isinstance(miss_in, dict):
                missing = miss_in
        if not missing and data.get("device_name") and data.get("lt"):
            vno_raw = (data.get("vno") or data.get("vno_s") or "").strip()
            try:
                vno_n = int(vno_raw) if vno_raw else None
            except ValueError:
                vno_n = None
            device = (data.get("device_name") or "").strip()
            lt_s = (data.get("lt") or "").strip()
            pon_s = (data.get("pon") or "").strip()
            ont_s = (data.get("ont") or "").strip()
            if device and lt_s and pon_s and ont_s and vno_n:
                missing = {
                    "device_name": device,
                    "lt": lt_s,
                    "pon": pon_s,
                    "ont": ont_s,
                    "vno": vno_n,
                    "vno_s": str(vno_n),
                    "fiber_name": f"{device}-{lt_s}-{pon_s}",
                    "target": f"{device}-{lt_s}-{pon_s}-{ont_s}#{vno_n}#gpon",
                }

        if not missing:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "No se pudo interpretar la ubicación faltante en L1 Scheduler. "
                            "Usá una fila con error-detail o el mensaje completo de sync fallido."
                        ),
                    }
                ),
                400,
            )

        vno_n = missing.get("vno")
        operador = (data.get("operador") or "").strip().upper()
        if not operador and vno_n is not None:
            operador = (OPERADORES.get(int(vno_n)) or "").upper()
        if not operador:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": f"VNO {vno_n} sin operador mapeado en la suite; indicá operador en la petición.",
                    }
                ),
                400,
            )

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                    }
                ),
                401,
            )

        out = crear_ont_connection_intent(
            operador=operador,
            entorno_nbi="INP",
            device_name=str(missing["device_name"]),
            lt=str(missing["lt"]),
            pon=str(missing["pon"]),
            ont=str(missing["ont"]),
            vno=str(missing.get("vno_s") or missing.get("vno")),
            fiber_name=str(missing["fiber_name"]),
            access_id=access_id,
            pir=ONT_CONNECTION_PIR_FIXED,
            cir=ONT_CONNECTION_CIR_FIXED,
            nbi_bearer_token=sess_token,
        )
        if out.get("ok"):
            out["missing_ont_connection"] = missing
            out["access_id"] = access_id
            out["message"] = (
                f"ONT Connection creada en {out.get('target') or missing.get('target')} "
                f"con Access ID {access_id}. Podés sincronizar de nuevo."
            )
        code = 200 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/corregir-dependencias-l1", methods=["POST"])
    def dash_altiplano_corregir_dependencias_l1():
        """
        Crea en cadena ONT Connections faltantes en L1 (mismo Access ID) y sincroniza
        hasta alinear el intent consultado.
        """
        data = request.get_json(silent=True) or {}
        access_id = (data.get("access_id") or data.get("by_id") or "").strip()
        if not access_id:
            return jsonify({"ok": False, "message": "Access ID requerido"}), 400

        ctx = _inp_intent_mutacion_context(data)
        if ctx.get("error"):
            body, st = ctx["error"]
            return jsonify(body), st

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                    }
                ),
                401,
            )

        err_text = (
            data.get("error_detail")
            or data.get("message")
            or data.get("error_message")
            or ""
        ).strip()
        try:
            max_steps = int(data.get("max_steps") or 8)
        except (TypeError, ValueError):
            max_steps = 8

        out = corregir_dependencias_l1_y_alinear_intent_inp(
            sess_token,
            access_id=access_id,
            device_prefix=ctx["device_prefix"],
            intent_uuid=ctx["intent_uuid"],
            error_detail=err_text or None,
            max_steps=max_steps,
            pir=ONT_CONNECTION_PIR_FIXED,
            cir=ONT_CONNECTION_CIR_FIXED,
        )
        code = 200 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/actualizar-required-network-state", methods=["POST"])
    def dash_altiplano_actualizar_required_network_state():
        """PATCH ``required-network-state`` (equivalente a «Modify intent» en la GUI)."""
        data = request.get_json(silent=True) or {}
        rn = (data.get("required_network_state") or data.get("requiredNetworkState") or "").strip()
        if not rn:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Indicá required_network_state (active, suspended, not-present, delete)",
                        "matches": [],
                    }
                ),
                400,
            )

        vno = _vno_mutacion_from_request(data)
        if vno and vno.get("error"):
            body, st = vno["error"]
            return jsonify(body), st
        if vno and vno.get("vno"):
            out = actualizar_required_network_state_nbi(
                vno["operator"],
                rn,
                target=vno["target"],
                intent_type=vno["intent_type"],
            )
            code = 200 if out.get("ok") else 502
            if not out.get("ok"):
                code = _http_code_for_borrado_payload(out)
            return jsonify(out), code

        ctx = _inp_intent_mutacion_context(data)
        if ctx.get("error"):
            body, st = ctx["error"]
            return jsonify(body), st

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                        "matches": [],
                    }
                ),
                401,
            )

        out = actualizar_required_network_state_ont_connection_inp(
            sess_token,
            rn,
            device_prefix=ctx["device_prefix"],
            access_id=ctx["access_id"],
            intent_uuid=ctx["intent_uuid"],
        )
        if ctx.get("inventory_resolution"):
            out["inventory_resolution"] = ctx["inventory_resolution"]
        if ctx.get("inventory_miss_fallback"):
            out["inventory_miss_fallback"] = True
        code = 200 if out.get("ok") else 502
        if not out.get("ok"):
            code = _http_code_for_borrado_payload(out)
        return jsonify(out), code

    @app.route("/dashboard/altiplano/tasa-composite-profile-suggestions", methods=["POST"])
    def dash_altiplano_tasa_composite_profile_suggestions():
        """Sugerencias GUI TASA (autocomplete) para perfiles HSI tasa-composite."""
        data = request.get_json(silent=True) or {}
        target = (data.get("target") or "").strip()
        operator = (data.get("operator") or "TASA").strip().upper()
        kind = (data.get("kind") or data.get("profile_kind") or "").strip().lower()
        if not target:
            vno = _vno_mutacion_from_request(data)
            if vno and not vno.get("error") and vno.get("vno"):
                target = (vno.get("target") or "").strip()
                operator = (vno.get("operator") or operator).strip().upper()
        if not target or kind not in ("upstream", "downstream", "traffic", "shaper"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Indicá target y kind (upstream o downstream)",
                        "profiles": [],
                    }
                ),
                400,
            )
        tasa_hsi = data.get("tasa_hsi")
        if tasa_hsi is not None and not isinstance(tasa_hsi, dict):
            tasa_hsi = None
        query = (data.get("query") or data.get("searchQuery") or "").strip()
        out = tasa_composite_profile_suggestions_nbi(
            operator,
            target,
            kind,
            tasa_hsi=tasa_hsi,
            search_query=query,
        )
        code = 200 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/actualizar-tasa-composite-profiles", methods=["POST"])
    def dash_altiplano_actualizar_tasa_composite_profiles():
        """PATCH Shaper + Traffic Descriptor en intent ``tasa-composite`` (VNO TASA)."""
        data = request.get_json(silent=True) or {}
        vno = _vno_mutacion_from_request(data)
        if vno and vno.get("error"):
            body, st = vno["error"]
            return jsonify(body), st
        if not vno or not vno.get("vno"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Solo aplica en VNO (scope=vno, tasa-composite)",
                    }
                ),
                400,
            )
        if (vno.get("intent_type") or "").strip().lower() != "tasa-composite":
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Solo para intent-type tasa-composite",
                    }
                ),
                400,
            )
        hsi = data.get("tasa_hsi") if isinstance(data.get("tasa_hsi"), dict) else {}
        downstream = (
            data.get("downstream_profile")
            or data.get("shaper_profile")
            or hsi.get("downstream_profile")
            or ""
        )
        upstream = (
            data.get("upstream_profile")
            or data.get("traffic_descriptor_profile")
            or hsi.get("upstream_profile")
            or ""
        )
        out = actualizar_tasa_composite_profiles_nbi(
            vno["operator"],
            vno["target"],
            downstream_profile=str(downstream).strip(),
            upstream_profile=str(upstream).strip(),
        )
        code = 200 if out.get("ok") else 502
        return jsonify(out), code

    @app.route("/dashboard/altiplano/reinyectar-tasa-composite", methods=["POST"])
    def dash_altiplano_reinyectar_tasa_composite():
        """Borra y recrea un intent ``tasa-composite`` en el NBI del operador (TASA)."""
        data = request.get_json(silent=True) or {}
        vno = _vno_mutacion_from_request(data)
        if vno and vno.get("error"):
            body, st = vno["error"]
            return jsonify(body), st
        if not vno or not vno.get("vno"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Reinyección solo aplica en VNO (scope=vno, tasa-composite)",
                    }
                ),
                400,
            )
        if (vno.get("intent_type") or "").strip().lower() != "tasa-composite":
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Reinyección solo para intent-type tasa-composite",
                    }
                ),
                400,
            )
        tasa_hsi = data.get("tasa_hsi")
        if tasa_hsi is not None and not isinstance(tasa_hsi, dict):
            tasa_hsi = None
        out = reinyectar_tasa_composite_nbi(
            vno["operator"],
            vno["target"],
            tasa_hsi=tasa_hsi,
        )
        code = 200 if out.get("ok") else 502
        if not out.get("ok") and out.get("phase") == "delete":
            code = _http_code_for_borrado_payload(out)
        return jsonify(out), code

    @app.route("/dashboard/altiplano/borrar-intent", methods=["POST"])
    def dash_altiplano_borrar_intent():
        """Elimina un intent en INP (cascada VNO) o solo en VNO si ``scope=vno``."""
        data = request.get_json(silent=True) or {}
        vno = _vno_mutacion_from_request(data)
        if vno and vno.get("error"):
            body, st = vno["error"]
            return jsonify(body), st
        if vno and vno.get("vno"):
            out = borrar_intent_nbi(
                vno["operator"],
                target=vno["target"],
                intent_type=vno["intent_type"],
            )
            code = _http_code_for_borrado_payload(out)
            return jsonify(out), code

        device_name = (data.get("device_name") or "").strip()
        by_id = (data.get("by_id") or data.get("id") or "").strip()
        svlan = (data.get("svlan") or data.get("SVLAN") or "").strip() or None

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                    }
                ),
                401,
            )

        out = _borrar_ont_connection_desde_campos(
            sess_token, device_name, by_id, svlan=svlan
        )
        code = _http_code_for_borrado_payload(out)
        return jsonify(out), code

    @app.route("/dashboard/altiplano/borrar-intent-lote", methods=["POST"])
    def dash_altiplano_borrar_intent_lote():
        """Borrado masivo: lista de device names o de Access IDs (un valor por fila en archivo)."""
        data = request.get_json(silent=True) or {}
        mode = (data.get("mode") or "").strip().lower()
        raw_items = data.get("items")
        if raw_items is None:
            raw_items = data.get("lines") or []
        if mode not in ("device", "access"):
            return (
                jsonify({"ok": False, "message": "Modo inválido: indicá device o access"}),
                400,
            )
        if not isinstance(raw_items, list):
            return jsonify({"ok": False, "message": "Se esperaba una lista en items"}), 400

        items: list[str] = []
        for x in raw_items:
            s = str(x).strip()
            if s:
                items.append(s)
        if not items:
            return jsonify({"ok": False, "message": "La lista está vacía"}), 400
        if len(items) > ALTIPLANO_BORRADO_LOTE_MAX_ITEMS:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": f"Máximo {ALTIPLANO_BORRADO_LOTE_MAX_ITEMS} filas por lote",
                    }
                ),
                400,
            )

        sess_token = _orquestador_session_token()
        if not sess_token:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": (
                            "Sesión Orquestador no iniciada. "
                            "Ingresá con tu usuario Altiplano (INP) desde la pantalla de login."
                        ),
                        "results": [],
                    }
                ),
                401,
            )

        results = []
        ok_n = 0
        fail_n = 0
        for idx, token in enumerate(items, start=1):
            if mode == "device":
                row_out = _borrar_ont_connection_desde_campos(sess_token, token, "")
            else:
                row_out = _borrar_ont_connection_desde_campos(sess_token, "", token)
            row_ok = bool(row_out.get("ok"))
            if row_ok:
                ok_n += 1
            else:
                fail_n += 1
            results.append(
                {
                    "index": idx,
                    "input": token,
                    "ok": row_ok,
                    "message": row_out.get("message") or "",
                    "target": row_out.get("target"),
                }
            )

        summary_ok = fail_n == 0
        msg = f"Lote: {ok_n} borrado(s) OK, {fail_n} error(es)."
        return (
            jsonify(
                {
                    "ok": summary_ok,
                    "message": msg,
                    "mode": mode,
                    "total": len(items),
                    "ok_count": ok_n,
                    "fail_count": fail_n,
                    "results": results,
                }
            ),
            200,
        )

    @app.route("/dashboard/camino-optico/consultar", methods=["POST"])
    def dash_camino_optico_consultar():
        """Dispatcher JSON para consultas del dashboard Camino Óptico."""
        data = request.get_json(silent=True) or {}
        tipo = (data.get("tipo") or "").strip().lower()
        valor = (data.get("valor") or "").strip()
        if not valor:
            return jsonify({"error": "Parámetro valor requerido"}), 400
        if not tipo or tipo == "auto":
            tipo = infer_camino_consulta_tipo(valor) or ""
            if tipo == "access_id":
                valor = re.sub(r"\s+", "", valor)
            if not tipo:
                return (
                    jsonify(
                        {
                            "error": (
                                "No se reconoce el formato. Usá «FATC» (CTO), «RATC» (rama), "
                                "solo dígitos (Access ID), un LT tipo BA_OLTA_….LT1, "
                                "o sitio / región (ej. Moreno, MR01, sitio:Tigre)."
                            ),
                        }
                    ),
                    400,
                )
        else:
            if tipo in ("access_id", "aid", "id"):
                valor = re.sub(r"\s+", "", valor)
        try:
            if tipo == "cto":
                return jsonify(dashboard_camino_optico_cto(valor))
            if tipo == "rama":
                return jsonify(dashboard_camino_optico_rama(valor))
            if tipo in ("access_id", "aid", "id"):
                return jsonify(dashboard_camino_optico_access_id(valor))
            if tipo == "lt":
                return jsonify(dashboard_camino_optico_lt(valor))
            if tipo in ("equipo", "olt"):
                return jsonify(dashboard_camino_optico_equipo(valor))
            if tipo == "sitio":
                return jsonify(dashboard_camino_optico_sitio(valor))
            return jsonify(
                {
                    "error": (
                        "tipo inválido. Use: cto, rama, access_id, lt, equipo, sitio o auto"
                    )
                }
            ), 400
        except Exception:
            return _log_and_internal_error("Error al consultar camino óptico")

    @app.route("/dashboard/camino-optico/gis-por-lt", methods=["POST"])
    def dash_camino_optico_gis_por_lt():
        """GIS + marcadores para un LT (capas superpuestas en el mapa)."""
        data = request.get_json(silent=True) or {}
        lt = (data.get("lt") or "").strip()
        if not lt:
            return jsonify({"ok": False, "error": "Parámetro lt requerido"}), 400
        try:
            payload = gis_payload_para_lt(lt)
        except Exception:
            return _log_and_internal_error("Error al cargar GIS por LT")
        if not payload.get("ok"):
            return jsonify(payload), 400
        return jsonify(payload)

    @app.route("/dashboard/camino-optico/arbol-olt.json")
    def dash_camino_arbol_olt_json():
        """Jerarquía sitio → OLT → LT (misma data que dashboard OLT/LT) para mapa por casillas."""
        try:
            tree = dashboard_olts()
            return jsonify({"ok": True, "tree": tree})
        except Exception:
            return _log_and_internal_error("Error al cargar árbol OLT para Camino óptico")

    @app.route("/dashboard/camino-optico/gis", methods=["POST"])
    def dash_camino_optico_gis():
        """GeoJSON del camino óptico por rama (`cm.ci_op` o tabla configurada)."""
        data = request.get_json(silent=True) or {}
        valor = (data.get("valor") or data.get("rama") or "").strip()
        if not valor:
            return jsonify({"ok": False, "error": "Parámetro valor (rama) requerido"}), 400
        try:
            out = consultar_ci_op_por_rama(valor)
        except Exception:
            return _log_and_internal_error("Error interno consultando GIS Camino óptico")
        if not out.get("ok"):
            return jsonify(out), 400
        return jsonify(out)
