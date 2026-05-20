import html
import logging
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from urllib.parse import quote, urlencode

from config import (
    get_altiplano_power_workers,
    get_altiplano_credentials,
    get_altiplano_inp_intent_metadata_yang_version,
    get_altiplano_inp_intent_probe_http_timeout_s,
    get_altiplano_inp_intent_restconf_paths,
    get_altiplano_inp_search_http_timeout_s,
    get_altiplano_inp_wide_search_http_timeout_s,
    get_altiplano_nbi_target,
    get_altiplano_operator_credentials,
    get_altiplano_token_cache_max_age_seconds,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Cache de tokens: ``(auth_url, usuario) -> (token, monotonic_ts)``
_token_cache = {}
_ALTIPLANO_POWER_TARGETS_BY_OPERATOR_ID = {
    1001: ("tasa", "https://10.200.4.101:32443/tasa-altiplano-ac/rest/auth/login"),
    3001: ("dtv", "https://10.200.7.107:32443/dtv-altiplano-ac/rest/auth/login"),
    4000: ("metro", "https://10.200.5.102:32443/metro-altiplano-ac/rest/auth/login"),
    4010: ("metro", "https://10.200.5.102:32443/metro-altiplano-ac/rest/auth/login"),
    3950: ("iplan", "https://10.200.5.103:32444/iplan-altiplano-ac/rest/auth/login"),
    2800: ("atc", "https://10.200.5.105:32446/atc-altiplano-ac/rest/auth/login"),
    2805: ("atc", "https://10.200.5.105:32446/atc-altiplano-ac/rest/auth/login"),
    2806: ("atc", "https://10.200.5.105:32446/atc-altiplano-ac/rest/auth/login"),
}


def _extract_rpc_error_message_from_xml(xml_text: str) -> str | None:
    """Extrae ``error-message`` / ``devMessage`` de un ``rpc-reply`` NETCONF (GUI / netconf execute)."""
    raw = (xml_text or "").strip()
    if not raw:
        return None
    for tag in ("error-message", "devMessage"):
        m = re.search(
            rf"<{tag}[^>]*>(.*?)</{tag}>",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if m:
            text = html.unescape(m.group(1))
            text = text.replace("\\n", "\n").replace("\\r", "\r").strip()
            if text:
                return text
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    for el in root.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local in ("error-message", "devMessage") and (el.text or "").strip():
            return (el.text or "").strip()
    return None


def _extract_error_message_from_parsed_body(body: object) -> str:
    """Mensaje legible desde JSON Altiplano (RESTCONF, netconf execute con prefijo XSSI, etc.)."""
    if not isinstance(body, dict):
        return ""

    if body.get("error") is True:
        resp_xml = body.get("response")
        if isinstance(resp_xml, str):
            msg = _extract_rpc_error_message_from_xml(resp_xml)
            if msg:
                return msg[:2000]
        em = body.get("errorMessage")
        if em and str(em).strip() and str(em).strip().lower() != "rpc error":
            return str(em).strip()[:2000]

    err_list = body.get("error")
    if isinstance(err_list, list) and err_list:
        first = err_list[0]
        if isinstance(first, dict):
            msg = first.get("error-message") or first.get("errorMessage")
            if msg:
                return str(msg)[:2000]

    wrapped = body.get("ietf-restconf:errors") or body.get("errors")
    if isinstance(wrapped, dict):
        err_list = wrapped.get("error")
        if isinstance(err_list, list) and err_list and isinstance(err_list[0], dict):
            msg = err_list[0].get("error-message") or err_list[0].get("errorMessage")
            if msg:
                return str(msg)[:2000]

    msg = body.get("errors")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()[:2000]
    msg = body.get("error-message") or body.get("errorMessage")
    if msg:
        return str(msg)[:2000]
    return ""


def _split_altiplano_sync_error_message(full: str) -> tuple[str, str | None]:
    """Separa título («Sync failed…») y motivo («Reason: …») como en el diálogo de la GUI."""
    text = (full or "").strip()
    if not text:
        return "", None
    m = re.search(r"\bReason:\s*(.+)\s*$", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return text[: m.start()].strip(), m.group(1).strip()
    return text, None


_L1_SCHEDULER_MISSING_ONT_RE = re.compile(
    r"ont-connection intent does not exist for "
    r"(?P<vno>\d+)_(?P<device>BA_OLTA_[^-]+)-(?P<lt>\d+)-(?P<pon>\d+)-(?P<ont>\d+)_GPON",
    re.IGNORECASE,
)


def parse_l1_scheduler_missing_ont_connection(text: str) -> dict | None:
    """
  Parsea la clave L1 del mensaje Altiplano (GUI / sync / ``error-detail`` en consulta).

  Ej.: ``1001_BA_OLTA_ES01_01-9-4-11_GPON`` → device, lt, pon, ont, vno y target IBN.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    m = _L1_SCHEDULER_MISSING_ONT_RE.search(raw)
    if not m:
        return None
    device = m.group("device").strip()
    lt_s = m.group("lt")
    pon_s = m.group("pon")
    ont_s = m.group("ont")
    vno_s = m.group("vno")
    fiber = f"{device}-{lt_s}-{pon_s}"
    target = f"{device}-{lt_s}-{pon_s}-{ont_s}#{vno_s}#gpon"
    sitio = device[8:] if device.upper().startswith("BA_OLTA_") else ""
    return {
        "device_name": device,
        "lt": lt_s,
        "pon": pon_s,
        "ont": ont_s,
        "vno": int(vno_s),
        "vno_s": vno_s,
        "fiber_name": fiber,
        "target": target,
        "sitio": sitio,
    }


def _altiplano_error_payload_from_message(message: str) -> dict:
    title, detail = _split_altiplano_sync_error_message(message)
    out: dict = {"message": message}
    if title and title != message:
        out["error_title"] = title
    if detail:
        out["error_detail"] = detail
    missing = parse_l1_scheduler_missing_ont_connection(message)
    if not missing and detail:
        missing = parse_l1_scheduler_missing_ont_connection(detail)
    if missing:
        out["missing_ont_connection"] = missing
        out["can_create_missing_ont_connection"] = True
    return out


def _extract_altiplano_error_message(response: requests.Response) -> str:
    """Obtiene un mensaje de error breve desde una respuesta HTTP de Altiplano."""
    body = _json_loads_altiplano_http_response(response)
    if body is not None:
        msg = _extract_error_message_from_parsed_body(body)
        if msg:
            return msg
    try:
        body = response.json()
    except ValueError:
        msg = (response.text or "").strip()
        if msg.startswith(")]}',"):
            msg = msg[5:].lstrip("\n\r\t ")
        try:
            parsed = json.loads(msg) if msg.startswith("{") else None
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            extracted = _extract_error_message_from_parsed_body(parsed)
            if extracted:
                return extracted
        return msg[:2000] if msg else f"HTTP {response.status_code}"

    msg = _extract_error_message_from_parsed_body(body)
    if msg:
        return msg
    return str(body)[:2000]


def _obtener_token(auth_url, username=None, password=None, force_refresh=False):
    """
    Devuelve un token cacheado para Altiplano.
    Si no existe, autentica y lo guarda.

    La caché es por (auth_url, usuario) para no mezclar tokens entre credenciales distintas.
    """
    user_in = (username or "").strip() if username else ""
    pwd_in = password if isinstance(password, str) else (password or "")
    pwd_in = pwd_in if isinstance(pwd_in, str) else str(pwd_in)

    if user_in and pwd_in != "":
        user = user_in
        pwd = pwd_in
    else:
        user, pwd = get_altiplano_credentials()
        user = (user or "").strip()
        pwd = pwd or ""

    if not user or not pwd:
        logger.warning("ALTIPLANO_USER / ALTIPLANO_PASSWORD no configurados")
        return None

    cache_key = (auth_url, user)
    if force_refresh:
        _token_cache.pop(cache_key, None)

    if cache_key in _token_cache:
        token, ts = _token_cache[cache_key]
        max_age = get_altiplano_token_cache_max_age_seconds()
        if max_age > 0 and (time.monotonic() - ts) > max_age:
            _token_cache.pop(cache_key, None)
        else:
            return token

    auth = requests.post(
        auth_url, auth=(user, pwd), verify=False, timeout=60
    )
    if auth.status_code != 200:
        return None

    token = auth.json().get("accessToken")
    if token:
        _token_cache[cache_key] = (token, time.monotonic())
    return token


def obtener_token_entorno_nbi(entorno_nbi: str, username: str, password, *, force_refresh: bool = False):
    """
    Obtiene un Bearer token desde el endpoint de login REST del entorno NBI (ej. INP).

    Args:
        entorno_nbi: Clave de entorno compatible con `get_altiplano_nbi_target` (INP, TASA, …).
        username: Usuario Altiplano.
        password: Contraseña (se envía tal cual al POST de login).
        force_refresh: Si True, ignora la entrada en caché para ese usuario/auth_url.

    Returns:
        Token string o None si falla login o configuración.
    """
    op = str(entorno_nbi or "").strip().upper()
    if not op:
        return None
    host, port, base_url = get_altiplano_nbi_target(op)
    if not host or not port or not base_url:
        return None
    u = (username or "").strip()
    if not u:
        return None
    pwd = password if isinstance(password, str) else (password or "")
    pwd = pwd if isinstance(pwd, str) else str(pwd)
    if pwd == "":
        return None
    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"
    return _obtener_token(auth_url, username=u, password=pwd, force_refresh=force_refresh)


def cambiar_sn_ont(access_id, operador, ont_target, new_sn):
    """
    Cambia el serial esperado de una ONT en Altiplano.

    Args:
        access_id: Access ID asociado a la ONT.
        operador: Operador comercial (ej. TASA, DIRECTV).
        ont_target: Target técnico del intent ONT.
        new_sn: Nuevo serial a configurar.

    Returns:
        Dict con `ok` y `message`. En éxito también incluye `sn`.
    """
    aid = str(access_id or "").strip()
    op = str(operador or "").strip().upper()
    ont = str(ont_target or "").strip()
    raw_sn = str(new_sn or "").strip()
    if op == "TASA":
        from services.sn_tasa import normalize_tasa_change_sn

        sn = normalize_tasa_change_sn(raw_sn)
    else:
        sn = raw_sn.upper()

    if not aid:
        return {"ok": False, "message": "Access ID requerido"}
    if not ont:
        return {"ok": False, "message": "ONT target requerido"}
    if not sn:
        return {"ok": False, "message": "SN requerido"}
    if len(sn) < 6 or len(sn) > 32:
        return {"ok": False, "message": "SN inválido (largo fuera de rango)"}

    host, port, base_url = get_altiplano_nbi_target(op)
    if not host or not port or not base_url:
        return {"ok": False, "message": f"Operador no soportado para cambio SN: {op or 'N/A'}"}

    username, pwd = get_altiplano_operator_credentials(op)
    if not username or not pwd:
        return {"ok": False, "message": f"Credenciales no configuradas para operador {op}"}

    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"
    token = _obtener_token(auth_url, username=username, password=pwd)
    if not token:
        return {"ok": False, "message": "No se pudo autenticar contra Altiplano"}

    url = (
        f"https://{host}:{port}/{base_url}/rest/restconf/data/ibn:ibn/"
        f"intent={quote(ont, safe='')},ont?altiplano-triggerSyncUponSuccess=true"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json",
        "Content-Type": "application/yang-data+json",
    }
    payload = {
        "ibn:intent": {
            "intent-specific-data": {
                "ont:ont": {
                    "expected-serial-number": sn
                }
            }
        }
    }

    try:
        res = requests.patch(url, json=payload, headers=headers, verify=False, timeout=45)
    except requests.RequestException as ex:
        return {"ok": False, "message": f"Error de red hacia Altiplano: {ex}"}

    if res.status_code == 401:
        token = _obtener_token(
            auth_url,
            username=username,
            password=pwd,
            force_refresh=True,
        )
        if not token:
            return {"ok": False, "message": "Token expirado y no se pudo renovar"}
        headers["Authorization"] = f"Bearer {token}"
        try:
            res = requests.patch(url, json=payload, headers=headers, verify=False, timeout=45)
        except requests.RequestException as ex:
            return {"ok": False, "message": f"Error de red hacia Altiplano: {ex}"}

    if 200 <= res.status_code < 300:
        return {"ok": True, "message": "SN actualizado correctamente", "sn": sn}

    msg = _extract_altiplano_error_message(res)
    return {"ok": False, "message": f"Altiplano rechazó la operación: {msg}"}


def crear_ont_connection_intent(
    operador,
    entorno_nbi,
    device_name,
    lt,
    pon,
    ont,
    vno,
    fiber_name,
    access_id,
    pir=1000,
    cir=35,
    intent_type_version="11",
    nbi_username=None,
    nbi_password=None,
    nbi_bearer_token=None,
):
    """
    Crea un intent `ont-connection` en Altiplano.

    Args:
        operador: Operador de negocio (credenciales por operador si no hay UI).
        nbi_username / nbi_password: opcional; si ambos vienen informados, autentican
            contra el NBI en lugar de variables de entorno por operador.
        nbi_bearer_token: opcional; si viene informado, se usa como Bearer y no se llama al login.
        entorno_nbi: Entorno de destino NBI (por ejemplo INP).
        device_name: Equipo OLT lógico.
        lt: LT de la ONT.
        pon: PON de la ONT.
        ont: Índice/puerto ONT.
        vno: VNO a aplicar en el target.
        fiber_name: Nombre de fibra (normalmente derivado en backend/UI).
        access_id: Access ID comercial.
        pir: Perfil PIR a enviar en el intent.
        cir: Perfil CIR a enviar en el intent.
        intent_type_version: Versión del intent-type en Altiplano.

    Returns:
        Dict normalizado con `ok`, `message` y, en éxito, `target`.
        En caso de error de red o validación devuelve `ok=False`.
    """
    op = str(operador or "").strip().upper()
    nbi_env = str(entorno_nbi or "").strip().upper()
    device = str(device_name or "").strip()
    lt_s = str(lt or "").strip()
    pon_s = str(pon or "").strip()
    ont_s = str(ont or "").strip()
    vno_s = str(vno or "").strip()
    fiber = str(fiber_name or "").strip()
    aid = str(access_id or "").strip()
    ver = str(intent_type_version or "").strip() or "11"

    if not op:
        return {"ok": False, "message": "Operador requerido"}
    if not nbi_env:
        nbi_env = "INP"
    if not device:
        return {"ok": False, "message": "Device Name requerido"}
    if not lt_s or not pon_s or not ont_s:
        return {"ok": False, "message": "LT, PON y ONT son requeridos"}
    if not vno_s:
        return {"ok": False, "message": "VNO requerido"}
    if not fiber:
        return {"ok": False, "message": "Fiber Name requerido"}
    if not aid:
        return {"ok": False, "message": "Access ID requerido"}

    try:
        pir_n = int(pir)
        cir_n = int(cir)
    except (TypeError, ValueError):
        return {"ok": False, "message": "PIR/CIR inválidos"}
    if pir_n <= 0 or cir_n < 0:
        return {"ok": False, "message": "PIR/CIR fuera de rango"}

    host, port, base_url = get_altiplano_nbi_target(nbi_env)
    if not host or not port or not base_url:
        return {"ok": False, "message": f"Entorno NBI no soportado: {nbi_env}"}

    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"

    bearer_in = (nbi_bearer_token or "").strip() if nbi_bearer_token else ""
    username_for_refresh = None
    pwd_for_refresh = None
    token = None

    if bearer_in:
        token = bearer_in
    else:
        ui_user = (nbi_username or "").strip() if nbi_username else ""
        ui_pwd = nbi_password if isinstance(nbi_password, str) else (nbi_password or "")
        ui_pwd = ui_pwd if isinstance(ui_pwd, str) else str(ui_pwd)

        if ui_user and ui_pwd != "":
            username_for_refresh, pwd_for_refresh = ui_user, ui_pwd
        else:
            username_for_refresh, pwd_for_refresh = get_altiplano_operator_credentials(op)
            if not username_for_refresh or not pwd_for_refresh:
                return {"ok": False, "message": f"Credenciales no configuradas para operador {op}"}

        token = _obtener_token(
            auth_url, username=username_for_refresh, password=pwd_for_refresh
        )
        if not token:
            return {"ok": False, "message": "No se pudo autenticar contra Altiplano"}

    target = f"{device}-{lt_s}-{pon_s}-{ont_s}#{vno_s}#gpon"
    url = (
        f"https://{host}:{port}/{base_url}/rest/restconf/data/ibn:ibn"
        "?altiplano-triggerSyncUponSuccess=true"
    )
    logger.info(
        "Altiplano ont-connection request: operador=%s entorno=%s url=%s",
        op,
        nbi_env,
        url,
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json",
        "Content-Type": "application/yang-data+json",
    }
    payload = {
        "ibn:intent": {
            "target": target,
            "intent-type": "ont-connection",
            "intent-specific-data": {
                "ont-connection:ont-connection": {
                    "pir": pir_n,
                    "cir": cir_n,
                    "fiber-name": fiber,
                    "access-id": aid,
                }
            },
            "intent-type-version": ver,
            "required-network-state": "active",
        }
    }

    try:
        res = requests.post(url, json=payload, headers=headers, verify=False, timeout=45)
    except requests.RequestException as ex:
        return {"ok": False, "message": f"Error de red hacia Altiplano: {ex}"}

    if res.status_code == 401:
        if bearer_in:
            return {
                "ok": False,
                "message": "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar.",
            }
        token = _obtener_token(
            auth_url,
            username=username_for_refresh,
            password=pwd_for_refresh,
            force_refresh=True,
        )
        if not token:
            return {"ok": False, "message": "Token expirado y no se pudo renovar"}
        headers["Authorization"] = f"Bearer {token}"
        try:
            res = requests.post(url, json=payload, headers=headers, verify=False, timeout=45)
        except requests.RequestException as ex:
            return {"ok": False, "message": f"Error de red hacia Altiplano: {ex}"}

    if 200 <= res.status_code < 300:
        logger.info(
            "Altiplano ont-connection success: operador=%s entorno=%s status=%s",
            op,
            nbi_env,
            res.status_code,
        )
        return {
            "ok": True,
            "message": "ONT Connection creada correctamente",
            "target": target,
            "status_code": res.status_code,
        }

    msg = _extract_altiplano_error_message(res)
    logger.warning(
        "Altiplano ont-connection failed: operador=%s entorno=%s status=%s error=%s",
        op,
        nbi_env,
        res.status_code,
        msg,
    )
    fail: dict = {"ok": False, "message": f"Altiplano rechazó la operación: {msg}"}
    extra = _altiplano_error_payload_from_message(msg)
    for key, val in extra.items():
        if key != "message":
            fail[key] = val
    return fail


def _intent_access_id_from_entry(entry: dict) -> str:
    """Lee access-id dentro de intent-specific-data ont-connection."""
    isd = entry.get("intent-specific-data") or {}
    if not isinstance(isd, dict):
        return ""
    for key in ("ont-connection:ont-connection", "ont-connection"):
        block = isd.get(key)
        if isinstance(block, dict):
            aid = block.get("access-id") or block.get("access_id")
            if aid is not None and str(aid).strip() != "":
                return str(aid).strip()
    return ""


def _intent_uuid_from_entry(entry: dict) -> str:
    for key in ("uuid", "intent-id"):
        v = entry.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def _collect_ont_connection_intents(obj, out: list) -> None:
    """Recorre la respuesta RESTCONF y acumula nodos de intent ont-connection."""
    if isinstance(obj, dict):
        if obj.get("intent-type") == "ont-connection" and obj.get("target"):
            out.append(obj)
        for v in obj.values():
            _collect_ont_connection_intents(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_ont_connection_intents(item, out)


def _normalize_target_prefix(q: str) -> str:
    q = (q or "").strip()
    if not q:
        return ""
    if "#" in q:
        return q.split("#", 1)[0].strip()
    return q


def _target_head(target: str) -> str:
    t = (target or "").strip()
    if "#" in t:
        return t.split("#", 1)[0].strip()
    return t


def _access_id_likely_full_token_for_inp_consult(needle: str) -> bool:
    """
    True si el token parece un Access ID completo (no un prefijo corto de búsqueda).

    Heurística: segmento final tras el último ``_`` son dígitos y tiene longitud ≥ 3
    (ej. ``BORRAR_003``). Así ``RES_IP_8`` sigue siendo prefijo (solo un dígito).
    """
    q = (needle or "").strip()
    if "_" not in q:
        return False
    tail = q.rsplit("_", 1)[-1]
    return tail.isdigit() and len(tail) >= 3


def _access_id_match_mode_for_inp_consult(needle: str) -> str:
    """
    Modo de filtro Access ID en consulta INP (lectura), alineado a la GUI Altiplano.

    - Solo dígitos: coincidencia **exacta** (evita que ``12`` matchee ``1234567890``).
    - Token con forma de ID completo (p. ej. ``BORRAR_003``): **exacta**.
    - Resto de tokens alfanuméricos: **prefijo** (ej. ``BORRAR`` matchea ``BORRAR_003``).
    """
    q = (needle or "").strip()
    if not q:
        return "exact"
    if q.isdigit():
        return "exact"
    if _access_id_likely_full_token_for_inp_consult(q):
        return "exact"
    return "prefix"


def _intent_access_id_matches(aid: str, needle: str, mode: str) -> bool:
    a = (aid or "").strip()
    q = (needle or "").strip()
    if not q:
        return True
    if not a:
        return False
    if mode == "prefix":
        return a.lower().startswith(q.lower())
    return a == q


def _intent_matches_filters(
    entry: dict,
    *,
    device_prefix: str | None,
    access_id: str | None,
    intent_uuid: str | None,
    access_id_match_mode: str = "exact",
) -> bool:
    target = entry.get("target") or ""
    head = _target_head(target)
    aid = _intent_access_id_from_entry(entry)
    uid = _intent_uuid_from_entry(entry)

    ok_dev = True
    if device_prefix:
        dp = _normalize_target_prefix(device_prefix)
        if not dp:
            ok_dev = False
        else:
            ok_dev = head.startswith(dp) or head == dp

    ok_aid = True
    if access_id:
        ok_aid = _intent_access_id_matches(aid, access_id.strip(), access_id_match_mode)

    ok_uid = True
    if intent_uuid:
        ok_uid = uid.lower() == intent_uuid.strip().lower()

    return ok_dev and ok_aid and ok_uid


# Consulta **solo Access ID** sobre el listado global (sin ``device_prefix``): puede haber muchas
# coincidencias; no encadenar GET/``search-intents`` por cada fila (la UI queda en spinner hasta
# timeout). Tope de filas devueltas:
_INP_WIDE_ACCESS_QUERY_MATCH_LIMIT = 500


# Slice owner / VNO típicos INP (formulario Orquestador). Postman NBI usa el target
# ``{device}-{lt}-{pon}-{ont}#{VNO}#gpon``; si el usuario solo ingresa el prefijo antes
# del primer ``#``, probamos cada VNO con GET por instancia (colección INP - NBI).
_INP_ONT_CONNECTION_VNO_IDS = (
    "1001",
    "3001",
    "3950",
    "4000",
    "4010",
    "962",
    "963",
    "2800",
    "2805",
    "2806",
)

# GET por instancia: solo variantes necesarias para existencia (no ``content=all`` aquí — evita 4× latencia).
_RESTCONF_PROBE_PARAMS: tuple[dict, ...] = ({}, {"altiplano-target": "INP"})

# Tope de variantes de query en ``_try_alignment_from_ibn_yang_metadata_api`` (evita cadenas largas de GET).
_IBN_YANG_METADATA_MAX_PARAM_VARIANTS = 14

# Máximo de GET de sonda (alineación) por una sola consulta INP; el resto se omite con seguridad.
# Debe cubrir ~8 boosts + ~28 leafs + intentos ``ibn/yang`` (varias URLs × variantes de query).
_INP_INTENT_ALIGNMENT_PROBE_GET_BUDGET = 220

_BA_OLTA_PREFIX_RE = re.compile(
    r"^BA_OLTA_(?P<sitio>.+)-(?P<lt>\d+)-(?P<pon>\d+)-(?P<ont>\d+)$",
    re.IGNORECASE,
)


def _vno_from_ont_connection_target(query: str) -> str | None:
    """Extrae VNO de un target ``…#1001#gpon``."""
    m = re.search(r"#(\d+)#gpon\s*$", (query or "").strip(), re.IGNORECASE)
    return m.group(1) if m else None


def build_consulta_create_prefill(
    *,
    device_query: str | None = None,
    access_id: str | None = None,
    inventory_resolution: dict | None = None,
) -> dict | None:
    """
    Precarga el formulario «Crear ONT Connection» tras una consulta sin match en Altiplano.

    Usa inventario ATC (si está) para sitio/LT/PON/ONT/VNO; siempre incluye Access ID cuando se buscó por AID.
    """
    inv = inventory_resolution if isinstance(inventory_resolution, dict) else {}
    prefill: dict = {}
    aid = (access_id or "").strip()
    if aid:
        prefill["access_id"] = aid

    dq = (device_query or "").strip()
    target = (inv.get("suggested_target") or inv.get("device_name_for_query") or "").strip()
    loc = (inv.get("device_location_prefix") or "").strip()
    parse_q = target or loc or dq
    if parse_q and "#" in parse_q:
        parse_q = parse_q.split("#", 1)[0].strip()

    parsed = parse_ba_olta_device_prefix_for_form(parse_q) if parse_q else None
    if parsed:
        prefill.update(parsed)

    vno = _vno_from_ont_connection_target(target or dq)
    if not vno and inv.get("invocator_system") is not None:
        vno = str(inv["invocator_system"]).strip()
    if vno:
        prefill["vno"] = vno

    if not prefill:
        return None
    return prefill


def parse_ba_olta_device_prefix_for_form(device_query: str) -> dict | None:
    """
    Intenta derivar sitio / LT / PON / ONT desde un prefijo ``BA_OLTA_<sitio>-<lt>-<pon>-<ont>``
    (sin ``#VNO#gpon``). Si no coincide el patrón, devuelve None.
    """
    q = (device_query or "").strip()
    if not q:
        return None
    if "#" in q:
        q = q.split("#", 1)[0].strip()
    m = _BA_OLTA_PREFIX_RE.match(q)
    if not m:
        return None
    return {
        "sitio": m.group("sitio"),
        "lt": m.group("lt"),
        "pon": m.group("pon"),
        "ont": m.group("ont"),
    }


# RESTCONF (RFC 8040): sin ``content``, muchos NBIs devuelven solo ``config``; ``alignment-state``
# del intent suele ser estado operacional y no aparece — la UI de Altiplano sí lo muestra.
_RESTCONF_ALIGNMENT_BOOST_PARAMS: tuple[dict, ...] = (
    {"content": "all"},
    {"content": "all", "altiplano-target": "INP"},
    {"content": "nonconfig"},
    {"content": "nonconfig", "altiplano-target": "INP"},
    # Algunos AC exponen operacional solo con profundidad explícita
    {"content": "all", "depth": "unbounded"},
    {"content": "nonconfig", "depth": "unbounded"},
    # RFC 8528: exponer hojas con valor por defecto (a veces el estado operacional queda oculto)
    {"content": "all", "with-defaults": "report-all"},
    {"content": "nonconfig", "with-defaults": "report-all"},
)

# GET directo al leaf (algunos AC solo exponen estado operacional como sub-recurso RESTCONF).
# La GUI Altiplano suele llamar aparte ``ont-connection:ont-connection-state`` (estado vs. config).
_INP_ALIGNMENT_LEAF_SUFFIXES: tuple[str, ...] = (
    "ont-connection:ont-connection-state",
    "ont-connection-state",
    "alignment-state",
    "intent-alignment-state",
    "last-alignment-state",
    "ibn:alignment-state",
    "ibn:intent-alignment-state",
    "intent-operational-data",
    "ibn:intent-operational-data",
    "operational-state",
    "ibn:operational-state",
    "compliance-state",
    "ibn:compliance-state",
    "state",
    "ibn:state",
    "intent-state",
    "ibn:intent-state",
)


def _inp_ibn_yang_api_root_from_restconf_data_base(base_rest: str) -> str | None:
    """``.../rest/ibn/yang`` (sin ``/metadata`` ni ``/runtime``)."""
    marker = "/rest/restconf/data"
    if not base_rest or marker not in base_rest:
        return None
    prefix = base_rest.split(marker, 1)[0].rstrip("/")
    return f"{prefix}/rest/ibn/yang"


def _inp_ibn_yang_metadata_root_from_restconf_data_base(base_rest: str) -> str | None:
    """
    Raíz ``.../rest/ibn/yang/metadata`` derivada de ``base_rest`` (``.../rest/restconf/data``).

    La GUI Altiplano usa p. ej.::

        .../inp-altiplano-ac/rest/ibn/yang/metadata/ont-connection/11/data/ont-connection:ont-connection

    mientras el Orquestador usa RESTCONF bajo ``.../rest/restconf/data/...``.
    """
    root = _inp_ibn_yang_api_root_from_restconf_data_base(base_rest)
    return f"{root}/metadata" if root else None


def _json_loads_altiplano_http_response(res: requests.Response) -> object | None:
    """Parsea JSON de respuestas Altiplano; quita prefijo anti-XSSI ``)]}',`` usado por Angular."""
    text = (res.text or "").strip()
    if text.startswith(")]}',"):
        text = text[5:].lstrip("\n\r\t ")
    elif text.startswith(")]}'"):
        text = text[4:].lstrip("\n\r\t ")
    if not text:
        try:
            return res.json()
        except ValueError:
            return None
    try:
        return json.loads(text)
    except ValueError:
        try:
            return res.json()
        except ValueError:
            return None


def _looks_like_ibn_yang_field_metadata_document(obj: object) -> bool:
    """
    True si el JSON es el **modelo YANG** (descripciones, ``validValues``, etc.) y no datos
    de instancia (la GUI pide el mismo path ``.../metadata/.../ont-connection-state`` para eso).
    """
    if not isinstance(obj, dict):
        return False
    yp = obj.get("_yang-properties_")
    if isinstance(yp, dict) and yp.get("container-name"):
        return True
    n_leafish = 0
    n_meta = 0
    for k, v in obj.items():
        if not isinstance(k, str) or k.startswith("_yang"):
            continue
        if not isinstance(v, dict):
            continue
        n_leafish += 1
        if v.get("node") == "leaf":
            n_meta += 1
        if v.get("type") in (
            "enumeration",
            "string",
            "leafref",
            "union",
            "boolean",
            "uint32",
            "int32",
            "decimal64",
        ):
            n_meta += 1
        if "validValues" in v or "i18n-text" in v:
            n_meta += 1
    if n_leafish == 0:
        return False
    return n_meta >= max(2, int(n_leafish * 0.5))


def _pull_alignment_leaves_from_metadata_tree(
    obj: object, depth: int = 0, max_depth: int = 14
) -> dict[str, str]:
    """
    Recoge ``alignment-state`` / ``required-network-state`` en cualquier nivel del JSON
    de ``/rest/ibn/yang/metadata/.../ont-connection:ont-connection-state`` (la GUI no
    usa RESTCONF ``ietf-restconf:data`` en esta ruta).
    """
    acc: dict[str, str] = {}
    if depth > max_depth:
        return acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            lk = k.lower().replace("_", "-")
            if lk in (
                "alignment-state",
                "intent-alignment-state",
                "intentalignmentstate",
                "alignmentstate",
            ):
                got = _scalar_alignment_value(v)
                if got:
                    acc["alignment-state"] = got
            if lk in ("required-network-state", "required_network_state"):
                got = _scalar_alignment_value(v)
                if got:
                    acc["required-network-state"] = got
            sub = _pull_alignment_leaves_from_metadata_tree(v, depth + 1, max_depth)
            for sk, sv in sub.items():
                if not sv or not str(sv).strip():
                    continue
                if sk not in acc or not str(acc.get(sk) or "").strip():
                    acc[sk] = sv
    elif isinstance(obj, list):
        for item in obj:
            sub = _pull_alignment_leaves_from_metadata_tree(item, depth + 1, max_depth)
            for sk, sv in sub.items():
                if not sv or not str(sv).strip():
                    continue
                if sk not in acc or not str(acc.get(sk) or "").strip():
                    acc[sk] = sv
    return acc


def _apply_ibn_metadata_json_to_entry(entry: dict, extra: dict, tgt: str) -> bool:
    """Fusiona respuesta metadata IBN en ``entry``; devuelve True si ya hay alignment-state."""
    pulled = _pull_alignment_leaves_from_metadata_tree(extra)
    for mk, mv in pulled.items():
        if mv is not None and str(mv).strip():
            entry[mk] = mv
    entry = _absorb_intent_metadata(entry, extra)
    if not _intent_alignment_state_raw(entry):
        found = _deep_find_alignment_leaf(extra)
        if found:
            entry["alignment-state"] = found
    if not _intent_alignment_state_raw(entry):
        blob = _alignment_from_restconf_payload_for_target(extra, tgt)
        if blob:
            entry["alignment-state"] = blob
    if not _intent_alignment_state_raw(entry):
        hint = _harvest_hinted_alignment_from_tree(extra, 0, 24)
        if hint:
            entry["alignment-state"] = hint
    if not _intent_alignment_state_raw(entry):
        loose = _scan_loose_alignment_enum(extra, 0, 28)
        if loose:
            entry["alignment-state"] = loose
    return bool(_intent_alignment_state_raw(entry))


def _try_alignment_from_ibn_yang_metadata_api(
    base_rest: str, full_target: str, entry: dict, _get
) -> dict:
    """
    GET a **ibn/yang/runtime** y **ibn/yang/metadata** bajo ``.../rest/ibn/yang/``.

    ``metadata`` suele devolver el **modelo** YANG (hojas, ``validValues``), no el estado del
    intent; ``runtime`` (si existe en el AC) es el candidato a datos de instancia. Se ignora
    JSON que parezca catálogo de modelo.
    """
    if _intent_alignment_state_raw(entry):
        return entry
    api_root = _inp_ibn_yang_api_root_from_restconf_data_base(base_rest)
    if not api_root:
        return entry
    ver = get_altiplano_inp_intent_metadata_yang_version()

    tgt = (full_target or "").strip()
    uuid_val = (_intent_uuid_from_entry(entry) or "").strip()
    aid = (_intent_access_id_from_entry(entry) or "").strip()

    param_candidates: list[dict] = [{}]
    if tgt:
        head = tgt.split("#", 1)[0].strip() if "#" in tgt else ""
        param_candidates.extend(
            (
                {"target": tgt},
                {"targetKey": tgt},
                {"intentTarget": tgt},
                {"intent-target": tgt},
                {"key": tgt},
                {"intentKey": tgt},
            )
        )
        if head and head != tgt:
            param_candidates.append({"location": head})
            param_candidates.append({"device": head})
    if uuid_val:
        param_candidates.extend(
            (
                {"uuid": uuid_val},
                {"intentUuid": uuid_val},
                {"intent-uuid": uuid_val},
                {"id": uuid_val},
            )
        )
    if aid:
        param_candidates.extend(
            (
                {"access-id": aid},
                {"accessId": aid},
                {"access_id": aid},
                {"byId": aid},
            )
        )

    seen_sig: set[tuple[tuple[str, str], ...]] = set()
    uniq_params: list[dict] = []
    for p in param_candidates:
        sig = tuple(sorted((str(k), str(v)) for k, v in p.items()))
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        uniq_params.append(p)
    nonempty_param_variants = [p for p in uniq_params if p][: _IBN_YANG_METADATA_MAX_PARAM_VARIANTS]

    def _urls_for_store(store: str) -> tuple[str, str]:
        root = f"{api_root}/{store}"
        su = f"{root}/ont-connection/{ver}/data/ont-connection:ont-connection-state"
        cu = f"{root}/ont-connection/{ver}/data/ont-connection:ont-connection"
        return su, cu

    # ``runtime`` primero: ``metadata`` a menudo solo devuelve el catálogo YANG del tipo.
    for store in ("runtime", "metadata"):
        state_url, config_url = _urls_for_store(store)
        for data_url in (state_url, config_url):
            for probe in _RESTCONF_PROBE_PARAMS:
                res = _get(data_url, dict(probe))
                if isinstance(res, requests.RequestException):
                    continue
                if res.status_code != 200:
                    continue
                extra = _json_loads_altiplano_http_response(res)
                if not isinstance(extra, dict):
                    continue
                if _looks_like_ibn_yang_field_metadata_document(extra):
                    continue
                if _apply_ibn_metadata_json_to_entry(entry, extra, tgt):
                    return entry

        for data_url in (state_url, config_url):
            for params in nonempty_param_variants:
                for probe in _RESTCONF_PROBE_PARAMS:
                    merged = {**params, **probe}
                    res = _get(data_url, merged)
                    if isinstance(res, requests.RequestException):
                        continue
                    if res.status_code != 200:
                        continue
                    extra = _json_loads_altiplano_http_response(res)
                    if not isinstance(extra, dict):
                        continue
                    if _looks_like_ibn_yang_field_metadata_document(extra):
                        continue
                    if _apply_ibn_metadata_json_to_entry(entry, extra, tgt):
                        return entry
    return entry


def _try_alignment_leaf_subresources(
    base_rest: str, full_target: str, entry: dict, _get
) -> dict:
    """Si el GET del intent completo no trae alineación, prueba leafs bajo la misma instancia."""
    if _intent_alignment_state_raw(entry):
        return entry
    inst_rel = _inp_rel_path_ont_connection_instance(full_target)
    for suffix in _INP_ALIGNMENT_LEAF_SUFFIXES:
        leaf_url = f"{base_rest}/{inst_rel}/{suffix}"
        for req_params in _RESTCONF_PROBE_PARAMS:
            res = _get(leaf_url, req_params)
            if isinstance(res, requests.RequestException):
                continue
            if res.status_code != 200:
                continue
            try:
                extra = res.json()
            except ValueError:
                continue
            entry = _absorb_intent_metadata(entry, extra)
            if not _intent_alignment_state_raw(entry):
                found = _deep_find_alignment_leaf(extra)
                if found:
                    entry["alignment-state"] = found
            if _intent_alignment_state_raw(entry):
                return entry
    return _try_alignment_from_ibn_yang_metadata_api(base_rest, full_target, entry, _get)


def _maybe_enrich_alignment_from_restconf_get(
    base_rest: str, full_target: str, entry: dict, _get
) -> dict:
    """Si el GET por defecto no trae alineación, reintenta con ``content`` operacional y leafs."""
    if _intent_alignment_state_raw(entry):
        return entry
    url = f"{base_rest}/{_inp_rel_path_ont_connection_instance(full_target)}"
    for boost in _RESTCONF_ALIGNMENT_BOOST_PARAMS:
        res = _get(url, boost)
        if isinstance(res, requests.RequestException):
            continue
        if res.status_code != 200:
            continue
        try:
            extra = res.json()
        except ValueError:
            continue
        entry = _absorb_intent_metadata(entry, extra)
        if not _intent_alignment_state_raw(entry):
            found = _deep_find_alignment_leaf(extra)
            if found:
                entry["alignment-state"] = found
        if _intent_alignment_state_raw(entry):
            return entry
    return _try_alignment_leaf_subresources(base_rest, full_target, entry, _get)


def _inp_rel_path_ont_connection_instance(full_target: str) -> str:
    """
    Path RESTCONF para un intent ``ont-connection`` concreto (Northbound INP / Postman).

    Ejemplo::
        ibn:ibn/intent=BA_OLTA_ES01_01-1-1-7%231001%23gpon,ont-connection

    La clave de lista es compuesta (``target``, ``intent-type``), no UUID.
    """
    t = (full_target or "").strip()
    enc = t.replace("#", "%23")
    return f"ibn:ibn/intent={enc},ont-connection"


def _inp_restconf_operations_root_from_data_base(base_rest: str) -> str | None:
    """``.../rest/restconf/data`` → ``.../rest/restconf/operations``."""
    marker = "/rest/restconf/data"
    if not base_rest or marker not in base_rest:
        return None
    return base_rest.split(marker, 1)[0].rstrip("/") + "/rest/restconf/operations"


def _inp_search_intents_operation_url(base_rest: str) -> str | None:
    """URL de la operación RPC que usa la GUI INP (``ibn:search-intents``)."""
    root = _inp_restconf_operations_root_from_data_base(base_rest)
    if not root:
        return None
    return f"{root.rstrip('/')}/ibn:search-intents?history=false"


_INP_ADVANCED_SEARCH_PAGE_SIZE = 250
_INP_ADVANCED_SEARCH_MAX_MATCHES = 3000
_INP_ADVANCED_SEARCH_MAX_PAGES = 20
_INP_ADVANCED_RN_FILTER_VALUES = frozenset({"active", "suspended", "not-present"})
_INP_ADVANCED_AL_FILTER_VALUES = frozenset({"aligned", "misaligned"})


def _normalize_inp_advanced_rn_filters(raw: list | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip().lower().replace("_", "-")
        if s in _INP_ADVANCED_RN_FILTER_VALUES and s not in out:
            out.append(s)
    return out


_INP_RN_UI_TO_IBN_SERVER = {
    "active": "active",
    "suspended": "suspend",
    "not-present": "delete",
}


def _inp_rn_ui_to_ibn_server_values(ui_rn: list[str]) -> list[str]:
    """Mapea filtros del dashboard a hojas YANG de ``ibn:search-intents`` (GUI: ``suspend``, no ``suspended``)."""
    out: list[str] = []
    for v in ui_rn:
        sv = _INP_RN_UI_TO_IBN_SERVER.get(v)
        if sv and sv not in out:
            out.append(sv)
    return out


def _normalize_inp_advanced_al_filters(raw: list | None) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        s = str(item or "").strip().lower()
        if s in _INP_ADVANCED_AL_FILTER_VALUES and s not in out:
            out.append(s)
    return out


def inp_advanced_filters_active_aligned_blocked(
    filter_required_network_state: list[str] | None = None,
    filter_alignment_state: list[str] | None = None,
) -> bool:
    """Active + Aligned global en INP devuelve demasiados intents; no permitir en búsqueda avanzada."""
    rn = _normalize_inp_advanced_rn_filters(filter_required_network_state)
    al = _normalize_inp_advanced_al_filters(filter_alignment_state)
    return "active" in rn and "aligned" in al


def _inp_gui_filter_alignment_fields(filter_alignment_state: list[str] | None) -> dict:
    """
    Filtro de alineación como la GUI INP: ``aligned`` ``\"true\"``/``\"false\"`` y ``health`` vacío.

    Con ambos estados marcados no se envía ``aligned`` (la GUI lista aligned + misaligned).
    """
    al = _normalize_inp_advanced_al_filters(filter_alignment_state)
    fields: dict = {"health": []}
    if len(al) == 1:
        fields["aligned"] = "true" if al[0] == "aligned" else "false"
    return fields


def _inp_gui_search_intents_filter_body(
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    filter_required_network_state: list[str] | None = None,
    filter_alignment_state: list[str] | None = None,
    intent_type_version: str | None = None,
    page_number: int = 0,
    page_size: int = 250,
) -> dict:
    """
    Cuerpo ``ibn:search-intents`` alineado a la GUI INP (filtros ES + estados opcionales).

    ``target`` con prefijo device acota por location; ``argument`` access-id acota por abonado.
    """
    ver = (
        (intent_type_version or "").strip()
        or get_altiplano_inp_intent_metadata_yang_version()
        or "11"
    )
    dp = (device_prefix or "").strip()
    aid = (access_id or "").strip()
    rn_ui = _normalize_inp_advanced_rn_filters(filter_required_network_state)
    rn_server = _inp_rn_ui_to_ibn_server_values(rn_ui)
    argument: list[dict] = []
    if aid:
        argument = [{"name": "access-id", "config": True, "value": aid}]
    filter_block: dict = {
        "device-name": [],
        "target": dp if dp else [],
        "label": [],
        "config-required": True,
        "state-required": False,
        "predicate": "CONTAINS",
        "relative-object-id": [],
        "intent-type-list": [
            {
                "intent-type": "ont-connection",
                "intent-type-version": ver,
            }
        ],
        "required-network-state": rn_server,
        "argument": argument,
        "order-by-input": {"direction": "asc", "argument": "target"},
    }
    filter_block.update(_inp_gui_filter_alignment_fields(filter_alignment_state))
    return {
        "ibn:search-intents": {
            "search-from": "ES",
            "page-number": max(0, int(page_number)),
            "page-size": max(1, min(int(page_size), 500)),
            "filter": filter_block,
        }
    }


def _inp_gui_search_intents_body_by_access_id(
    access_id: str,
    *,
    intent_type_version: str | None = None,
    page_size: int = 250,
) -> dict:
    """Cuerpo ``ibn:search-intents`` por Access ID (compat. con consulta GUI clásica)."""
    return _inp_gui_search_intents_filter_body(
        access_id=access_id,
        intent_type_version=intent_type_version,
        page_size=page_size,
    )


def _search_intents_output_meta(body: dict) -> tuple[int | None, int | None]:
    """``(total_count, page_size)`` desde ``ibn:output`` si el AC los expone."""
    if not isinstance(body, dict):
        return None, None
    for wrap in ("ibn:output", "ietf-restconf:output", "output"):
        out = body.get(wrap)
        if not isinstance(out, dict):
            continue
        total = out.get("total-count")
        ps = out.get("page-size")
        try:
            total_i = int(total) if total is not None else None
        except (TypeError, ValueError):
            total_i = None
        try:
            ps_i = int(ps) if ps is not None else None
        except (TypeError, ValueError):
            ps_i = None
        if total_i is not None or ps_i is not None:
            return total_i, ps_i
    data_wrap = body.get("ietf-restconf:data")
    if isinstance(data_wrap, dict):
        return _search_intents_output_meta(data_wrap)
    return None, None


def _advanced_rn_filter_matches(match: dict, selected: list[str]) -> bool:
    if not selected:
        return True
    rn_yang = str(match.get("required_network_state") or "").strip().lower()
    ui = str(match.get("network_state") or "").strip().lower()
    for sel in selected:
        if sel == "active" and (rn_yang == "active" or ui == "active"):
            return True
        if sel == "suspended" and (
            rn_yang in ("suspended", "suspend") or ui == "suspended"
        ):
            return True
        if sel == "not-present" and (
            rn_yang in ("not-present", "delete", "deleted", "to-be-deleted")
            or ui == "not present"
        ):
            return True
    return False


def _advanced_al_filter_matches(match: dict, selected: list[str]) -> bool:
    if not selected:
        return True
    ui = str(match.get("alignment_state") or "").strip().lower()
    for sel in selected:
        if sel == "aligned" and ui in ("aligned", "in-sync", "insync", "compliant"):
            return True
        if sel == "misaligned" and ui in (
            "misaligned",
            "out-of-sync",
            "outsync",
            "non-compliant",
            "noncompliant",
            "violation",
            "violations",
        ):
            return True
    return False


def _filter_matches_advanced_states(
    matches: list[dict],
    *,
    filter_required_network_state: list[str] | None,
    filter_alignment_state: list[str] | None,
) -> list[dict]:
    rn_sel = _normalize_inp_advanced_rn_filters(filter_required_network_state)
    al_sel = _normalize_inp_advanced_al_filters(filter_alignment_state)
    if not rn_sel and not al_sel:
        return matches
    out: list[dict] = []
    for m in matches:
        if not isinstance(m, dict):
            continue
        if _advanced_rn_filter_matches(m, rn_sel) and _advanced_al_filter_matches(m, al_sel):
            out.append(m)
    return out


def buscar_ont_connection_inp_via_gui_filter_search(
    base_rest: str,
    headers: dict,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    access_id_match_mode: str = "exact",
    filter_required_network_state: list[str] | None = None,
    filter_alignment_state: list[str] | None = None,
    timeout_s: float = 90.0,
) -> tuple[list[dict], bool]:
    """
    Lista ``ont-connection`` vía ``ibn:search-intents`` con filtros de estado (GUI INP).

    Returns:
        ``(matches_normalizados, truncated)``
    """
    url = _inp_search_intents_operation_url(base_rest)
    if not url:
        return [], False
    post_headers = {
        **headers,
        "Content-Type": "application/yang-data+json",
        "Accept": "application/yang-data+json, application/json;q=0.9, */*;q=0.5",
    }
    matches: list[dict] = []
    truncated = False
    total_count: int | None = None
    for page in range(_INP_ADVANCED_SEARCH_MAX_PAGES):
        if len(matches) >= _INP_ADVANCED_SEARCH_MAX_MATCHES:
            truncated = True
            break
        body = _inp_gui_search_intents_filter_body(
            device_prefix=device_prefix,
            access_id=access_id,
            filter_required_network_state=filter_required_network_state,
            filter_alignment_state=filter_alignment_state,
            page_number=page,
            page_size=_INP_ADVANCED_SEARCH_PAGE_SIZE,
        )
        try:
            res = requests.post(
                url,
                headers=post_headers,
                json=body,
                verify=False,
                timeout=timeout_s,
            )
        except requests.RequestException:
            break
        if res.status_code == 401:
            break
        if res.status_code != 200:
            break
        data = _json_loads_altiplano_http_response(res)
        if not isinstance(data, dict) or isinstance(data.get("ietf-restconf:errors"), dict):
            break
        page_total, _ps = _search_intents_output_meta(data)
        if page_total is not None:
            total_count = page_total
        rows = _extract_intent_list_from_search_intents_response(data)
        if not rows:
            break
        for row in rows:
            if len(matches) >= _INP_ADVANCED_SEARCH_MAX_MATCHES:
                truncated = True
                break
            if (row.get("intent-type") or "").strip() != "ont-connection":
                continue
            if access_id and not _intent_access_id_matches(
                _access_id_from_search_intents_row(row),
                access_id.strip(),
                access_id_match_mode,
            ):
                continue
            if device_prefix:
                dp = _normalize_target_prefix(device_prefix)
                head = _target_head((row.get("target") or "").strip())
                if dp and not (head.startswith(dp) or head == dp):
                    continue
            entry = _search_intent_row_to_ont_connection_entry(row)
            if not (entry.get("target") or "").strip():
                continue
            matches.append(_match_entry_to_result_dict(entry))
        if truncated:
            break
        if total_count is not None and len(matches) >= total_count:
            break
        if len(rows) < _INP_ADVANCED_SEARCH_PAGE_SIZE:
            break
    matches = _filter_matches_advanced_states(
        matches,
        filter_required_network_state=filter_required_network_state,
        filter_alignment_state=filter_alignment_state,
    )
    return matches, truncated


def _search_intent_row_to_ont_connection_entry(row: dict) -> dict:
    """Normaliza una fila de ``search-intents`` a un entry compatible con ``_match_entry_to_result_dict``."""
    if not isinstance(row, dict):
        return {}
    entry = dict(row)
    al = _alignment_canonical_from_ibn_aligned_leaf(row.get("aligned"))
    if al:
        entry["alignment-state"] = al
    ed = row.get("error-detail") or row.get("error_detail")
    if ed:
        entry["error-detail"] = ed
    return entry


def buscar_ont_connection_inp_via_gui_access_id_search(
    base_rest: str,
    headers: dict,
    access_id: str,
    *,
    access_id_match_mode: str = "exact",
    timeout_s: float = 90.0,
) -> list[dict]:
    """
    Lista intents por Access ID vía ``POST ibn:search-intents`` (misma operación que la GUI).

    Returns:
        Lista de dicts normalizados (``_match_entry_to_result_dict``), puede tener varios targets.
    """
    aid = (access_id or "").strip()
    if not aid:
        return []
    url = _inp_search_intents_operation_url(base_rest)
    if not url:
        return []
    body = _inp_gui_search_intents_body_by_access_id(aid)
    post_headers = {
        **headers,
        "Content-Type": "application/yang-data+json",
        "Accept": "application/yang-data+json, application/json;q=0.9, */*;q=0.5",
    }
    try:
        res = requests.post(
            url,
            headers=post_headers,
            json=body,
            verify=False,
            timeout=timeout_s,
        )
    except requests.RequestException:
        return []
    if res.status_code == 401:
        return []
    if res.status_code != 200:
        return []
    data = _json_loads_altiplano_http_response(res)
    if not isinstance(data, dict) or isinstance(data.get("ietf-restconf:errors"), dict):
        return []
    rows = _extract_intent_list_from_search_intents_response(data)
    matches: list[dict] = []
    for row in rows:
        if (row.get("intent-type") or "").strip() != "ont-connection":
            continue
        row_aid = _access_id_from_search_intents_row(row)
        if not _intent_access_id_matches(row_aid, aid, access_id_match_mode):
            continue
        entry = _search_intent_row_to_ont_connection_entry(row)
        if not (entry.get("target") or "").strip():
            continue
        matches.append(_match_entry_to_result_dict(entry))
    return matches


def _extract_intent_list_from_search_intents_response(body: object) -> list[dict]:
    """Parsea ``ibn:output`` / ``ietf-restconf:output`` de la operación ``ibn:search-intents``."""
    if not isinstance(body, dict):
        return []
    data_wrap = body.get("ietf-restconf:data")
    if isinstance(data_wrap, dict):
        nested = _extract_intent_list_from_search_intents_response(data_wrap)
        if nested:
            return nested
    for wrap in ("ibn:output", "ietf-restconf:output", "output"):
        out = body.get(wrap)
        if not isinstance(out, dict):
            continue
        intents = out.get("intents")
        if isinstance(intents, list):
            return [x for x in intents if isinstance(x, dict)]
        if isinstance(intents, dict):
            intent = intents.get("intent")
            if isinstance(intent, list):
                return [x for x in intent if isinstance(x, dict)]
            if isinstance(intent, dict):
                return [intent]
        intent_top = out.get("intent")
        if isinstance(intent_top, list):
            return [x for x in intent_top if isinstance(x, dict)]
        if isinstance(intent_top, dict):
            return [intent_top]
    return []


def _alignment_canonical_from_ibn_aligned_leaf(val: object) -> str:
    """
    La GUI / RPC ``ibn:search-intents`` expone ``aligned`` como ``\"true\"`` / ``\"false\"`` (string),
    no ``alignment-state`` como en otros recursos RESTCONF.
    """
    if val is None:
        return ""
    if isinstance(val, bool):
        return "aligned" if val else "misaligned"
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "aligned"):
        return "aligned"
    if s in ("false", "0", "no", "misaligned"):
        return "misaligned"
    return ""


def _search_intents_rpc_input_variants(
    prefer_target: str | None,
    access_id: str | None,
    intent_uuid: str | None,
) -> list[dict]:
    """Variantes de ``ibn:input``; el AC acepta distintas formas según release."""
    bodies: list[dict] = []
    seen: set[str] = set()

    def add(b: dict) -> None:
        key = json.dumps(b, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            bodies.append(b)

    t = (prefer_target or "").strip()
    aid = (access_id or "").strip() if access_id else ""
    uid = (intent_uuid or "").strip() if intent_uuid else ""

    if t and t.count("#") >= 2:
        add({"ibn:input": {"intent-type": "ont-connection", "target": t}})
        add({"ibn:input": {"target": t}})
        add({"ibn:input": {"intent-type": "ont-connection", "intent-target": t}})
        add({"ibn:input": {"intent-type": "ont-connection", "intentTarget": t}})
        add({"ibn:input": {"criteria": {"target": t}}})
        add({"ibn:input": {"filter": {"target": t, "intent-type": "ont-connection"}}})
    if aid:
        add({"ibn:input": {"access-id": aid, "intent-type": "ont-connection"}})
        add({"ibn:input": {"intent-type": "ont-connection", "access-id": aid}})
    if uid:
        add({"ibn:input": {"uuid": uid, "intent-type": "ont-connection"}})
        add({"ibn:input": {"intent-uuid": uid, "intent-type": "ont-connection"}})
    return bodies


def _access_id_from_search_intents_row(row: dict) -> str:
    if not isinstance(row, dict):
        return ""
    block = row.get("intent-specific-data")
    if not isinstance(block, dict):
        return ""
    oc = block.get("ont-connection:ont-connection") or block.get("ont-connection")
    if not isinstance(oc, dict):
        return ""
    return str(oc.get("access-id") or "").strip()


def _pick_search_intents_row_for_entry(
    rows: list[dict],
    entry: dict,
    *,
    prefer_target: str | None,
) -> dict | None:
    """Elige la fila RPC que corresponde al intent ya resuelto por RESTCONF."""
    if not rows:
        return None
    want_t = (prefer_target or (entry.get("target") or "")).strip()
    want_aid = (_intent_access_id_from_entry(entry) or "").strip()
    want_uid = (
        str(entry.get("uuid") or entry.get("intent-id") or entry.get("intent_id") or "")
        .strip()
        .lower()
    )
    for row in rows:
        if (row.get("intent-type") or "").strip() != "ont-connection":
            continue
        rt = (row.get("target") or "").strip()
        if want_t and rt == want_t:
            return row
        if want_aid and _access_id_from_search_intents_row(row) == want_aid:
            return row
        ru = str(row.get("uuid") or row.get("intent-id") or "").strip().lower()
        if want_uid and ru and ru == want_uid:
            return row
    if len(rows) == 1 and want_t and (rows[0].get("target") or "").strip() == want_t:
        return rows[0]
    return None


def _merge_search_intents_row_into_entry(entry: dict, row: dict) -> dict:
    """Fusiona campos de listado IBN (alineación booleana, required-network-state, …)."""
    if not isinstance(entry, dict) or not isinstance(row, dict):
        return entry
    for k in ("required-network-state", "required_network_state"):
        if k not in row or row[k] is None:
            continue
        rv = row[k]
        rvs = str(rv).strip()
        if not rvs or rvs.lower() in ("null", "none"):
            continue
        cur = entry.get("required-network-state") or entry.get("required_network_state")
        if not str(cur or "").strip():
            entry["required-network-state"] = rv
        break
    if "aligned" in row and row["aligned"] is not None:
        entry["aligned"] = row["aligned"]
    return entry


def _enrich_intent_entry_via_search_intents_rpc(
    base_rest: str,
    entry: dict,
    *,
    prefer_target: str | None,
    access_id: str | None,
    intent_uuid: str | None,
    headers: dict,
    timeout_s: float,
) -> dict:
    """
    POST a ``ibn:search-intents`` (misma operación que la GUI) y fusiona ``aligned`` / estados.

    Sin esto, muchos AC solo devuelven alineación en el RPC y no en GET ``ibn:ibn/intent=…``.
    """
    if not isinstance(entry, dict):
        return entry
    url = _inp_search_intents_operation_url(base_rest)
    if not url:
        return entry
    post_headers = {
        **headers,
        "Content-Type": "application/yang-data+json",
    }
    for body in _search_intents_rpc_input_variants(prefer_target, access_id, intent_uuid):
        if not body.get("ibn:input"):
            continue
        try:
            res = requests.post(
                url,
                headers=post_headers,
                json=body,
                verify=False,
                timeout=timeout_s,
            )
        except requests.RequestException:
            continue
        if res.status_code == 401:
            break
        if res.status_code != 200:
            continue
        data = _json_loads_altiplano_http_response(res)
        if not isinstance(data, dict) or isinstance(data.get("ietf-restconf:errors"), dict):
            continue
        rows = _extract_intent_list_from_search_intents_response(data)
        if not rows:
            continue
        hit = _pick_search_intents_row_for_entry(rows, entry, prefer_target=prefer_target)
        if hit:
            return _merge_search_intents_row_into_entry(entry, hit)
    return entry


def _expand_ont_connection_targets_for_instance_get(device_prefix: str) -> list[str]:
    """Devuelve targets completos ``...#VNO#gpon`` para probar GET por instancia."""
    s = (device_prefix or "").strip()
    if not s:
        return []
    if s.count("#") >= 2:
        return [s]
    return [f"{s}#{vno}#gpon" for vno in _INP_ONT_CONNECTION_VNO_IDS]


def _unwrap_restconf_data_layer(payload):
    """
    RESTCONF ``application/yang-data+json`` suele envolver el recurso en ``ietf-restconf:data``.
    Sin desenvolver, campos como ``alignment-state`` quedan en el wrapper y no los ve coerce/absorb.
    """
    if not isinstance(payload, dict):
        return payload
    inner = payload.get("ietf-restconf:data")
    if isinstance(inner, dict):
        return inner
    return payload


def _coerce_ont_connection_get_payload_to_intent(entry_payload: dict, full_target: str) -> dict:
    """
    Unifica la respuesta de GET (intent completo o solo ``ont-connection:ont-connection``).
    """
    if not isinstance(entry_payload, dict):
        return {
            "target": full_target,
            "intent-type": "ont-connection",
            "intent-specific-data": {},
        }
    entry_payload = _unwrap_restconf_data_layer(entry_payload)
    if entry_payload.get("intent-type") == "ont-connection" and entry_payload.get("target"):
        return entry_payload
    inner = entry_payload.get("ibn:intent")
    if isinstance(inner, list):
        for item in inner:
            if isinstance(item, dict) and item.get("intent-type") == "ont-connection":
                return item
    elif isinstance(inner, dict) and inner.get("intent-type") == "ont-connection":
        return inner
    inner_intent = entry_payload.get("intent")
    if isinstance(inner_intent, list):
        for item in inner_intent:
            if isinstance(item, dict) and item.get("intent-type") == "ont-connection":
                return item
    elif isinstance(inner_intent, dict) and inner_intent.get("intent-type") == "ont-connection":
        return inner_intent
    oc_block = entry_payload.get("ont-connection:ont-connection") or entry_payload.get(
        "ont-connection"
    )
    if isinstance(oc_block, dict):
        return {
            "target": full_target,
            "intent-type": "ont-connection",
            "intent-specific-data": {"ont-connection:ont-connection": oc_block},
        }
    return {
        "target": full_target,
        "intent-type": "ont-connection",
        "intent-specific-data": entry_payload,
    }


_INTENT_UI_NETWORK = {
    "active": "Active",
    "not-present": "Not present",
    "not present": "Not present",
    "suspended": "Suspended",
    "suspend": "Suspended",
    # Yang / IBN: intent marcado para borrado — misma lectura que «Not present» en la UI Nokia
    "delete": "Not present",
    "deleted": "Not present",
    "to-be-deleted": "Not present",
    "tobedeleted": "Not present",
}

_INTENT_UI_ALIGNMENT = {
    "aligned": "Aligned",
    "misaligned": "Misaligned",
    "in-sync": "Aligned",
    "out-of-sync": "Misaligned",
    "insync": "Aligned",
    "outsync": "Misaligned",
    # El NBI suele devolver esto cuando aún no hay auditoría; no confundir con «sin dato» (—).
    "unknown": "Unknown",
    "undefined": "Undefined",
    "compliant": "Aligned",
    "non-compliant": "Misaligned",
    "noncompliant": "Misaligned",
    "violation": "Misaligned",
    "violations": "Misaligned",
}

# Valores de string que aceptamos en escaneo amplio (solo bajo subárboles de intent / payload acotado).
_KNOWN_ALIGNMENT_VALUE_STRINGS: frozenset[str] = frozenset(
    (
        "aligned",
        "misaligned",
        "in-sync",
        "out-of-sync",
        "match",
        "matched",
        "no-match",
        "nomatch",
        "drift",
        "drifted",
        "consistent",
        "inconsistent",
        "satisfied",
        "unsatisfied",
    )
)


def _absorb_intent_metadata(entry: dict, raw_payload: dict) -> dict:
    """
    Copia del JSON RESTCONF campos de estado del intent (required/alignment) que a veces vienen
    en el envelope ``ibn:intent`` y no en el bloque coerced.
    """
    if not isinstance(entry, dict) or not isinstance(raw_payload, dict):
        return entry
    unwrapped = _unwrap_restconf_data_layer(raw_payload)
    layers: list = []
    seen: set[int] = set()

    def _push_layer(d: dict) -> None:
        i = id(d)
        if i in seen:
            return
        seen.add(i)
        layers.append(d)

    _push_layer(raw_payload)
    if isinstance(unwrapped, dict) and unwrapped is not raw_payload:
        _push_layer(unwrapped)
    for root in (raw_payload, unwrapped):
        if not isinstance(root, dict):
            continue
        for key in ("ibn:intent", "intent"):
            inner = root.get(key)
            if isinstance(inner, list):
                for item in inner:
                    if isinstance(item, dict):
                        _push_layer(item)
            elif isinstance(inner, dict):
                _push_layer(inner)
    merge_keys = (
        "required-network-state",
        "required_network_state",
        "alignment-state",
        "alignment_state",
        "intent-alignment-state",
        "last-alignment-state",
        "ibn:alignment-state",
        "ibn:intent-alignment-state",
        # Respuestas JSON con camelCase (Northbound / runtime Nokia)
        "intentAlignmentState",
        "lastIntentAlignmentState",
        "alignmentState",
        "uuid",
        "intent-id",
    )
    for layer in layers:
        for mk in merge_keys:
            if mk not in layer or layer[mk] is None:
                continue
            cur = entry.get(mk)
            if mk not in entry or cur is None or (isinstance(cur, str) and not str(cur).strip()):
                entry[mk] = layer[mk]

    # Alineación / required a menudo bajo ``ont-connection:ont-connection-state`` (o dentro del
    # bloque ``ont-connection:ont-connection``), no en la raíz del layer.
    _STATE_WRAP_KEYS = ("ont-connection:ont-connection-state", "ont-connection-state")
    _OC_BLOCK_KEYS = ("ont-connection:ont-connection", "ont-connection")
    for layer in layers:
        nested_roots: list[dict] = [layer]
        for obk in _OC_BLOCK_KEYS:
            ob = layer.get(obk)
            if isinstance(ob, dict):
                nested_roots.append(ob)
        for src in nested_roots:
            for swk in _STATE_WRAP_KEYS:
                blk = src.get(swk)
                if not isinstance(blk, dict):
                    continue
                for mk in merge_keys:
                    if mk in ("uuid", "intent-id"):
                        continue
                    if mk not in blk or blk[mk] is None:
                        continue
                    cur = entry.get(mk)
                    if mk not in entry or cur is None or (isinstance(cur, str) and not str(cur).strip()):
                        entry[mk] = blk[mk]

    # Claves de runtime no listadas en merge_keys (revisiones YANG / Nokia)
    if not str(entry.get("alignment-state") or "").strip():
        for layer in layers:
            for ck, cv in layer.items():
                if not isinstance(ck, str) or ck in merge_keys:
                    continue
                if not _key_looks_like_alignment_state(ck):
                    continue
                got = _scalar_alignment_value(cv)
                if got:
                    entry["alignment-state"] = got
                    break
            if str(entry.get("alignment-state") or "").strip():
                break
    return entry


def _key_looks_like_alignment_state(k: str) -> bool:
    """NBI/Nokia devuelve a veces kebab-case YANG, a veces camelCase en JSON (p. ej. ``intentAlignmentState``)."""
    lk = k.lower().replace("_", "-")
    kl = k.lower()
    if "alignment-state" in lk or "intent-alignment" in lk:
        return True
    if lk.endswith("-alignment") or lk == "alignment":
        return True
    # camelCase / API interna: contiene «alignment» y «state» (p. ej. intentAlignmentState, lastAlignmentState)
    if "alignment" in kl and "state" in kl:
        return True
    # Claves runtime sin «state» explícito (p. ej. intentAlignment, operationalAlignment)
    if "alignment" in kl and "health" not in kl:
        if "parameter" in kl or "chassis" in kl:
            return False
        return True
    if "compliance-state" in lk or ("compliance" in lk and "state" in lk):
        return True
    if "synchronization" in lk and "state" in lk:
        return True
    if "sync-state" in lk or lk == "sync-state":
        return True
    return False


def _collect_ont_connection_intent_dicts_matching_target(obj, target: str, out: list) -> None:
    """Acumula nodos JSON de intent ``ont-connection`` cuyo ``target`` coincide (para leer estado en subárbol)."""
    want = (target or "").strip()
    if not want:
        return
    if isinstance(obj, dict):
        if obj.get("intent-type") == "ont-connection" and (obj.get("target") or "").strip() == want:
            out.append(obj)
        for v in obj.values():
            _collect_ont_connection_intent_dicts_matching_target(v, target, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_ont_connection_intent_dicts_matching_target(item, target, out)


def _scan_loose_alignment_enum(obj, depth: int = 0, max_depth: int = 22) -> str:
    """
    Busca cadenas ``aligned`` / ``misaligned`` / ``in-sync`` / ``out-of-sync`` en cualquier hoja.
    Solo usar sobre subárboles acotados (un intent o respuesta GET única), no listados globales enormes.
    """
    if depth > max_depth or obj is None:
        return ""
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, str) and v.strip():
                ls = v.strip().lower().replace("_", "-")
                if ls in _KNOWN_ALIGNMENT_VALUE_STRINGS:
                    return ls
            sub = _scan_loose_alignment_enum(v, depth + 1, max_depth)
            if sub:
                return sub
    elif isinstance(obj, list):
        for item in obj:
            sub = _scan_loose_alignment_enum(item, depth + 1, max_depth)
            if sub:
                return sub
    return ""


def _alignment_context_key_strict(ks: str) -> bool:
    """Claves que casi siempre indican estado de alineación / auditoría del intent."""
    if not isinstance(ks, str) or not ks.strip():
        return False
    kl = ks.lower().replace("_", "-")
    if "parameter" in kl or "chassis" in kl:
        return False
    return any(
        p in kl
        for p in (
            "align",
            "compliance",
            "harmony",
            "audit",
            "drift",
            "mismatch",
            "deviation",
            "reconcil",
            "verification",
            "realiz",
            "intent-status",
            "intentstatus",
        )
    ) or ("sync" in kl and "async" not in kl)


def _alignment_context_key_generic(ks: str) -> bool:
    """Claves ambiguas: solo se usan con valores tipo MATCH / NO_MATCH."""
    if not isinstance(ks, str) or not ks.strip():
        return False
    kl = ks.lower().replace("_", "-")
    return kl in ("status", "state", "result", "outcome")


def _normalize_vendor_alignment_to_canonical(raw: str, *, strict_key: bool) -> str:
    """Convierte tokens de distintas releases NBI a ``aligned`` / ``misaligned`` / ``in-sync`` / ``out-of-sync``."""
    if not raw or not isinstance(raw, str):
        return ""
    tail = raw.strip().rsplit(":", 1)[-1].strip().lower().replace("_", "-").replace(" ", "-")
    if not tail:
        return ""
    if tail in ("aligned", "misaligned", "in-sync", "out-of-sync"):
        return tail
    if tail in ("match", "matched", "consistent", "satisfied"):
        return "aligned"
    if tail in ("no-match", "nomatch", "drift", "drifted", "inconsistent", "unsatisfied"):
        return "misaligned"
    if tail.upper() == "MATCH":
        return "aligned"
    if tail.upper() in ("NO_MATCH", "NO-MATCH", "NOMATCH"):
        return "misaligned"
    if strict_key:
        if tail in ("pass", "passed", "success", "ok"):
            return "aligned"
        if tail in ("fail", "failed", "error", "nok"):
            return "misaligned"
        if tail in ("true", "false"):
            return "aligned" if tail == "true" else "misaligned"
    return ""


def _harvest_hinted_alignment_from_tree(obj: object, depth: int = 0, max_depth: int = 28) -> str:
    """Último recurso: strings bajo claves que sugieren auditoría / alineación (p. ej. ``MATCH`` / ``NO_MATCH``)."""
    if depth > max_depth or obj is None:
        return ""
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k) if isinstance(k, str) else ""
            strict = _alignment_context_key_strict(ks)
            generic = _alignment_context_key_generic(ks)
            if isinstance(v, str) and v.strip():
                if strict:
                    got = _normalize_vendor_alignment_to_canonical(v.strip(), strict_key=True)
                    if got:
                        return got
                if generic:
                    got = _normalize_vendor_alignment_to_canonical(v.strip(), strict_key=False)
                    if got:
                        return got
            if isinstance(v, (dict, list)):
                sub = _harvest_hinted_alignment_from_tree(v, depth + 1, max_depth)
                if sub:
                    return sub
    elif isinstance(obj, list):
        for item in obj:
            sub = _harvest_hinted_alignment_from_tree(item, depth + 1, max_depth)
            if sub:
                return sub
    return ""


def _alignment_from_restconf_payload_for_target(payload: object, target: str) -> str:
    """
    Extrae alineación del JSON NBI: primero el nodo intent con ese ``target``, si no hay nodo
    (p. ej. GET que solo devuelve ``ont-connection:ont-connection``), barre el payload acotado.
    """
    if not isinstance(payload, dict):
        return ""
    roots: list = [payload]
    inner = _unwrap_restconf_data_layer(payload)
    if isinstance(inner, dict) and inner is not payload:
        roots.append(inner)
    hits: list = []
    for r in roots:
        _collect_ont_connection_intent_dicts_matching_target(r, target, hits)
    for subtree in hits:
        al = _intent_alignment_state_raw(subtree)
        if al:
            return al
        al = _deep_find_alignment_leaf(subtree)
        if al:
            return al
        al = _scan_loose_alignment_enum(subtree, 0, 18)
        if al:
            return al
    if hits:
        return ""
    for r in roots:
        al = _deep_find_alignment_leaf(r)
        if al:
            return al
        al = _scan_loose_alignment_enum(r, 0, 26)
        if al:
            return al
        al = _harvest_hinted_alignment_from_tree(r, 0, 30)
        if al:
            return al
    return ""


def _scalar_from_yang_identity_like_dict(d: dict) -> str:
    """
    RESTCONF/YANG a veces codifica identityref u hojas tipadas como dict (clave cualificada
    o valor con prefijo de módulo) en lugar de string plano.
    """
    if not isinstance(d, dict) or len(d) > 12:
        return ""
    known = frozenset(
        (
            "aligned",
            "misaligned",
            "in-sync",
            "out-of-sync",
            "unknown",
            "undefined",
        )
    )
    for key, val in d.items():
        if isinstance(key, str):
            tail = key.rsplit(":", 1)[-1].strip().lower().replace("_", "-")
            if tail in known:
                return tail
        if isinstance(val, str) and val.strip():
            leaf = val.strip().rsplit(":", 1)[-1].strip().lower().replace("_", "-")
            if leaf in known:
                return leaf
        if val in ((), [], [None], {}) and isinstance(key, str) and ":" in key:
            tail = key.rsplit(":", 1)[-1].strip().lower().replace("_", "-")
            if tail in known:
                return tail
    return ""


def _scalar_alignment_value(v) -> str:
    if isinstance(v, list):
        for item in v:
            got = _scalar_alignment_value(item)
            if got:
                return got
        return ""
    if isinstance(v, (str, int, float, bool)) and str(v).strip():
        return str(v).strip()
    if isinstance(v, dict):
        for subk in ("#text", "value", "@value", "state"):
            sv = v.get(subk)
            if isinstance(sv, (str, int, float, bool)) and str(sv).strip():
                return str(sv).strip()
        id_guess = _scalar_from_yang_identity_like_dict(v)
        if id_guess:
            return id_guess
    return ""


def _deep_find_alignment_leaf(obj, depth: int = 0, max_depth: int = 24) -> str:
    """Último recurso: primer valor escalar bajo una clave que sugiera alignment-state."""
    if depth > max_depth:
        return ""
    if depth == 0 and isinstance(obj, dict):
        obj = _unwrap_restconf_data_layer(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            if _key_looks_like_alignment_state(k):
                got = _scalar_alignment_value(v)
                if got:
                    return got
                if isinstance(v, dict):
                    sub = _deep_find_alignment_leaf(v, depth + 1, max_depth)
                    if sub:
                        return sub
            elif isinstance(v, (dict, list)):
                sub = _deep_find_alignment_leaf(v, depth + 1, max_depth)
                if sub:
                    return sub
    elif isinstance(obj, list):
        for item in obj:
            sub = _deep_find_alignment_leaf(item, depth + 1, max_depth)
            if sub:
                return sub
    return ""


def _intent_alignment_state_raw(entry: dict) -> str:
    for k in (
        "alignment-state",
        "intent-alignment-state",
        "last-alignment-state",
        "ibn:alignment-state",
        "ibn:intent-alignment-state",
        "alignment_state",
        "intentAlignmentState",
        "lastIntentAlignmentState",
        "alignmentState",
    ):
        v = entry.get(k)
        if v is None:
            continue
        got = _scalar_alignment_value(v)
        if got:
            return got
    syn = _alignment_canonical_from_ibn_aligned_leaf(entry.get("aligned"))
    if syn:
        return syn
    return (
        _deep_find_alignment_leaf(entry)
        or _scan_loose_alignment_enum(entry, 0, 16)
        or _harvest_hinted_alignment_from_tree(entry, 0, 22)
    )


def _format_intent_ui_label(raw: str, mapping: dict) -> str:
    if raw is None or str(raw).strip() == "":
        return "—"
    s = str(raw).strip().lower()
    if s in mapping:
        return mapping[s]
    # fallback legible (ej. valores Yang no mapeados)
    return str(raw).strip().replace("-", " ").title()


def _match_entry_rn_edit_allowed(rn_raw: str) -> bool:
    """¿Habilitar lápiz «cambiar required network state» en consulta INP? Active → no."""
    if rn_raw is None or str(rn_raw).strip() == "":
        return False
    s = str(rn_raw).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in s:
        s = s.replace("--", "-")
    if s == "active":
        return False
    return s in frozenset(
        {
            "suspended",
            "suspend",
            "not-present",
            "notpresent",
            "delete",
            "deleted",
            "to-be-deleted",
            "tobedeleted",
        }
    )


def _match_entry_to_result_dict(entry: dict) -> dict:
    rn_raw = (
        entry.get("required-network-state") or entry.get("required_network_state") or ""
    )
    rn_raw = str(rn_raw).strip() if rn_raw else ""
    al_raw = _intent_alignment_state_raw(entry)
    tgt = (entry.get("target") or "").strip()
    ed_raw = entry.get("error-detail") or entry.get("error_detail") or ""
    ed_raw = str(ed_raw).strip() if ed_raw else ""
    missing_l1 = parse_l1_scheduler_missing_ont_connection(ed_raw) if ed_raw else None
    return {
        "target": tgt,
        # Misma clave que en la GUI NBI: Location Name#Slice Owner Name#PON Type
        "location_slice_pon": tgt or None,
        "access_id": _intent_access_id_from_entry(entry),
        "intent_uuid": _intent_uuid_from_entry(entry),
        "intent_type": entry.get("intent-type") or "ont-connection",
        "required_network_state": rn_raw or None,
        "network_state": _format_intent_ui_label(rn_raw, _INTENT_UI_NETWORK),
        "alignment_state": _format_intent_ui_label(al_raw, _INTENT_UI_ALIGNMENT),
        "error_detail": ed_raw or None,
        "missing_ont_connection": missing_l1,
        "can_create_missing_ont_connection": bool(missing_l1),
        "rn_edit_allowed": _match_entry_rn_edit_allowed(rn_raw),
    }


def _buscar_is_wide_access_only_global_list(
    device_prefix: str | None, access_id: str | None
) -> bool:
    """True si la búsqueda recorre el árbol global filtrando solo por Access ID (sin acotar device)."""
    return bool((access_id or "").strip()) and not (device_prefix or "").strip()


def buscar_intents_ont_connection_inp(
    nbi_bearer_token: str,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    intent_uuid: str | None = None,
    access_id_match_mode: str = "exact",
    filter_required_network_state: list[str] | None = None,
    filter_alignment_state: list[str] | None = None,
) -> dict:
    """
    Lista intents ``ont-connection`` en INP vía RESTCONF y filtra en cliente.

    La **GUI Altiplano** usa además la operación ``ibn:search-intents`` (POST), que devuelve
    ``aligned`` / ``required-network-state`` por fila; el Orquestador fusiona esa salida cuando
    el GET por instancia no trae ``alignment-state``.

    Prioridad (Northbound INP / colección Postman *INP - NBI*):

    1. ``GET .../ibn:ibn/intent=<target_con_%23>,ont-connection`` — la lista se indexa por
       ``(target, intent-type)``, no por UUID. Si el usuario ingresa solo el prefijo del
       device (antes del primer ``#``), se prueba cada VNO habitual con ese GET.
    2. Si hace falta listado global o UUID, se mantienen los intentos previos sobre
       ``ibn:ibn`` / ``ibn:intent`` y variantes de query.

    Returns:
        Dict con ``ok``, ``matches`` (lista de dicts normalizados) y ``message``.

    ``access_id_match_mode``: ``exact`` (default, mutaciones) o ``prefix`` (consulta INP con token
    alfanumérico, alineado a la GUI Altiplano para ``BORRAR`` vs ``BORRAR_003``).
    """
    token = (nbi_bearer_token or "").strip()
    if not token:
        return {"ok": False, "message": "Token requerido", "matches": []}

    rn_filters = _normalize_inp_advanced_rn_filters(filter_required_network_state)
    al_filters = _normalize_inp_advanced_al_filters(filter_alignment_state)
    has_advanced_filters = bool(rn_filters or al_filters)

    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Entorno NBI INP no configurado", "matches": []}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json, application/json;q=0.9, text/plain;q=0.8, */*;q=0.5",
    }
    base_rest = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    path_list = get_altiplano_inp_intent_restconf_paths()
    search_http_timeout_s = get_altiplano_inp_search_http_timeout_s()
    wide_access_only = _buscar_is_wide_access_only_global_list(device_prefix, access_id)
    list_fetch_timeout_s = (
        get_altiplano_inp_wide_search_http_timeout_s()
        if wide_access_only
        else search_http_timeout_s
    )
    probe_http_timeout_s = get_altiplano_inp_intent_probe_http_timeout_s()
    probe_get_budget = [0]

    def _get(url: str, req_params):
        try:
            return requests.get(
                url,
                headers=headers,
                params=req_params,
                verify=False,
                timeout=list_fetch_timeout_s,
            )
        except requests.RequestException as ex:
            return ex

    def _get_probe(url: str, req_params):
        if probe_get_budget[0] >= _INP_INTENT_ALIGNMENT_PROBE_GET_BUDGET:

            class _Skipped:
                status_code = 499

            return _Skipped()
        probe_get_budget[0] += 1
        try:
            return requests.get(
                url,
                headers=headers,
                params=req_params,
                verify=False,
                timeout=probe_http_timeout_s,
            )
        except requests.RequestException as ex:
            return ex

    matches_out: list = []
    tried_instance_probe = False

    def _advanced_filter_summary() -> str:
        parts: list[str] = []
        if rn_filters:
            parts.append("RN: " + ", ".join(rn_filters))
        if al_filters:
            parts.append("alineación: " + ", ".join(al_filters))
        return "; ".join(parts)

    def _finish_advanced_search(matches: list[dict], truncated: bool, scope: str) -> dict:
        n = len(matches)
        summary = _advanced_filter_summary()
        msg = f"{n} intent(s) ont-connection"
        if scope:
            msg += f" ({scope})"
        if summary:
            msg += f" con filtros [{summary}]"
        if truncated:
            msg += f" (tope {_INP_ADVANCED_SEARCH_MAX_MATCHES}; acotá con device o Access ID)"
        if n == 1:
            msg = msg.replace("intent(s)", "intent", 1)
        return {
            "ok": True,
            "message": msg,
            "matches": matches,
            "search_source": "gui-search-intents-advanced",
            "advanced_filters": {
                "required_network_state": rn_filters,
                "alignment_state": al_filters,
            },
            "truncated": truncated,
        }

    # --- 0a) Solo filtros de estado (sin device ni Access ID): búsqueda global ES
    if has_advanced_filters and not (device_prefix or "").strip() and not (access_id or "").strip():
        gui_matches, truncated = buscar_ont_connection_inp_via_gui_filter_search(
            base_rest,
            headers,
            filter_required_network_state=rn_filters,
            filter_alignment_state=al_filters,
            timeout_s=float(search_http_timeout_s),
        )
        if not gui_matches:
            return {
                "ok": True,
                "message": "Sin intents ont-connection para los filtros indicados.",
                "matches": [],
                "no_match": True,
                "search_source": "gui-search-intents-advanced",
                "advanced_filters": {
                    "required_network_state": rn_filters,
                    "alignment_state": al_filters,
                },
            }
        return _finish_advanced_search(gui_matches, truncated, "búsqueda global INP")

    # --- 0b) Access ID sin device: ``ibn:search-intents`` como la GUI (varios targets posibles)
    if wide_access_only and (access_id or "").strip():
        if has_advanced_filters:
            gui_matches, truncated = buscar_ont_connection_inp_via_gui_filter_search(
                base_rest,
                headers,
                access_id=access_id.strip(),
                access_id_match_mode=access_id_match_mode,
                filter_required_network_state=rn_filters,
                filter_alignment_state=al_filters,
                timeout_s=float(search_http_timeout_s),
            )
            if not gui_matches:
                return {
                    "ok": True,
                    "message": "No existe ese Access ID en Altiplano para los filtros indicados.",
                    "matches": [],
                    "no_match": True,
                    "suggest_create": True,
                    "consulta_criterion": "access_id",
                    "search_source": "gui-search-intents-advanced",
                }
            return _finish_advanced_search(
                gui_matches, truncated, f"Access ID {access_id.strip()}"
            )
        gui_matches = buscar_ont_connection_inp_via_gui_access_id_search(
            base_rest,
            headers,
            access_id.strip(),
            access_id_match_mode=access_id_match_mode,
            timeout_s=float(search_http_timeout_s),
        )
        if gui_matches:
            n = len(gui_matches)
            aid_show = access_id.strip()
            return {
                "ok": True,
                "message": (
                    f"{n} intent(s) encontrado(s) para Access ID {aid_show}"
                    if n != 1
                    else f"1 intent encontrado para Access ID {aid_show}"
                ),
                "matches": gui_matches,
                "search_source": "gui-search-intents",
            }
        return {
            "ok": True,
            "message": "No existe ese Access ID en Altiplano",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "access_id",
        }

    # --- 0c) Device + filtros de estado: ``search-intents`` con target CONTAINS
    if device_prefix and not intent_uuid and has_advanced_filters and not (access_id or "").strip():
        gui_matches, truncated = buscar_ont_connection_inp_via_gui_filter_search(
            base_rest,
            headers,
            device_prefix=device_prefix.strip(),
            filter_required_network_state=rn_filters,
            filter_alignment_state=al_filters,
            timeout_s=float(search_http_timeout_s),
        )
        if gui_matches:
            return _finish_advanced_search(gui_matches, truncated, f"device {device_prefix.strip()}")
        dp = device_prefix.strip()
        prefill = parse_ba_olta_device_prefix_for_form(dp) if dp else None
        out_prefill = dict(prefill) if prefill else {}
        vno = _vno_from_ont_connection_target(dp)
        if vno:
            out_prefill["vno"] = vno
        return {
            "ok": True,
            "message": "Sin intents ont-connection para ese device y los filtros indicados.",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "device_name",
            "create_prefill": out_prefill or None,
            "search_source": "gui-search-intents-advanced",
        }

    # --- 1) GET por instancia (Postman: Search > Get ont-connection)
    if device_prefix and not intent_uuid:
        tried_instance_probe = True
        targets_try = _expand_ont_connection_targets_for_instance_get(device_prefix)
        stop_on_access_hit = bool(access_id)
        for ft in targets_try:
            rel = _inp_rel_path_ont_connection_instance(ft)
            url = f"{base_rest}/{rel}"
            got_payload = None
            for req_params in _RESTCONF_PROBE_PARAMS:
                res = _get(url, req_params)
                if isinstance(res, requests.RequestException):
                    return {"ok": False, "message": f"Error de red hacia Altiplano: {res}", "matches": []}
                if res.status_code == 401:
                    return {
                        "ok": False,
                        "message": (
                            "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                        ),
                        "matches": [],
                    }
                if res.status_code == 200:
                    try:
                        got_payload = res.json()
                        break
                    except ValueError:
                        return {"ok": False, "message": "Respuesta JSON inválida de Altiplano", "matches": []}
                if res.status_code == 404:
                    continue
            if got_payload is None:
                continue
            entry = _coerce_ont_connection_get_payload_to_intent(got_payload, ft)
            entry = _absorb_intent_metadata(entry, got_payload)
            if not _intent_alignment_state_raw(entry):
                found_al = _alignment_from_restconf_payload_for_target(got_payload, ft)
                if found_al:
                    entry["alignment-state"] = found_al
            entry = _maybe_enrich_alignment_from_restconf_get(base_rest, ft, entry, _get_probe)
            entry = _enrich_intent_entry_via_search_intents_rpc(
                base_rest,
                entry,
                prefer_target=ft,
                access_id=access_id,
                intent_uuid=intent_uuid,
                headers=headers,
                timeout_s=float(search_http_timeout_s),
            )
            if _intent_matches_filters(
                entry,
                device_prefix=device_prefix,
                access_id=access_id,
                intent_uuid=intent_uuid,
                access_id_match_mode=access_id_match_mode,
            ):
                matches_out.append(_match_entry_to_result_dict(entry))
                if stop_on_access_hit and _intent_access_id_matches(
                    _intent_access_id_from_entry(entry),
                    access_id or "",
                    access_id_match_mode,
                ):
                    break

        if matches_out:
            if has_advanced_filters:
                matches_out = _filter_matches_advanced_states(
                    matches_out,
                    filter_required_network_state=rn_filters,
                    filter_alignment_state=al_filters,
                )
            return {
                "ok": True,
                "message": (
                    f"{len(matches_out)} intent(s) encontrado(s)"
                    if len(matches_out) != 1
                    else "1 intent encontrado"
                ),
                "matches": matches_out,
            }

    if tried_instance_probe and not matches_out:
        dp = (device_prefix or "").strip()
        prefill = parse_ba_olta_device_prefix_for_form(dp) if dp else None
        out_prefill = dict(prefill) if prefill else {}
        vno = _vno_from_ont_connection_target(dp)
        if vno:
            out_prefill["vno"] = vno
        return {
            "ok": True,
            "message": "No existe ese Device Name en Altiplano",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "device_name",
            "create_prefill": out_prefill or None,
        }

    raw_root = None
    last_problem = ""

    uid_only = bool(intent_uuid) and not device_prefix and not access_id
    if uid_only and intent_uuid:
        qu = quote(intent_uuid.strip(), safe="")
        for suffix in (f"ibn:ibn/intent={qu}", f"ibn:intent={qu}"):
            got = False
            for req_params in _RESTCONF_PROBE_PARAMS:
                url = f"{base_rest}/{suffix}"
                res = _get(url, req_params)
                if isinstance(res, requests.RequestException):
                    return {"ok": False, "message": f"Error de red hacia Altiplano: {res}", "matches": []}
                if res.status_code == 401:
                    return {
                        "ok": False,
                        "message": (
                            "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                        ),
                        "matches": [],
                    }
                if res.status_code == 200:
                    try:
                        raw_root = res.json()
                        got = True
                        break
                    except ValueError:
                        return {"ok": False, "message": "Respuesta JSON inválida de Altiplano", "matches": []}
                if res.status_code == 404:
                    continue
                last_problem = _extract_altiplano_error_message(res)
            if got:
                break

    if raw_root is None:
        for rel_path in path_list:
            got = False
            for req_params in _RESTCONF_PROBE_PARAMS:
                url = f"{base_rest}/{rel_path}"
                res = _get(url, req_params)
                if isinstance(res, requests.RequestException):
                    return {"ok": False, "message": f"Error de red hacia Altiplano: {res}", "matches": []}
                if res.status_code == 401:
                    return {
                        "ok": False,
                        "message": (
                            "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                        ),
                        "matches": [],
                    }
                if res.status_code == 200:
                    try:
                        raw_root = res.json()
                        got = True
                        break
                    except ValueError:
                        return {"ok": False, "message": "Respuesta JSON inválida de Altiplano", "matches": []}
                if res.status_code == 404:
                    continue
                last_problem = _extract_altiplano_error_message(res)
            if got:
                break

    if raw_root is None:
        msg = (last_problem or "").strip()
        if not msg:
            if device_prefix and not intent_uuid:
                msg = (
                    "No se encontró el intent vía GET por instancia (404 en los targets probados). "
                    "Si usaste solo el prefijo del location name, el VNO puede no estar en la lista interna; "
                    "indicá el target completo tipo …#1001#gpon en el campo device name."
                )
            else:
                msg = "No se pudo leer intents desde Altiplano (probá permisos del usuario o versión NBI)."
        low = msg.lower()
        if "ibn" in low or "does not exist" in low or "module" in low:
            msg += (
                " Podés fijar la ruta correcta en ALTIPLANO_INP_INTENT_DATA_PATHS "
                "(coma-separado), según el Northbound Interface Guide de tu release."
            )
        return {"ok": False, "message": msg, "matches": []}

    intents_list: list = []
    _collect_ont_connection_intents(raw_root, intents_list)

    wide = _buscar_is_wide_access_only_global_list(device_prefix, access_id)
    truncated_matches = False

    matches_out = []
    for entry in intents_list:
        if wide and len(matches_out) >= _INP_WIDE_ACCESS_QUERY_MATCH_LIMIT:
            truncated_matches = True
            break
        if not isinstance(entry, dict):
            continue
        if _intent_matches_filters(
            entry,
            device_prefix=device_prefix,
            access_id=access_id,
            intent_uuid=intent_uuid,
            access_id_match_mode=access_id_match_mode,
        ):
            ft_list = (entry.get("target") or "").strip()
            if ft_list:
                if wide:
                    if not _intent_alignment_state_raw(entry):
                        found_al = _alignment_from_restconf_payload_for_target(raw_root, ft_list)
                        if found_al:
                            entry["alignment-state"] = found_al
                else:
                    entry = _maybe_enrich_alignment_from_restconf_get(
                        base_rest, ft_list, entry, _get_probe
                    )
                    entry = _enrich_intent_entry_via_search_intents_rpc(
                        base_rest,
                        entry,
                        prefer_target=ft_list,
                        access_id=access_id,
                        intent_uuid=intent_uuid,
                        headers=headers,
                        timeout_s=float(search_http_timeout_s),
                    )
                    if not _intent_alignment_state_raw(entry):
                        found_al = _alignment_from_restconf_payload_for_target(raw_root, ft_list)
                        if found_al:
                            entry["alignment-state"] = found_al
            matches_out.append(_match_entry_to_result_dict(entry))

    if not matches_out and (device_prefix or "").strip() and not (access_id or "").strip():
        dp = (device_prefix or "").strip()
        prefill = parse_ba_olta_device_prefix_for_form(dp) or {}
        vno = _vno_from_ont_connection_target(dp)
        if vno:
            prefill["vno"] = vno
        return {
            "ok": True,
            "message": "No existe ese Device Name en Altiplano",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "device_name",
            "create_prefill": prefill or None,
        }

    msg = (
        f"{len(matches_out)} intent(s) encontrado(s)"
        if matches_out
        else "Sin coincidencias para los criterios indicados"
    )
    if wide:
        if truncated_matches:
            msg += (
                f" (tope {_INP_WIDE_ACCESS_QUERY_MATCH_LIMIT} filas; acotá con device/target si hace falta)."
            )
        if matches_out:
            msg += (
                " Consulta amplia: alineación y required network state salen del listado RESTCONF "
                "(sin refinar intent por intent contra el NBI)."
            )
    if not matches_out and wide and (access_id or "").strip():
        return {
            "ok": True,
            "message": "No existe ese Access ID en Altiplano",
            "matches": [],
            "no_match": True,
            "suggest_create": True,
            "consulta_criterion": "access_id",
        }
    if has_advanced_filters and matches_out:
        matches_out = _filter_matches_advanced_states(
            matches_out,
            filter_required_network_state=rn_filters,
            filter_alignment_state=al_filters,
        )
        msg = (
            f"{len(matches_out)} intent(s) con filtros [{_advanced_filter_summary()}]"
            if matches_out
            else f"Sin coincidencias con filtros [{_advanced_filter_summary()}]"
        )
    return {
        "ok": True,
        "message": msg,
        "matches": matches_out,
    }


def _inp_resolve_single_ont_connection_match_for_mutations(
    nbi_bearer_token: str,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict:
    """
    Resuelve **exactamente un** intent ``ont-connection`` (misma regla que borrado).

    Returns:
        ``{"ok": True, "match": dict, "matches": list, "target": str}`` o
        ``{"ok": False, "message": str, "target": None, "matches": list}``.
    """
    search = buscar_intents_ont_connection_inp(
        nbi_bearer_token,
        device_prefix=device_prefix,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not search.get("ok"):
        return {
            "ok": False,
            "message": search.get("message", "Error al localizar el intent"),
            "target": None,
            "matches": search.get("matches") or [],
        }
    matches = search.get("matches") or []
    if len(matches) == 0:
        return {
            "ok": False,
            "message": "No se encontró ningún intent con esos criterios.",
            "target": None,
            "matches": [],
        }
    if len(matches) > 1:
        return {
            "ok": False,
            "message": (
                f"Se encontraron {len(matches)} intents. Acotá con Access ID o target completo "
                "(…#VNO#gpon) en device name."
            ),
            "target": None,
            "matches": matches,
        }
    full_target = (matches[0].get("target") or "").strip()
    if not full_target:
        return {
            "ok": False,
            "message": "El intent hallado no tiene target.",
            "target": None,
            "matches": matches,
        }
    return {"ok": True, "match": matches[0], "matches": matches, "target": full_target}


def _normalize_required_network_state_yang_value(raw: str) -> str | None:
    """Convierte texto UI o API a hoja YANG ``required-network-state`` (valores IBN: suspend, delete, …)."""
    s = (raw or "").strip().lower().replace(" ", "-").replace("_", "-")
    if s in ("active",):
        return "active"
    if s in ("suspended", "suspend"):
        return "suspend"
    if s in ("not-present", "notpresent", "delete", "deleted", "to-be-deleted", "tobedeleted"):
        return "delete"
    if s == "custom":
        return "custom"
    return None


def _inp_synchronize_intent_operation_names() -> tuple[str, ...]:
    """Nombres RESTCONF de operación; override coma-separado en ``ALTIPLANO_INP_SYNCHRONIZE_INTENT_OPERATION``."""
    env = (os.environ.get("ALTIPLANO_INP_SYNCHRONIZE_INTENT_OPERATION") or "").strip()
    if env:
        parts = tuple(x.strip() for x in env.split(",") if x.strip())
        if parts:
            return parts
    return (
        "ibn:synchronize-intent",
        "ibn:synchronize-intents",
        "ibn:sync-intent",
    )


def _inp_sync_intent_rpc_body_variants(full_target: str) -> tuple[dict, ...]:
    t = (full_target or "").strip()
    seen: set[str] = set()
    out: list[dict] = []
    for b in (
        {"ibn:input": {"target": t, "intent-type": "ont-connection"}},
        {"ibn:input": {"intent-type": "ont-connection", "target": t}},
        {"ibn:input": {"intent": {"target": t, "intent-type": "ont-connection"}}},
        {"ibn:input": {"intent-type": "ont-connection", "intent-target": t}},
        {"ibn:input": {"intent-type": "ont-connection", "intentTarget": t}},
    ):
        sig = json.dumps(b, sort_keys=True, default=str)
        if sig not in seen:
            seen.add(sig)
            out.append(b)
    return tuple(out)


def _inp_post_restconf_operation(
    base_rest_data: str,
    operation_segment: str,
    body: dict,
    headers: dict,
    *,
    query: dict[str, str] | None = None,
    timeout_s: float = 90.0,
) -> requests.Response | requests.RequestException | None:
    root = _inp_restconf_operations_root_from_data_base(base_rest_data)
    if not root:
        return None
    url = f"{root.rstrip('/')}/{operation_segment.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"
    try:
        return requests.post(
            url,
            headers=headers,
            json=body,
            verify=False,
            timeout=timeout_s,
        )
    except requests.RequestException as ex:
        return ex


def _inp_restconf_operation_response_ok(res: requests.Response) -> bool:
    if res.status_code not in (200, 204):
        return False
    if res.status_code == 204:
        return True
    data = _json_loads_altiplano_http_response(res)
    if not isinstance(data, dict):
        return True
    if data.get("error") is True:
        return False
    if data.get("ietf-restconf:errors"):
        return False
    # Inc/Altiplano a veces devuelve 200 con errores en "error": [ { "error-message": ... } ]
    # (sin clave ietf-restconf:errors). Si no lo tratamos como fallo, la GUI muestra error y
    # aquí devolvíamos ok=True (p. ej. sync fallida con mensaje tipo «Sync failed for intent…»).
    err_top = data.get("error")
    if isinstance(err_top, list) and err_top:
        return False
    wrapped = data.get("errors")
    if isinstance(wrapped, dict):
        inner = wrapped.get("error")
        if isinstance(inner, list) and inner:
            return False
    resp_xml = data.get("response")
    if isinstance(resp_xml, str):
        low = resp_xml.lower()
        if "<rpc-error>" in low:
            return False
        rpc_msg = _extract_rpc_error_message_from_xml(resp_xml)
        if rpc_msg:
            low_msg = rpc_msg.lower()
            if "sync failed" in low_msg or "ont-connection intent does not exist" in low_msg:
                return False
        if "sync failed" in low or "ont-connection intent does not exist" in low:
            return False
    return True


def _inp_netconf_execute_response_ok(res: requests.Response) -> bool:
    """True si ``/rest/netconf/v1/execute`` no devolvió ``rpc-error`` (mismo criterio que la GUI)."""
    return _inp_restconf_operation_response_ok(res)


def _inp_sync_intent_netconf_rpc_xml(full_target: str) -> str:
    """RPC NETCONF equivalente al botón **Synchronize intent** (HAR GUI INP)."""
    t = html.escape((full_target or "").strip(), quote=False)
    mid = str(int(time.time() * 1000))
    return (
        f"<rpc xmlns='urn:ietf:params:xml:ns:netconf:base:1.0' message-id='{mid}'>"
        "<action xmlns='urn:ietf:params:xml:ns:yang:1'>"
        "<ibn xmlns='http://www.nokia.com/management-solutions/ibn'>"
        "<intent>"
        f"<target>{t}</target>"
        "<intent-type>ont-connection</intent-type>"
        "<synchronize></synchronize>"
        "</intent>"
        "</ibn>"
        "</action>"
        "</rpc>"
    )


def _inp_synchronize_intent_via_netconf_execute(
    host: str,
    port: str,
    base_url: str,
    token: str,
    full_target: str,
) -> tuple[bool, str]:
    """
    POST ``…/rest/netconf/v1/execute`` (como Chrome al pulsar Synchronize intent).
    Returns:
        (ok, error_message) — ``error_message`` vacío si ok.
    """
    url = f"https://{host}:{port}/{base_url.rstrip('/')}/rest/netconf/v1/execute"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/xml;charset=UTF-8",
    }
    xml_body = _inp_sync_intent_netconf_rpc_xml(full_target)
    try:
        res = requests.post(
            url,
            headers=headers,
            params={"favorite": "false", "history": "false"},
            data=xml_body.encode("utf-8"),
            verify=False,
            timeout=90.0,
        )
    except requests.RequestException as ex:
        return False, f"Error de red hacia Altiplano (NETCONF execute): {ex}"
    if res.status_code == 401:
        return False, (
            "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
        )
    if _inp_netconf_execute_response_ok(res):
        return True, ""
    return False, _extract_altiplano_error_message(res)


def sincronizar_intent_ont_connection_inp(
    nbi_bearer_token: str,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict:
    """
    Equivale al botón **Synchronize intent** de la GUI INP (alinear intent ``ont-connection``).

    Primero ``POST …/rest/netconf/v1/execute`` (mismo RPC que la GUI); si falla, prueba RESTCONF
    ``ibn:synchronize-intent`` (``ALTIPLANO_INP_SYNCHRONIZE_INTENT_OPERATION`` coma-separado).
    """
    token = (nbi_bearer_token or "").strip()
    if not token:
        return {"ok": False, "message": "Token requerido", "target": None, "matches": []}

    resolved = _inp_resolve_single_ont_connection_match_for_mutations(
        token,
        device_prefix=device_prefix,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not resolved.get("ok"):
        return {
            "ok": False,
            "message": resolved.get("message", "Error"),
            "target": resolved.get("target"),
            "matches": resolved.get("matches") or [],
        }

    full_target = resolved["target"]
    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Entorno NBI INP no configurado", "target": full_target}

    sync_ok_payload = {
        "ok": True,
        "message": "Sincronización de intent solicitada en Altiplano (IBN).",
        "target": full_target,
        "access_id": resolved["match"].get("access_id"),
        "intent_uuid": resolved["match"].get("intent_uuid"),
        "matches": resolved.get("matches") or [],
    }

    ok_nc, err_nc = _inp_synchronize_intent_via_netconf_execute(
        host, port, base_url, token, full_target
    )
    if ok_nc:
        return _inp_post_sync_verify_alignment(
            token,
            full_target,
            resolved,
            sync_ok_payload,
            access_id=access_id,
            intent_uuid=intent_uuid,
        )

    last_err = err_nc

    base_rest = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json, application/json;q=0.9, */*;q=0.5",
        "Content-Type": "application/yang-data+json",
    }
    for op_name in _inp_synchronize_intent_operation_names():
        for body in _inp_sync_intent_rpc_body_variants(full_target):
            res = _inp_post_restconf_operation(
                base_rest, op_name, body, headers, query=None, timeout_s=90.0
            )
            if res is None:
                return {
                    "ok": False,
                    "message": "No se pudo armar la URL de operaciones RESTCONF.",
                    "target": full_target,
                    "matches": resolved.get("matches") or [],
                }
            if isinstance(res, requests.RequestException):
                return {
                    "ok": False,
                    "message": f"Error de red hacia Altiplano: {res}",
                    "target": full_target,
                    "matches": resolved.get("matches") or [],
                }
            if res.status_code == 401:
                return {
                    "ok": False,
                    "message": (
                        "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                    ),
                    "target": full_target,
                    "matches": resolved.get("matches") or [],
                }
            if _inp_restconf_operation_response_ok(res):
                return _inp_post_sync_verify_alignment(
                    token,
                    full_target,
                    resolved,
                    sync_ok_payload,
                    access_id=access_id,
                    intent_uuid=intent_uuid,
                )
            if res.status_code == 404:
                last_err = f"404 en operación {op_name}"
                break
            last_err = _extract_altiplano_error_message(res)

    hint = (
        " Si la operación tiene otro nombre en tu release, definí la variable de entorno "
        "ALTIPLANO_INP_SYNCHRONIZE_INTENT_OPERATION con el segmento RESTCONF exacto "
        "(copiado de Chrome → Red al pulsar Synchronize intent)."
    )
    fail_msg = (last_err or "No se pudo sincronizar el intent.") + hint
    out = {
        "ok": False,
        "target": full_target,
        "matches": resolved.get("matches") or [],
        **_altiplano_error_payload_from_message(fail_msg),
    }
    if "message" not in out:
        out["message"] = fail_msg
    if out.get("can_create_missing_ont_connection") and resolved.get("match"):
        aid = resolved["match"].get("access_id")
        if aid:
            miss = dict(out.get("missing_ont_connection") or {})
            miss["access_id"] = str(aid)
            out["missing_ont_connection"] = miss
    return out


def _intent_row_is_aligned(row: dict) -> bool:
    return str(row.get("alignment_state") or "").strip().lower() == "aligned"


def _inp_relookup_intent_row(
    nbi_bearer_token: str,
    *,
    full_target: str,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict | None:
    """Vuelve a leer un intent tras mutaciones (alignment / error-detail actualizados)."""
    search = buscar_intents_ont_connection_inp(
        nbi_bearer_token,
        device_prefix=full_target,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not search.get("ok"):
        return None
    want = (full_target or "").strip()
    for row in search.get("matches") or []:
        if (row.get("target") or "").strip() == want:
            return row
    matches = search.get("matches") or []
    if len(matches) == 1:
        return matches[0]
    return None


def _inp_sync_still_misaligned_payload(
    token: str,
    full_target: str,
    resolved: dict,
    fresh: dict,
) -> dict:
    ed = (fresh.get("error_detail") or "").strip()
    msg = ed or "El intent sigue Misaligned tras sincronizar en Altiplano."
    out: dict = {
        "ok": False,
        "message": msg,
        "target": full_target,
        "access_id": fresh.get("access_id") or resolved["match"].get("access_id"),
        "intent_uuid": fresh.get("intent_uuid") or resolved["match"].get("intent_uuid"),
        "matches": [fresh],
        "alignment_state": fresh.get("alignment_state"),
        "error_detail": ed or None,
    }
    if ed:
        out.update(_altiplano_error_payload_from_message(ed))
    elif fresh.get("can_create_missing_ont_connection"):
        miss = fresh.get("missing_ont_connection")
        if miss:
            out["missing_ont_connection"] = miss
            out["can_create_missing_ont_connection"] = True
    aid = out.get("access_id")
    if out.get("can_create_missing_ont_connection") and aid:
        miss = dict(out.get("missing_ont_connection") or {})
        miss["access_id"] = str(aid)
        out["missing_ont_connection"] = miss
    return out


def _inp_post_sync_verify_alignment(
    token: str,
    full_target: str,
    resolved: dict,
    sync_ok_payload: dict,
    *,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict:
    """Si Altiplano aceptó el RPC pero el intent sigue Misaligned, devolver fallo con Fix-it."""
    fresh = _inp_relookup_intent_row(
        token,
        full_target=full_target,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not fresh or _intent_row_is_aligned(fresh):
        return sync_ok_payload
    return _inp_sync_still_misaligned_payload(token, full_target, resolved, fresh)


def corregir_dependencias_l1_y_alinear_intent_inp(
    nbi_bearer_token: str,
    *,
    access_id: str,
    device_prefix: str | None = None,
    intent_uuid: str | None = None,
    error_detail: str | None = None,
    max_steps: int = 8,
    pir: int = 1000,
    cir: int = 35,
) -> dict:
    """
    Crea en cadena las ``ont-connection`` que falten en L1 (mismo Access ID) y sincroniza
    el intent consultado hasta alinearlo o agotar ``max_steps``.
    """
    from services.domain import OPERADORES

    token = (nbi_bearer_token or "").strip()
    aid = (access_id or "").strip()
    if not token:
        return {"ok": False, "message": "Token requerido", "steps": []}
    if not aid:
        return {"ok": False, "message": "Access ID requerido", "steps": []}

    resolved = _inp_resolve_single_ont_connection_match_for_mutations(
        token,
        device_prefix=device_prefix,
        access_id=aid,
        intent_uuid=intent_uuid,
    )
    if not resolved.get("ok"):
        return {
            "ok": False,
            "message": resolved.get("message", "No se encontró el intent"),
            "steps": [],
            "matches": resolved.get("matches") or [],
        }

    full_target = resolved["target"]
    steps: list[dict] = []
    created_targets: set[str] = set()
    pending_missing: list[dict] = []

    seed_err = (error_detail or "").strip()
    if seed_err:
        seed = parse_l1_scheduler_missing_ont_connection(seed_err)
        if seed:
            pending_missing.append(seed)

    def _operador_for_vno(vno_n: int | None) -> str:
        if vno_n is None:
            return ""
        return (OPERADORES.get(int(vno_n)) or "").upper()

    def _create_missing(miss: dict) -> dict:
        vno_n = miss.get("vno")
        op = _operador_for_vno(vno_n)
        if not op:
            return {
                "ok": False,
                "message": f"VNO {vno_n} sin operador mapeado en la suite.",
            }
        return crear_ont_connection_intent(
            operador=op,
            entorno_nbi="INP",
            device_name=str(miss["device_name"]),
            lt=str(miss["lt"]),
            pon=str(miss["pon"]),
            ont=str(miss["ont"]),
            vno=str(miss.get("vno_s") or miss.get("vno")),
            fiber_name=str(miss["fiber_name"]),
            access_id=aid,
            pir=pir,
            cir=cir,
            nbi_bearer_token=token,
        )

    limit = max(1, min(int(max_steps or 8), 16))
    for _ in range(limit):
        while pending_missing:
            miss = pending_missing.pop(0)
            tgt_key = (miss.get("target") or "").strip()
            if not tgt_key or tgt_key in created_targets:
                continue
            create_out = _create_missing(miss)
            steps.append(
                {
                    "action": "create",
                    "target": tgt_key,
                    "ok": create_out.get("ok"),
                    "message": create_out.get("message"),
                }
            )
            if create_out.get("ok"):
                created_targets.add(tgt_key)
                continue
            err_msg = create_out.get("message") or ""
            dep = parse_l1_scheduler_missing_ont_connection(err_msg)
            if not dep and create_out.get("error_detail"):
                dep = parse_l1_scheduler_missing_ont_connection(
                    str(create_out.get("error_detail"))
                )
            if dep and (dep.get("target") or "").strip() not in created_targets:
                pending_missing.insert(0, dep)
                if tgt_key not in created_targets:
                    pending_missing.append(miss)
                continue
            return {
                "ok": False,
                "message": create_out.get("message", "No se pudo crear ONT Connection"),
                "target": full_target,
                "steps": steps,
                "matches": resolved.get("matches") or [],
                **{
                    k: create_out[k]
                    for k in (
                        "error_detail",
                        "can_create_missing_ont_connection",
                        "missing_ont_connection",
                    )
                    if k in create_out
                },
            }

        sync_out = sincronizar_intent_ont_connection_inp(
            token,
            device_prefix=full_target,
            access_id=aid,
            intent_uuid=intent_uuid,
        )
        steps.append(
            {
                "action": "sync",
                "target": full_target,
                "ok": sync_out.get("ok"),
                "message": sync_out.get("message"),
            }
        )
        if sync_out.get("ok"):
            fresh = _inp_relookup_intent_row(
                token, full_target=full_target, access_id=aid, intent_uuid=intent_uuid
            )
            if fresh and _intent_row_is_aligned(fresh):
                return {
                    "ok": True,
                    "message": f"Intent alineado en {full_target} (Access ID {aid}).",
                    "target": full_target,
                    "access_id": aid,
                    "steps": steps,
                    "matches": [fresh],
                    "created_targets": sorted(created_targets),
                }
            ed = (fresh or {}).get("error_detail") or sync_out.get("error_detail") or ""
            dep = parse_l1_scheduler_missing_ont_connection(ed)
            if not dep and sync_out.get("message"):
                dep = parse_l1_scheduler_missing_ont_connection(str(sync_out.get("message")))
            if dep and (dep.get("target") or "").strip() not in created_targets:
                pending_missing.append(dep)
                continue
            if fresh and not _intent_row_is_aligned(fresh):
                return {
                    **_inp_sync_still_misaligned_payload(token, full_target, resolved, fresh),
                    "steps": steps,
                    "created_targets": sorted(created_targets),
                }
            return {
                "ok": True,
                "message": sync_out.get("message", "Sincronización solicitada."),
                "target": full_target,
                "access_id": aid,
                "steps": steps,
                "matches": sync_out.get("matches") or [],
                "created_targets": sorted(created_targets),
            }

        err_msg = sync_out.get("error_detail") or sync_out.get("message") or ""
        dep = parse_l1_scheduler_missing_ont_connection(err_msg)
        if not dep and sync_out.get("missing_ont_connection"):
            dep = sync_out.get("missing_ont_connection")
        if dep and (dep.get("target") or "").strip() not in created_targets:
            pending_missing.append(dep)
            continue
        return {**sync_out, "steps": steps, "created_targets": sorted(created_targets)}

    return {
        "ok": False,
        "message": (
            f"Se alcanzó el límite de {limit} pasos creando dependencias L1 / sincronizando. "
            "Revisá la consulta y volvé a intentar."
        ),
        "target": full_target,
        "access_id": aid,
        "steps": steps,
        "created_targets": sorted(created_targets),
    }


def actualizar_required_network_state_ont_connection_inp(
    nbi_bearer_token: str,
    required_network_state: str,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict:
    """
    Equivale al **Modify intent** de la GUI: cambia ``required-network-state`` (p. ej. a ``active``).

    Usa RESTCONF ``PATCH`` sobre la instancia ``ibn:ibn/intent=<target>,ont-connection``.
    Valores típicos: ``active``, ``suspended``, ``not-present``, ``delete``.
    """
    token = (nbi_bearer_token or "").strip()
    if not token:
        return {"ok": False, "message": "Token requerido", "target": None, "matches": []}

    yang = _normalize_required_network_state_yang_value(required_network_state)
    if not yang:
        return {
            "ok": False,
            "message": "Valor inválido; usá active, suspended, not-present o delete.",
            "target": None,
            "matches": [],
        }

    resolved = _inp_resolve_single_ont_connection_match_for_mutations(
        token,
        device_prefix=device_prefix,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not resolved.get("ok"):
        return {
            "ok": False,
            "message": resolved.get("message", "Error"),
            "target": resolved.get("target"),
            "matches": resolved.get("matches") or [],
        }

    full_target = resolved["target"]
    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Entorno NBI INP no configurado", "target": full_target}

    base_rest = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    rel = _inp_rel_path_ont_connection_instance(full_target)
    url = f"{base_rest}/{rel}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json, application/json;q=0.9, */*;q=0.5",
        "Content-Type": "application/yang-data+json",
    }
    param_variants = (
        {},
        {"altiplano-target": "INP"},
        {"altiplano-triggerSyncUponSuccess": "true"},
        {"altiplano-target": "INP", "altiplano-triggerSyncUponSuccess": "true"},
    )
    patch_bodies: tuple[dict, ...] = (
        {"required-network-state": yang},
        {"ibn:intent": {"required-network-state": yang}},
        {
            "ont-connection:ont-connection": {
                "required-network-state": yang,
            },
        },
    )

    last_err = ""
    for params in param_variants:
        for payload in patch_bodies:
            try:
                res = requests.patch(
                    url,
                    headers=headers,
                    params=params or None,
                    json=payload,
                    verify=False,
                    timeout=90,
                )
            except requests.RequestException as ex:
                return {
                    "ok": False,
                    "message": f"Error de red hacia Altiplano: {ex}",
                    "target": full_target,
                    "matches": resolved.get("matches") or [],
                }
            if res.status_code == 401:
                return {
                    "ok": False,
                    "message": (
                        "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                    ),
                    "target": full_target,
                    "matches": resolved.get("matches") or [],
                }
            if 200 <= res.status_code < 300:
                return {
                    "ok": True,
                    "message": f"Required network state actualizado a «{yang}».",
                    "target": full_target,
                    "required_network_state": yang,
                    "access_id": resolved["match"].get("access_id"),
                    "intent_uuid": resolved["match"].get("intent_uuid"),
                    "matches": resolved.get("matches") or [],
                }
            if res.status_code == 404:
                last_err = "404 Not Found"
                continue
            last_err = _extract_altiplano_error_message(res)

    return {
        "ok": False,
        "message": (last_err or "PATCH rechazado").strip(),
        "target": full_target,
        "matches": resolved.get("matches") or [],
    }


def borrar_intent_ont_connection_inp(
    nbi_bearer_token: str,
    *,
    device_prefix: str | None = None,
    access_id: str | None = None,
    intent_uuid: str | None = None,
) -> dict:
    """
    Elimina **un único** intent ``ont-connection`` en INP mediante RESTCONF ``DELETE`` sobre la
    instancia ``ibn:ibn/intent=<target>,ont-connection`` (misma clave que GET Postman).

    Reutiliza la búsqueda de :func:`buscar_intents_ont_connection_inp`; si hay 0 o más de 1
    coincidencia, no borra nada y devuelve error descriptivo.
    """
    resolved = _inp_resolve_single_ont_connection_match_for_mutations(
        nbi_bearer_token,
        device_prefix=device_prefix,
        access_id=access_id,
        intent_uuid=intent_uuid,
    )
    if not resolved.get("ok"):
        matches_err = resolved.get("matches") or []
        if len(matches_err) > 1:
            msg = (
                f"Se encontraron {len(matches_err)} intents. Para borrar uno solo, acotá con "
                "Access ID (si hay ambigüedad) o indicá el target completo "
                "(…#VNO#gpon) en device name."
            )
        else:
            msg = resolved.get("message", "Error al localizar el intent")
            if msg == "No se encontró ningún intent con esos criterios.":
                msg = "No se encontró ningún intent con esos criterios; no se borró nada."
            elif msg == "El intent hallado no tiene target.":
                msg = "El intent hallado no tiene target; no se puede borrar."
        return {
            "ok": False,
            "message": msg,
            "target": resolved.get("target"),
            "matches": matches_err,
        }

    matches = resolved.get("matches") or []
    full_target = resolved["target"]

    token = (nbi_bearer_token or "").strip()
    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Entorno NBI INP no configurado", "target": full_target}

    base_rest = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    rel = _inp_rel_path_ont_connection_instance(full_target)
    url = f"{base_rest}/{rel}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json",
    }
    param_variants = (
        {"altiplano-triggerSyncUponSuccess": "true"},
        {},
        {"altiplano-target": "INP"},
        {"altiplano-target": "INP", "altiplano-triggerSyncUponSuccess": "true"},
    )

    def _delete(params: dict):
        try:
            return requests.delete(url, headers=headers, params=params or None, verify=False, timeout=90)
        except requests.RequestException as ex:
            return ex

    last_err = ""
    for req_params in param_variants:
        res = _delete(req_params)
        if isinstance(res, requests.RequestException):
            return {
                "ok": False,
                "message": f"Error de red hacia Altiplano: {res}",
                "target": full_target,
                "matches": matches,
            }
        if res.status_code == 401:
            return {
                "ok": False,
                "message": (
                    "Sesión Altiplano expirada; cerrá sesión en Orquestador y volvé a ingresar."
                ),
                "target": full_target,
                "matches": matches,
            }
        if res.status_code in (200, 204):
            return {
                "ok": True,
                "message": "Intent ont-connection eliminado en Altiplano.",
                "target": full_target,
                "access_id": matches[0].get("access_id"),
                "intent_uuid": matches[0].get("intent_uuid"),
            }
        if res.status_code == 404:
            last_err = "404 Not Found"
            continue
        last_err = _extract_altiplano_error_message(res)

    msg = (last_err or "DELETE rechazado").strip()
    return {
        "ok": False,
        "message": f"No se pudo borrar el intent: {msg}",
        "target": full_target,
        "matches": matches,
    }


def normalizar_object_name(object_name_raw: str) -> str:
    """
    Convierte el object_name de Postgres al formato que Altiplano espera.

    Ejemplo:
        BA_OLTA_TG01_02:1-1-3-6-35
    →   BA_OLTA_TG01_02-3-6-35
    """
    if ":1-1-" in object_name_raw:
        base, resto = object_name_raw.split(":1-1-")
        return f"{base}-{resto}"
    return object_name_raw


def _altiplano_power_target(operator_id) -> tuple[str, str] | None:
    if operator_id is None:
        return None
    try:
        op_key = int(operator_id)
    except (TypeError, ValueError):
        op_key = operator_id
    return _ALTIPLANO_POWER_TARGETS_BY_OPERATOR_ID.get(op_key)


def _vno_slug_from_base_url(base_url: str) -> str:
    base = (base_url or "").strip()
    if base.endswith("-altiplano-ac"):
        return base[: -len("-altiplano-ac")]
    return base.split("-")[0] if base else ""


def _power_auth_contexts(operator_id) -> list[tuple[str, str, str, str]]:
    """
    Contextos (vno, auth_url, user, password) para leer potencias.

    Usa credenciales por operador (``ALTIPLANO_TASA_*``, etc.) y prueba también INP
    (misma AC que Network Views en la GUI).
    """
    from services.domain import OPERADORES

    contexts: list[tuple[str, str, str, str]] = []
    seen_auth: set[str] = set()

    def _append_operator(op_name: str) -> None:
        host, port, base = get_altiplano_nbi_target(op_name)
        if not host or not base:
            return
        user, pwd = get_altiplano_operator_credentials(op_name)
        if not user or not pwd:
            return
        auth_url = f"https://{host}:{port}/{base}/rest/auth/login"
        if auth_url in seen_auth:
            return
        seen_auth.add(auth_url)
        contexts.append((_vno_slug_from_base_url(base), auth_url, user, pwd))

    op_key = None
    if operator_id is not None:
        try:
            op_key = int(operator_id)
        except (TypeError, ValueError):
            pass
    if op_key is not None:
        op_name = OPERADORES.get(op_key)
        if op_name:
            _append_operator(op_name)

    _append_operator("INP")

    if contexts:
        return contexts

    legacy = _altiplano_power_target(operator_id)
    if not legacy:
        return []
    vno, auth_url = legacy
    user, pwd = get_altiplano_credentials()
    if user and pwd:
        return [(vno, auth_url, user, pwd)]
    return []


def _ne_from_object_name_raw(object_name_raw: str) -> str | None:
    """
    Deriva ``BA_OLTA_ES01_01.LT1`` desde ``BA_OLTA_ES01_01-1-1-4`` o ``…:1-1-1-4``.

    No usar ``split('-')[0/1]`` a secas: el nombre OLT ya contiene guiones.
    """
    normalized = normalizar_object_name(str(object_name_raw or "").strip())
    if not normalized:
        return None
    m = re.match(r"^(BA_OLTA_[A-Za-z0-9_]+)-(\d+)", normalized)
    if m:
        return f"{m.group(1)}.LT{m.group(2)}"
    parts = normalized.split("-")
    if len(parts) >= 2 and parts[0] and str(parts[1]).isdigit():
        return f"{parts[0]}.LT{parts[1]}"
    return None


def _dbm_from_altiplano_tenths(value) -> float | None:
    try:
        return round(float(value) * 0.1, 2)
    except (TypeError, ValueError):
        return None


def _potencias_from_diagnostics_body(body: object) -> tuple[float, float] | None:
    if not isinstance(body, dict):
        return None
    diag = body.get("bbf-hardware-transceivers-mounted:diagnostics")
    if not isinstance(diag, dict):
        return None
    tx = _dbm_from_altiplano_tenths(
        diag.get("nokia-hardware-transceivers-dbm-mounted:tx-power-dbm")
    )
    rx = _dbm_from_altiplano_tenths(
        diag.get("nokia-hardware-transceivers-dbm-mounted:rx-power-dbm")
    )
    if tx is None or rx is None:
        return None
    return tx, rx


def _potencias_from_ema_entity_body(body: object) -> tuple[float, float] | None:
    """Misma escala que la GUI Network Views (``extraAttributes`` × 0,1 dBm)."""
    if not isinstance(body, dict):
        return None
    ea = body.get("extraAttributes")
    if not isinstance(ea, dict):
        return None
    tx = _dbm_from_altiplano_tenths(ea.get("tx-signal-level"))
    rx = _dbm_from_altiplano_tenths(
        ea.get("rx-signal-level-ont") or ea.get("rx-signal-level")
    )
    if tx is None or rx is None:
        return None
    return tx, rx


def _sn_valor_legible(val) -> str | None:
    """Normaliza un campo de serial de EMA; descarta placeholders de la GUI."""
    if val is None or isinstance(val, dict):
        return None
    s = str(val).strip()
    if not s or s == "-":
        return None
    low = s.lower()
    if low.startswith("{") or "classname" in low or "undefined" in low:
        return None
    if len(s) < 6 or len(s) > 20:
        return None
    return s.upper()


def _sn_from_ema_entity_body(body: object) -> str | None:
    """Expected Serial Number (General en Network Views); fallback a detectado/legacy."""
    if not isinstance(body, dict):
        return None
    ea = body.get("extraAttributes")
    if not isinstance(ea, dict):
        return None
    for key in (
        "expected-serial-number",
        "detected-serial-number",
        "serialNumber",
        "serial-number",
    ):
        sn = _sn_valor_legible(ea.get(key))
        if sn:
            return sn
    return None


def _restconf_potencias_url(base_host: str, vno: str, ne: str, object_name_raw: str) -> str:
    object_name_altiplano = normalizar_object_name(object_name_raw)
    onu_encoded = quote(object_name_altiplano, safe="")
    return (
        f"https://{base_host}/{vno}-altiplano-ac/rest/restconf/data/"
        f"anv:device-manager/anv-device-holders:device={ne}/"
        f"device-specific-data/bbf-fiber-onu-emulated-mount:onus/"
        f"onu={onu_encoded}_GPON/root/"
        f"ietf-hardware-mounted:hardware-state/component=ANIPORT/"
        f"bbf-hardware-transceivers-mounted:transceiver-link/diagnostics"
        f"?altiplano-target=INP"
    )


def _ema_entity_url(
    base_host: str,
    vno: str,
    ne: str,
    object_name_raw: str,
    *,
    fetch_device_attributes: bool,
    is_one: bool,
) -> str:
    """URL API EMA de Network Views (potencias, oper/admin, SN)."""
    object_name_altiplano = normalizar_object_name(object_name_raw)
    onu_name = quote(f"v1~{object_name_altiplano}_GPON", safe="")
    ne_enc = quote(ne, safe="")
    qs = urlencode(
        {
            "fetchDeviceAttributes": "true" if fetch_device_attributes else "false",
            "isChild": "false",
            "isOne": "true" if is_one else "false",
            "forCondition": "false",
        }
    )
    return (
        f"https://{base_host}/{vno}-altiplano-ac/rest/ema/entity/"
        f"LS-FX-MF-SF-LT/ONT/{ne_enc}/{onu_name}?{qs}"
    )


def _ema_potencias_url(base_host: str, vno: str, ne: str, object_name_raw: str) -> str:
    return _ema_entity_url(
        base_host,
        vno,
        ne,
        object_name_raw,
        fetch_device_attributes=True,
        is_one=True,
    )


def _ema_entity_resource_url(
    base_host: str, vno: str, ne: str, object_name_raw: str
) -> str:
    """URL base EMA de la ONT (POST lock/unlock admin, HAR Network Views)."""
    object_name_altiplano = normalizar_object_name(object_name_raw)
    onu_name = quote(f"v1~{object_name_altiplano}_GPON", safe="")
    ne_enc = quote(ne, safe="")
    return (
        f"https://{base_host}/{vno}-altiplano-ac/rest/ema/entity/"
        f"LS-FX-MF-SF-LT/ONT/{ne_enc}/{onu_name}"
    )


def _ont_connection_full_target(object_name_raw: str, operator_id) -> str:
    """Target RESTCONF ``…#{VNO}#gpon`` a partir de inventario."""
    onu = normalizar_object_name(str(object_name_raw or "").strip())
    if not onu:
        return ""
    low = onu.lower()
    if "#" in onu and "gpon" in low:
        return onu
    vno = ""
    if operator_id is not None:
        try:
            vno = str(int(operator_id))
        except (TypeError, ValueError):
            vno = str(operator_id).strip()
    if not vno:
        return ""
    return f"{onu}#{vno}#gpon"


def _ema_top_level_state(body: object, key: str) -> str | None:
    if not isinstance(body, dict):
        return None
    val = body.get(key)
    if val is None:
        return None
    s = str(val).strip()
    return s.upper() if s else None


def _normalize_altiplano_iso8601_for_js(raw: str | None) -> str | None:
    """Normaliza ISO8601 de Altiplano para ``Date`` en navegadores (``+0000`` → ``+00:00``)."""
    s = str(raw or "").strip()
    if not s:
        return None
    m = re.match(r"^(.*)([+-])(\d{2})(\d{2})$", s)
    if m and "T" in m.group(1):
        s = f"{m.group(1)}{m.group(2)}{m.group(3)}:{m.group(4)}"
    return s


def _parse_altiplano_datetime_utc(raw: str | None):
    from datetime import datetime, timezone

    norm = _normalize_altiplano_iso8601_for_js(raw)
    if not norm:
        return None
    try:
        dt = datetime.fromisoformat(norm.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _newest_altiplano_iso_timestamp(*values: str | None) -> str | None:
    """El timestamp más reciente entre candidatos (p. ej. IBN vs EMA ``onu-detected``)."""
    best_dt = None
    best_raw = None
    for raw in values:
        if not raw:
            continue
        dt = _parse_altiplano_datetime_utc(raw)
        if dt is None:
            continue
        if best_dt is None or dt > best_dt:
            best_dt = dt
            best_raw = raw
    return _normalize_altiplano_iso8601_for_js(best_raw) if best_raw else None


def _onu_detected_datetime_from_ema(body: object) -> str | None:
    """``extraAttributes/onu-detected-datetime`` (Network Views / EMA)."""
    if not isinstance(body, dict):
        return None
    ea = body.get("extraAttributes")
    if not isinstance(ea, dict):
        return None
    val = ea.get("onu-detected-datetime")
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _intent_health_from_search_intents_row(row: dict) -> dict[str, str | None]:
    """Campos de health en una fila cruda de ``ibn:search-intents`` (como la GUI)."""
    out: dict[str, str | None] = {"health": None, "health_ts": None}
    if not isinstance(row, dict):
        return out
    h = row.get("health") or row.get("intent-health")
    if h is not None and str(h).strip():
        out["health"] = str(h).strip()
    ts = row.get("health-last-updated-timestamp") or row.get(
        "intent-health-last-updated-timestamp"
    )
    if ts is not None and str(ts).strip():
        out["health_ts"] = _normalize_altiplano_iso8601_for_js(str(ts).strip())
    return out


def _deep_find_intent_health_fields(obj: object, depth: int = 0, max_depth: int = 12) -> dict[str, str]:
    """Extrae health y timestamp del JSON RESTCONF/IBN."""
    out: dict[str, str] = {}
    if depth > max_depth:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                continue
            lk = k.lower().replace("_", "-")
            if lk in ("intent-health", "health") and v is not None:
                sv = str(v).strip()
                if sv and "health" not in out:
                    out["health"] = sv
            elif lk in (
                "intent-health-last-updated-timestamp",
                "health-last-updated-timestamp",
            ) and v is not None:
                sv = str(v).strip()
                if sv:
                    norm = _normalize_altiplano_iso8601_for_js(sv)
                    if norm:
                        out["health_ts"] = norm
            sub = _deep_find_intent_health_fields(v, depth + 1, max_depth)
            for sk, sv in sub.items():
                if sv and sk not in out:
                    out[sk] = sv
    elif isinstance(obj, list):
        for item in obj:
            sub = _deep_find_intent_health_fields(item, depth + 1, max_depth)
            for sk, sv in sub.items():
                if sv and sk not in out:
                    out[sk] = sv
    return out


def _nv_health_display_timestamp(
    health_ts: str | None,
    onu_detected_ts: str | None,
    *,
    oper: str | None,
    health: str | None,
) -> str | None:
    """
    Timestamp para el “hace X min” bajo Healthy.

    ``health-last-updated-timestamp`` del intent a veces queda desfasado (días) mientras
    la GUI muestra la detección reciente de la ONT (EMA ``onu-detected-datetime``).
    Con ONT Up, priorizar el más reciente entre IBN y EMA (como Network Views).
    """
    oper_up = str(oper or "").strip().upper() == "UP"
    health_ok = str(health or "").strip().lower() in ("healthy", "health")
    if oper_up and (health_ok or onu_detected_ts):
        return _newest_altiplano_iso_timestamp(health_ts, onu_detected_ts)
    return _newest_altiplano_iso_timestamp(health_ts) or _normalize_altiplano_iso8601_for_js(
        onu_detected_ts
    )


def _fetch_intent_health_inp(
    access_id: str,
    full_target: str,
    *,
    username: str,
    password: str,
) -> dict[str, str | None]:
    """Health vía ``ibn:search-intents`` (GUI) y fallback GET RESTCONF por target."""
    out: dict[str, str | None] = {"health": None, "health_ts": None}
    aid = str(access_id or "").strip()
    tgt = (full_target or "").strip().lower()

    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return out
    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"
    base_rest = f"https://{host}:{port}/{base_url}/rest/restconf/data"
    token = _obtener_token(auth_url, username=username, password=password)
    if not token:
        return out
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json",
    }

    if aid:
        url = _inp_search_intents_operation_url(base_rest)
        if url:
            body = _inp_gui_search_intents_body_by_access_id(aid)
            post_headers = {
                **headers,
                "Content-Type": "application/yang-data+json",
            }
            try:
                res = requests.post(
                    url,
                    headers=post_headers,
                    json=body,
                    verify=False,
                    timeout=get_altiplano_inp_search_http_timeout_s(),
                )
            except requests.RequestException:
                res = None
            if res is not None and res.status_code == 200:
                data = _json_loads_altiplano_http_response(res)
                rows = _extract_intent_list_from_search_intents_response(data)
                best: dict[str, str | None] | None = None
                best_target_match = False
                for row in rows:
                    if (row.get("intent-type") or "").strip() != "ont-connection":
                        continue
                    if aid:
                        row_aid = _access_id_from_search_intents_row(row)
                        if not _intent_access_id_matches(row_aid, aid, "exact"):
                            continue
                    row_tgt = str(row.get("target") or "").strip().lower()
                    target_match = bool(tgt and row_tgt and row_tgt == tgt)
                    if not aid and tgt and row_tgt and row_tgt != tgt:
                        continue
                    found = _intent_health_from_search_intents_row(row)
                    if not found.get("health") and not found.get("health_ts"):
                        continue
                    if target_match:
                        if found.get("health"):
                            out["health"] = found["health"]
                        if found.get("health_ts"):
                            out["health_ts"] = found["health_ts"]
                        if out["health"] or out["health_ts"]:
                            return out
                    if best is None or target_match and not best_target_match:
                        best = found
                        best_target_match = target_match
                    elif best is not None and not best_target_match:
                        merged_ts = _newest_altiplano_iso_timestamp(
                            best.get("health_ts"), found.get("health_ts")
                        )
                        if merged_ts:
                            best["health_ts"] = merged_ts
                        if not best.get("health") and found.get("health"):
                            best["health"] = found["health"]
                if best:
                    if best.get("health"):
                        out["health"] = best["health"]
                    if best.get("health_ts"):
                        out["health_ts"] = best["health_ts"]
                    if out["health"] or out["health_ts"]:
                        return out

    if not tgt:
        return out
    url = f"{base_rest}/{_inp_rel_path_ont_connection_instance(full_target)}"
    body = _http_get_altiplano_json(
        url,
        auth_url,
        access_id=access_id,
        ne="",
        log_label="intent health INP",
        accept="application/yang-data+json",
        username=username,
        password=password,
    )
    if not isinstance(body, dict):
        return out
    found = _deep_find_intent_health_fields(body)
    if found.get("health"):
        out["health"] = found["health"]
    if found.get("health_ts"):
        out["health_ts"] = found["health_ts"]
    return out


def _http_post_altiplano_json(
    url: str,
    auth_url: str,
    payload: dict,
    *,
    access_id: str,
    ne: str,
    log_label: str,
    accept: str = "application/json",
    username: str | None = None,
    password: str | None = None,
) -> object | None:
    """POST JSON a Altiplano (p. ej. búsqueda de alarmas activas en AC INP)."""
    token = _obtener_token(auth_url, username=username, password=password)
    if not token:
        logger.warning(
            "Altiplano POST (%s): sin token (auth_url=%s access_id=%s)",
            log_label,
            auth_url,
            access_id,
        )
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "Content-Type": "application/json",
    }

    def _post(bearer: str):
        headers["Authorization"] = f"Bearer {bearer}"
        return requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=60,
        )

    try:
        res = _post(token)
    except requests.RequestException:
        logger.warning(
            "Altiplano POST (%s): error de red access_id=%s NE=%s",
            log_label,
            access_id,
            ne,
        )
        return None

    if res.status_code in (401, 403):
        token_new = _obtener_token(
            auth_url, username=username, password=password, force_refresh=True
        )
        if not token_new:
            return None
        try:
            res = _post(token_new)
        except requests.RequestException:
            return None

    if res.status_code != 200:
        logger.warning(
            "Altiplano POST (%s): HTTP %s access_id=%s NE=%s",
            log_label,
            res.status_code,
            access_id,
            ne,
        )
        return None

    return _json_loads_altiplano_http_response(res)


def _http_post_altiplano_expect_ok(
    url: str,
    auth_url: str,
    payload: dict,
    *,
    access_id: str,
    ne: str,
    log_label: str,
    username: str | None = None,
    password: str | None = None,
    ok_statuses: tuple[int, ...] = (200, 201, 204),
) -> dict:
    """POST JSON; éxito por código HTTP (EMA lock/unlock suele responder vacío)."""
    token = _obtener_token(auth_url, username=username, password=password)
    if not token:
        return {"ok": False, "message": "No se pudo autenticar en Altiplano"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
    }

    def _post(bearer: str):
        headers["Authorization"] = f"Bearer {bearer}"
        return requests.post(
            url,
            headers=headers,
            json=payload,
            verify=False,
            timeout=60,
        )

    try:
        res = _post(token)
    except requests.RequestException as ex:
        logger.warning(
            "Altiplano POST (%s): error de red access_id=%s NE=%s",
            log_label,
            access_id,
            ne,
        )
        return {"ok": False, "message": f"Error de red: {ex}"}

    if res.status_code in (401, 403):
        token_new = _obtener_token(
            auth_url, username=username, password=password, force_refresh=True
        )
        if token_new:
            try:
                res = _post(token_new)
            except requests.RequestException as ex:
                return {"ok": False, "message": f"Error de red: {ex}"}

    if res.status_code in ok_statuses:
        return {"ok": True, "status_code": res.status_code}

    msg = _extract_altiplano_error_message(res)
    return {
        "ok": False,
        "message": msg or f"HTTP {res.status_code}",
        "status_code": res.status_code,
    }


def cambiar_admin_status_ont(
    access_id: str,
    object_name_raw: str,
    operador: str,
    admin_status: str,
    *,
    ne: str | None = None,
) -> dict:
    """
    Bloquea o desbloquea la ONT (admin lock) vía EMA INP.

    Misma API que Network Views: ``POST …/ema/entity/…/ONT/{NE}/{onu}`` con
    ``{"adminStatus":"LOCKED"}`` o ``{"adminStatus":"UNLOCKED"}`` (HAR).
    """
    status = str(admin_status or "").strip().upper()
    if status not in ("LOCKED", "UNLOCKED"):
        return {"ok": False, "message": "admin_status debe ser LOCKED o UNLOCKED"}

    obj = str(object_name_raw or "").strip()
    if not obj or obj == "—":
        return {"ok": False, "message": "object_name de ONT requerido"}

    ne_val = (ne or "").strip() or _ne_from_object_name_raw(obj)
    if not ne_val:
        return {"ok": False, "message": "No se pudo derivar NE desde object_name"}

    host, port, base_url = get_altiplano_nbi_target("INP")
    if not host or not port or not base_url:
        return {"ok": False, "message": "Entorno NBI INP no configurado"}

    op = str(operador or "").strip().upper()
    user, pwd = get_altiplano_operator_credentials("INP")
    if not user or not pwd:
        user, pwd = get_altiplano_operator_credentials(op)
    if not user or not pwd:
        user, pwd = get_altiplano_credentials()
    if not user or not pwd:
        return {"ok": False, "message": "Credenciales Altiplano INP no configuradas"}

    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"
    base_host = f"{host}:{port}"
    url = _ema_entity_resource_url(base_host, "inp", ne_val, obj)
    payload = {"adminStatus": status}

    out = _http_post_altiplano_expect_ok(
        url,
        auth_url,
        payload,
        access_id=str(access_id or "").strip(),
        ne=ne_val,
        log_label=f"EMA admin {status}",
        username=user,
        password=pwd,
    )
    if out.get("ok"):
        label = "Locked" if status == "LOCKED" else "Unlocked"
        out["admin_status"] = status
        out["message"] = f"ONT {label.lower()} correctamente en Altiplano"
    return out


def _http_get_altiplano_json(
    url: str,
    auth_url: str,
    *,
    access_id: str,
    ne: str,
    log_label: str,
    accept: str = "application/json",
    username: str | None = None,
    password: str | None = None,
) -> object | None:
    token = _obtener_token(auth_url, username=username, password=password)
    if not token:
        logger.warning(
            "Altiplano potencias (%s): sin token (auth_url=%s access_id=%s)",
            log_label,
            auth_url,
            access_id,
        )
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
    }

    def _get(bearer: str):
        headers["Authorization"] = f"Bearer {bearer}"
        return requests.get(url, headers=headers, verify=False, timeout=60)

    try:
        res = _get(token)
    except requests.RequestException:
        logger.warning(
            "Altiplano potencias (%s): error de red access_id=%s NE=%s",
            log_label,
            access_id,
            ne,
        )
        return None

    if res.status_code in (401, 403):
        token_new = _obtener_token(
            auth_url, username=username, password=password, force_refresh=True
        )
        if not token_new:
            logger.warning(
                "Altiplano potencias (%s): sin token tras HTTP %s access_id=%s NE=%s",
                log_label,
                res.status_code,
                access_id,
                ne,
            )
            return None
        try:
            res = _get(token_new)
        except requests.RequestException:
            logger.warning(
                "Altiplano potencias (%s): error de red tras refrescar token access_id=%s NE=%s",
                log_label,
                access_id,
                ne,
            )
            return None

    if res.status_code != 200:
        msg = (
            "Altiplano potencias (%s): HTTP %s access_id=%s NE=%s",
            log_label,
            res.status_code,
            access_id,
            ne,
        )
        # 404 habitual si la ONT no está en ese VNO (p. ej. prueba TASA e INP).
        if res.status_code == 404:
            logger.debug(*msg)
        else:
            logger.warning(*msg)
        return None

    return _json_loads_altiplano_http_response(res)


def _fetch_ont_telemetry_live(
    access_id: str,
    object_name_raw: str,
    operator_id,
    ne: str,
) -> dict[str, object | None]:
    """
    TX/RX (RESTCONF + EMA), SN (EMA) y estado oper/admin/health (Network Views).

    Returns:
        ``tx``, ``rx``, ``sn``, ``oper``, ``admin``, ``health``, ``health_ts``.
    """
    out: dict[str, object | None] = {
        "tx": None,
        "rx": None,
        "sn": None,
        "oper": None,
        "admin": None,
        "health": None,
        "health_ts": None,
    }
    contexts = _power_auth_contexts(operator_id)
    if not contexts:
        logger.warning(
            "Altiplano telemetría: sin credenciales/endpoint (access_id=%s operator_id=%s)",
            access_id,
            operator_id,
        )
        return out

    for vno, auth_url, user, pwd in contexts:
        base_host = auth_url.split("/")[2]
        if out["tx"] is None or out["rx"] is None:
            restconf_body = _http_get_altiplano_json(
                _restconf_potencias_url(base_host, vno, ne, object_name_raw),
                auth_url,
                access_id=access_id,
                ne=ne,
                log_label=f"RESTCONF diagnostics ({vno})",
                accept="application/yang-data+json",
                username=user,
                password=pwd,
            )
            pair = _potencias_from_diagnostics_body(restconf_body)
            if pair is not None:
                out["tx"], out["rx"] = pair

        ema_body = _http_get_altiplano_json(
            _ema_potencias_url(base_host, vno, ne, object_name_raw),
            auth_url,
            access_id=access_id,
            ne=ne,
            log_label=f"EMA entity ({vno})",
            username=user,
            password=pwd,
        )
        onu_detected_ts = None

        def _merge_onu_detected(body: object | None) -> None:
            nonlocal onu_detected_ts
            ts = _onu_detected_datetime_from_ema(body)
            if not ts:
                return
            onu_detected_ts = _newest_altiplano_iso_timestamp(onu_detected_ts, ts)

        if ema_body:
            if out["sn"] is None:
                out["sn"] = _sn_from_ema_entity_body(ema_body)
            if out["tx"] is None or out["rx"] is None:
                pair = _potencias_from_ema_entity_body(ema_body)
                if pair is not None:
                    out["tx"], out["rx"] = pair
            if out["oper"] is None:
                out["oper"] = _ema_top_level_state(ema_body, "operationState")
            _merge_onu_detected(ema_body)

        if out["admin"] is None:
            ema_admin_body = _http_get_altiplano_json(
                _ema_entity_url(
                    base_host,
                    vno,
                    ne,
                    object_name_raw,
                    fetch_device_attributes=False,
                    is_one=False,
                ),
                auth_url,
                access_id=access_id,
                ne=ne,
                log_label=f"EMA admin ({vno})",
                username=user,
                password=pwd,
            )
            if ema_admin_body:
                out["admin"] = _ema_top_level_state(ema_admin_body, "adminStatus")
                _merge_onu_detected(ema_admin_body)

        if out["health"] is None:
            full_target = _ont_connection_full_target(object_name_raw, operator_id)
            if full_target:
                health = _fetch_intent_health_inp(
                    access_id,
                    full_target,
                    username=user,
                    password=pwd,
                )
                if health.get("health"):
                    out["health"] = health["health"]
                if health.get("health_ts"):
                    out["health_ts"] = health["health_ts"]

        if out["health"] is None and str(out.get("oper") or "").strip().upper() == "UP":
            out["health"] = "Healthy"

        if out.get("health") or out.get("health_ts") or onu_detected_ts:
            out["health_ts"] = _nv_health_display_timestamp(
                out.get("health_ts"),
                onu_detected_ts,
                oper=out.get("oper"),
                health=out.get("health"),
            )

        if (
            out["tx"] is not None
            and out["rx"] is not None
            and out["sn"]
            and out["oper"]
            and out["admin"]
            and out["health"]
        ):
            break

    return out


def _ont_gpon_interface_suffix(object_name_raw: str) -> str:
    """Sufijo GPON de la ONT (p. ej. ``v1~BA_OLTA_SF01_04-7-1-5_GPON``)."""
    onu = normalizar_object_name(str(object_name_raw or "").strip())
    if not onu:
        return ""
    return f"v1~{onu}_GPON"


def _alarm_resource_raw_paths(ne: str, object_name_raw: str) -> list[str]:
    """Rutas ``alarmResource.raw`` usadas por Network Views (HAR / AC INP)."""
    ne_val = str(ne or "").strip()
    gpon = _ont_gpon_interface_suffix(object_name_raw)
    if not ne_val or not gpon:
        return []
    prefix = (
        f"/anv:device-manager/anv-device-holders:device={ne_val}/"
        "device-specific-data"
    )
    onu_key = normalizar_object_name(str(object_name_raw or "").strip())
    paths = [
        f"{prefix}/ietf-interfaces:interfaces/interface={gpon}",
        f"{prefix}/bbf-fiber-onu-emulated-mount:onus/onu={gpon}",
        f"{prefix}/bbf-fiber-onu-emulated-mount:onus/onu={gpon}/root/"
        "ietf-hardware-mounted:hardware/component=ANIPORT",
        f"{prefix}/bbf-fiber-onu-emulated-mount:onus/onu={gpon}/root/"
        "ietf-hardware-mounted:hardware/component=CHASSIS",
    ]
    if onu_key:
        paths.append(
            f"{prefix}/bbf-fiber-onu-emulated-mount:onus/onu=v1~{onu_key}_GPON"
        )
    return paths


def _build_alarmas_activas_search_query(ne: str, object_name_raw: str) -> dict | None:
    paths = _alarm_resource_raw_paths(ne, object_name_raw)
    if not paths:
        return None
    should: list[dict] = [{"match": {"alarmResource.raw": p}} for p in paths]
    gpon = _ont_gpon_interface_suffix(object_name_raw)
    onu_key = normalizar_object_name(str(object_name_raw or "").strip())
    if gpon:
        should.append({"wildcard": {"alarmResource.raw": f"*{gpon}*"}})
    if onu_key:
        should.append({"wildcard": {"alarmResourceUiName": f"*{onu_key}_GPON*"}})
        should.append({"wildcard": {"alarmResourceUiName": f"*{onu_key}*"}})
    return {
        "query": {
            "bool": {
                "must": [
                    {"bool": {"should": [{"term": {"alarmStatus": "Active"}}]}},
                    {"bool": {"should": should, "minimum_should_match": 1}},
                ]
            }
        }
    }


def _parse_alarmas_activas_search_body(body: object) -> list[dict]:
    """Normaliza hits de ``/rest/alarm/alarms/search`` (índice ``alarms-active``)."""
    if not isinstance(body, dict):
        return []
    hits_wrap = body.get("hits")
    if not isinstance(hits_wrap, dict):
        return []
    items = hits_wrap.get("hits")
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        src = item.get("_source")
        if not isinstance(src, dict):
            continue
        if str(src.get("alarmStatus") or "").strip().lower() != "active":
            continue
        cleared_raw = src.get("clearedTime")
        cleared = ""
        if cleared_raw is not None and str(cleared_raw).strip() not in ("", "-"):
            cleared = str(cleared_raw).strip()
        out.append(
            {
                "severity": str(src.get("alarmSeverity") or "").strip(),
                "status": str(src.get("alarmStatus") or "").strip(),
                "type": str(src.get("alarmType") or "").strip(),
                "raised": str(src.get("raisedTime") or "").strip(),
                "cleared": cleared,
                "resource": str(
                    src.get("alarmResourceUiName") or src.get("alarmResource") or ""
                ).strip(),
                "text": str(
                    src.get("alarmText") or src.get("additionalInfo") or ""
                ).strip(),
                "main_device": str(src.get("mainDeviceRefId") or "").strip(),
                "repair": str(src.get("proposedRepairAction") or "").strip(),
                "service_affecting": str(src.get("serviceAffecting") or "").strip(),
            }
        )
    out.sort(key=lambda a: a.get("raised") or "", reverse=True)
    return out


def _inp_alarm_search_url() -> tuple[str, str, str, str] | None:
    """URL y credenciales del buscador de alarmas en AC INP (como Network Views)."""
    host, port, base = get_altiplano_nbi_target("INP")
    if not host or not base:
        return None
    user, pwd = get_altiplano_operator_credentials("INP")
    if not user or not pwd:
        user, pwd = get_altiplano_credentials()
    if not user or not pwd:
        return None
    auth_url = f"https://{host}:{port}/{base}/rest/auth/login"
    search_url = (
        f"https://{host}:{port}/{base}/rest/alarm/alarms/search"
        "?index=alarms-active"
    )
    return search_url, auth_url, user, pwd


def obtener_alarmas_ont_activas(
    access_id: str,
    object_name_raw: str,
    operator_id,
    *,
    ne: str | None = None,
) -> list[dict]:
    """
    Alarmas activas de la ONT vía ``POST …/rest/alarm/alarms/search`` (AC INP).

    Misma API que la pestaña Alarms de Network Views (HAR ``10.200.4.101.har``).
    """
    _ = operator_id  # reservado; alarmas se consultan siempre en INP
    obj = str(object_name_raw or "").strip()
    if not obj:
        return []
    ne_val = (ne or "").strip() or _ne_from_object_name_raw(obj)
    if not ne_val:
        return []
    query = _build_alarmas_activas_search_query(ne_val, obj)
    if not query:
        return []
    ctx = _inp_alarm_search_url()
    if not ctx:
        return []
    search_url, auth_url, user, pwd = ctx
    body = _http_post_altiplano_json(
        search_url,
        auth_url,
        query,
        access_id=str(access_id or "").strip(),
        ne=ne_val,
        log_label="alarmas activas INP",
        username=user,
        password=pwd,
    )
    return _parse_alarmas_activas_search_body(body)


def obtener_telemetry_ont(
    access_id,
    object_name_raw,
    operator_id,
    *,
    ne: str | None = None,
) -> dict[str, object | None]:
    """TX/RX, SN y estado Network Views de una ONT vía Altiplano."""
    obj = str(object_name_raw or "").strip()
    empty = {
        "tx": None,
        "rx": None,
        "sn": None,
        "oper": None,
        "admin": None,
        "health": None,
        "health_ts": None,
    }
    if not obj:
        return empty
    ne_val = (ne or "").strip() or _ne_from_object_name_raw(obj)
    if not ne_val:
        return empty
    return _fetch_ont_telemetry_live(str(access_id or "").strip(), obj, operator_id, ne_val)


def obtener_potencias_ont(
    access_id,
    object_name_raw,
    operator_id,
    *,
    ne: str | None = None,
) -> tuple[float, float] | None:
    """
    TX/RX de una ONT en Altiplano (RESTCONF diagnostics; si falla, API EMA como la GUI).

    Args:
        access_id: Solo para logs.
        object_name_raw: ``object_name`` de inventario / aux.bajada_inventario.
        operator_id: ``operatorid`` de inventario (mapa por operador en este módulo).
        ne: Network Element; si se omite se deriva del ``object_name_raw``.

    Returns:
        ``(tx_dbm, rx_dbm)`` o ``None`` si no hay lectura.
    """
    telem = obtener_telemetry_ont(
        access_id, object_name_raw, operator_id, ne=ne
    )
    tx, rx = telem.get("tx"), telem.get("rx")
    if tx is None or rx is None:
        return None
    return float(tx), float(rx)


def obtener_sn_ont(
    access_id,
    object_name_raw,
    operator_id,
    *,
    ne: str | None = None,
) -> str | None:
    """Serial number (detectado) desde API EMA de Altiplano."""
    telem = obtener_telemetry_ont(
        access_id, object_name_raw, operator_id, ne=ne
    )
    sn = telem.get("sn")
    return str(sn).strip().upper() if sn else None


def obtener_potencias_por_cto(NE, onts_cto):
    """
    Obtiene TX/RX de Altiplano para ONTs de una CTO.

    Args:
        NE: Nombre del Network Element (OLT) en Altiplano.
        onts_cto: Lista de tuplas `(access_id, object_name_raw, operator_id)`.

    Returns:
        Diccionario `{access_id: (tx, rx)}` para ONTs con consulta exitosa.

    Notas:
        - Soporta TASA, DIRECTV, METROTEL, IPLAN y ATC (según ``operator_id`` de inventario).
        - Cuando una ONT falla, se omite y el proceso continúa con el resto.
    """

    resultados = {}

    if not NE or not onts_cto:
        return resultados

    tasks = []
    for access_id, object_name_raw, operator_id in onts_cto:
        target = _ALTIPLANO_POWER_TARGETS_BY_OPERATOR_ID.get(operator_id)
        if target is None:
            continue
        vno, auth_url = target
        tasks.append((str(access_id), object_name_raw, operator_id, vno, auth_url))

    if not tasks:
        return resultados

    def _fetch_one(access_id, object_name_raw, operator_id, vno, auth_url):
        _ = vno, auth_url
        telem = _fetch_ont_telemetry_live(access_id, object_name_raw, operator_id, NE)
        tx, rx = telem.get("tx"), telem.get("rx")
        if tx is None or rx is None:
            return access_id, None
        return access_id, (float(tx), float(rx))

    max_workers = min(len(tasks), get_altiplano_power_workers())
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_fetch_one, access_id, object_name_raw, operator_id, vno, auth_url)
            for access_id, object_name_raw, operator_id, vno, auth_url in tasks
        ]
        for fut in as_completed(futures):
            aid, power = fut.result()
            if power is not None:
                resultados[aid] = power

    return resultados