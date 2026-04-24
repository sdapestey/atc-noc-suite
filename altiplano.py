import logging

import requests
import urllib3
from urllib.parse import quote

from config import (
    get_altiplano_credentials,
    get_altiplano_nbi_target,
    get_altiplano_operator_credentials,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Cache simple de tokens por auth_url
_token_cache = {}


def _extract_altiplano_error_message(response: requests.Response) -> str:
    """Obtiene un mensaje de error breve desde una respuesta HTTP de Altiplano."""
    try:
        body = response.json()
        msg = body.get("errors") or body.get("error-message") or str(body)
    except ValueError:
        msg = (response.text or "").strip()
    return msg[:260] if msg else f"HTTP {response.status_code}"


def _obtener_token(auth_url, username=None, password=None, force_refresh=False):
    """
    Devuelve un token cacheado para Altiplano.
    Si no existe, autentica y lo guarda.
    """
    if force_refresh:
        _token_cache.pop(auth_url, None)
    if auth_url in _token_cache:
        return _token_cache[auth_url]

    user = username
    pwd = password
    if not user or not pwd:
        user, pwd = get_altiplano_credentials()
    if not user or not pwd:
        logger.warning("ALTIPLANO_USER / ALTIPLANO_PASSWORD no configurados")
        return None

    auth = requests.post(
        auth_url, auth=(user, pwd), verify=False, timeout=60
    )
    if auth.status_code != 200:
        return None

    token = auth.json().get("accessToken")
    if token:
        _token_cache[auth_url] = token
    return token


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
):
    """
    Crea un intent `ont-connection` en Altiplano.

    Args:
        operador: Operador de negocio (credenciales por operador).
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

    username, pwd = get_altiplano_operator_credentials(op)
    if not username or not pwd:
        return {"ok": False, "message": f"Credenciales no configuradas para operador {op}"}

    auth_url = f"https://{host}:{port}/{base_url}/rest/auth/login"
    token = _obtener_token(auth_url, username=username, password=pwd)
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
    return {"ok": False, "message": f"Altiplano rechazó la operación: {msg}"}


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


def obtener_potencias_por_cto(NE, onts_cto):
    """
    Obtiene TX/RX de Altiplano para ONTs de una CTO.

    Args:
        NE: Nombre del Network Element (OLT) en Altiplano.
        onts_cto: Lista de tuplas `(access_id, object_name_raw, operator_id)`.

    Returns:
        Diccionario `{access_id: (tx, rx)}` para ONTs con consulta exitosa.

    Notas:
        - Actualmente soporta dominios/operadores TASA y DIRECTV.
        - Cuando una ONT falla, se omite y el proceso continúa con el resto.
    """

    resultados = {}

    if not NE or not onts_cto:
        return resultados

    for access_id, object_name_raw, operator_id in onts_cto:

        # Selección de dominio según operador
        if operator_id == 1001:
            vno = "tasa"
            auth_url = "https://10.200.4.101:32443/tasa-altiplano-ac/rest/auth/login"
        elif operator_id == 3001:
            vno = "dtv"
            auth_url = "https://10.200.7.107:32443/dtv-altiplano-ac/rest/auth/login"
        else:
            continue

        token = _obtener_token(auth_url)
        if not token:
            continue

        base_host = auth_url.split("/")[2]

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/yang-data+json",
            "Content-Type": "application/yang-data+json"
        }

        # Normalización + URL encoding (CRÍTICO)
        object_name_altiplano = normalizar_object_name(object_name_raw)
        onu_encoded = quote(object_name_altiplano, safe="")

        power_url = (
            f"https://{base_host}/{vno}-altiplano-ac/rest/restconf/data/"
            f"anv:device-manager/anv-device-holders:device={NE}/"
            f"device-specific-data/bbf-fiber-onu-emulated-mount:onus/"
            f"onu={onu_encoded}_GPON/root/"
            f"ietf-hardware-mounted:hardware-state/component=ANIPORT/"
            f"bbf-hardware-transceivers-mounted:transceiver-link/diagnostics"
            f"?altiplano-target=INP"
        )

        r = requests.get(power_url, headers=headers, verify=False, timeout=60)
        if r.status_code != 200:
            continue

        try:
            diagnostics = r.json()["bbf-hardware-transceivers-mounted:diagnostics"]

            tx = round(
                diagnostics["nokia-hardware-transceivers-dbm-mounted:tx-power-dbm"] * 0.1,
                2
            )
            rx = round(
                diagnostics["nokia-hardware-transceivers-dbm-mounted:rx-power-dbm"] * 0.1,
                2
            )

            resultados[str(access_id)] = (tx, rx)

        except Exception as ex:
            logger.debug(
                "Altiplano: sin diagnostics para access_id=%s: %s", access_id, ex
            )
            continue

    return resultados