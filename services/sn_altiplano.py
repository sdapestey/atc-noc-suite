"""Normalización y validación de serial para cambio SN en Altiplano (NBI)."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path


def _load_sn_tasa_module():
    path = Path(__file__).resolve().parent / "sn_tasa.py"
    spec = importlib.util.spec_from_file_location("sn_tasa", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# YANG ``expected-serial-number`` (GUI / NBI): 4 alfanuméricos + 8 hex.
ONT_SN_YANG_PATTERN = re.compile(r"^[A-Z0-9]{4}[0-9A-F]{8}$")
_HEX16 = re.compile(r"^[0-9A-F]{16}$")

# Prefijos ASCII en hex (16 caracteres del rotulo → 12 para Altiplano).
_VENDOR_HEX_PREFIX_TO_LABEL: dict[str, str] = {
    "41534B59": "ASKY",
    "4D535443": "MSTC",
    "53444D43": "SDMC",
    "414C434C": "ALCL",
}


def normalize_change_sn(raw: str, operador: str | None = None) -> str:
    """
    Serial listo para ``expected-serial-number`` en RESTCONF.

    - TASA: reglas ASKY/MSTC (``services.sn_tasa``).
    - Resto (DIRECTV, METROTEL, …): si viene 16 hex con prefijo de fabricante conocido,
      convierte a ``XXXX`` + últimos 8 hex (p. ej. ``53444D435C73B3AF`` → ``SDMC5C73B3AF``).
    """
    op = (operador or "").strip().upper()
    if op == "TASA":
        return _load_sn_tasa_module().normalize_tasa_change_sn(raw)

    s = (raw or "").strip().upper()
    if not s:
        return s
    if ONT_SN_YANG_PATTERN.match(s):
        return s
    if len(s) == 16 and _HEX16.match(s):
        for prefix_hex, label in _VENDOR_HEX_PREFIX_TO_LABEL.items():
            if s.startswith(prefix_hex):
                return label + s[-8:]
    return s


def validate_ont_sn_for_altiplano(sn: str) -> str | None:
    """``None`` si el SN cumple el patrón YANG; si no, mensaje para el usuario."""
    s = (sn or "").strip().upper()
    if not s:
        return "SN requerido"
    if ONT_SN_YANG_PATTERN.match(s):
        return None
    return (
        "SN inválido para Altiplano: deben ser 12 caracteres "
        "(4 letras/números + 8 hex), por ejemplo SDMC5C73B3AF. "
        "Si pegás el serial de 16 dígitos hex del rótulo de la ONT, "
        "usá el valor completo y el sistema lo convertirá automáticamente."
    )
