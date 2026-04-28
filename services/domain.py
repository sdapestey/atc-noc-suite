"""Constantes de negocio y helpers sin acceso a base de datos."""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

OPERADORES = {
    1001: "TASA",
    3001: "DIRECTV",
    3950: "IPLAN",
    4000: "METROTEL",
    4010: "METROTEL",
    962: "SION",
    963: "SION",
    2800: "ATC",
    2805: "ATC",
    2806: "ATC",
}

SITIO_PRINCIPAL_POR_REGION = {
    "MR01": "Moreno",
    "ES01": "Escobar",
    "SM01": "San Martín",
    "SM02": "San Martín",
    "TG01": "Tigre",
    "TG02": "Tigre",
    "VL01": "Vicente López",
    "SF01": "San Fernando",
    "SI01": "San Isidro",
    "SI02": "San Isidro",
    "SI03": "San Isidro",
}
SITIO_PRINCIPAL_DEFAULT = "Otros"

OLT_PRESENCIA_FORZADA = [
    "BA_OLTA_MR01_01",
    "BA_OLTA_MR01_02",
    "BA_OLTA_MR01_03",
]


def nombre_operador(op_id: Any) -> str:
    """Mapea `operator_id` a nombre comercial legible."""
    return OPERADORES.get(op_id, str(op_id))


def natural_sort_key_str(s: Optional[str]):
    """Genera clave de orden natural (texto + números)."""
    if s is None:
        return ()
    parts = re.split(r"(\d+)", str(s))
    key = []
    for p in parts:
        if p.isdigit():
            key.append(int(p))
        elif p:
            key.append(p.lower())
    return tuple(key)


def calcular_ne(object_name_raw: str) -> str:
    """Deriva el NE (`<OLT>.LT<n>`) desde `object_name` de Altiplano."""
    p = object_name_raw.split("-")
    return f"{p[0]}.LT{p[1]}"


def lt_desde_object_name(object_name_raw: Optional[str]) -> Optional[str]:
    """Deriva LT lógica desde `object_name`; retorna `None` si no aplica."""
    if not object_name_raw:
        return None
    p = object_name_raw.split("-")
    if len(p) < 2:
        return None
    return f"{p[0]}.LT{p[1]}"


def principal_y_sitio_desde_olt(olt_logico: str) -> Tuple[str, str, str]:
    """Obtiene sitio principal y código de sitio a partir del nombre de OLT."""
    o = (olt_logico or "").strip()
    m = re.match(r"^BA_OLTA_([A-Z]{2}\d{2})_(\d{2})$", o, re.I)
    if not m:
        return SITIO_PRINCIPAL_DEFAULT, o, o
    region = m.group(1).upper()
    suf = m.group(2)
    codigo = f"{region}_{suf}"
    principal = SITIO_PRINCIPAL_POR_REGION.get(region, SITIO_PRINCIPAL_DEFAULT)
    return principal, codigo, o


def principal_sort_key(nombre: str):
    """Clave de orden para sitios principales con prioridades de negocio."""
    prio = {"Moreno": 0, "Otros": 99}
    return (prio.get(nombre, 50), natural_sort_key_str(nombre))


def region_desde_rama(rama: str) -> str:
    """Extrae región base (ej. `TG01`) desde un identificador de rama."""
    if not rama:
        return ""
    s = str(rama).strip()
    head = s.split("-")[0].strip().upper()
    if re.match(r"^[A-Z]{2}\d{2}$", head):
        return head
    m = re.match(r"^([A-Z]{2}\d{2})", s.upper())
    if m:
        return m.group(1)
    return s[:4].upper() if len(s) >= 4 else s.upper()


def clasificar_rx_dbm(rx: Any) -> Optional[str]:
    """Clasifica RX dBm en `rojo`, `amarillo`, `verde` o `None`."""
    if rx is None:
        return None
    try:
        v = float(rx)
    except (TypeError, ValueError):
        return None
    if v < -27:
        return "rojo"
    if v <= -25:
        return "amarillo"
    return "verde"


def split_index_query_tokens(raw: str | None) -> list[str]:
    """Separa varios valores de consulta del índice por comas o saltos de línea."""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    normalized = s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", ",")
    out: list[str] = []
    for chunk in normalized.split(","):
        t = chunk.strip()
        if t:
            out.append(t)
    return out
