import logging

import requests
import urllib3
from urllib.parse import quote

from config import get_altiplano_credentials

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Cache simple de tokens por auth_url
_token_cache = {}


def _obtener_token(auth_url):
    """
    Devuelve un token cacheado para Altiplano.
    Si no existe, autentica y lo guarda.
    """
    if auth_url in _token_cache:
        return _token_cache[auth_url]

    user, password = get_altiplano_credentials()
    if not user or not password:
        logger.warning("ALTIPLANO_USER / ALTIPLANO_PASSWORD no configurados")
        return None

    auth = requests.post(
        auth_url, auth=(user, password), verify=False, timeout=60
    )
    if auth.status_code != 200:
        return None

    token = auth.json().get("accessToken")
    if token:
        _token_cache[auth_url] = token
    return token


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
    Obtiene TX / RX de Altiplano para una lista de ONT de una CTO.
    Replica el flujo efectivo de consulta_cto.py, pero de forma modular.
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