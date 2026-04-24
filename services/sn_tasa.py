"""Normalización de SN para cambio vía NBI (solo operador TASA)."""
from __future__ import annotations

import re

_HEX16 = re.compile(r"^[0-9A-F]{16}$")
_ASKY_HEX_PREFIX = "41534B59"  # ASCII "ASKY" en hex
_MSTC_HEX_PREFIX = "4D535443"  # ASCII "MSTC" en hex
_ASKY_MSTC_SUFFIX = re.compile(r"^[0-9A-F]{8}$")


def normalize_tasa_change_sn(raw: str) -> str:
    """
    Normaliza el SN ingresado por el usuario en flujo «Cambiar SN» (TASA).

    Reglas:
    - Si el valor es exactamente 16 caracteres hex y empieza por el prefijo
      hex de ASKY (41534B59): se envía ``ASKY`` + los últimos 8 hex del string.
    - Igual para MSTC (prefijo 4D535443): ``MSTC`` + últimos 8 hex.
    - Si ya viene ``ASKY``/``MSTC`` + 8 hex (12 caracteres), se deja en mayúsculas.
    - En cualquier otro caso se devuelve trim + mayúsculas (comportamiento previo).

    Args:
        raw: Serial ingresado por usuario.

    Returns:
        Serial normalizado para enviar al endpoint NBI de TASA.
    """
    s = (raw or "").strip().upper()
    if not s:
        return s

    if len(s) == 16 and _HEX16.match(s):
        if s.startswith(_ASKY_HEX_PREFIX):
            return "ASKY" + s[-8:]
        if s.startswith(_MSTC_HEX_PREFIX):
            return "MSTC" + s[-8:]
        return s

    if len(s) == 12:
        if s.startswith("ASKY") and _ASKY_MSTC_SUFFIX.match(s[4:]):
            return s
        if s.startswith("MSTC") and _ASKY_MSTC_SUFFIX.match(s[4:]):
            return s

    return s
