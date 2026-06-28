"""Constantes de negocio y helpers sin acceso a base de datos."""
from __future__ import annotations

import re
from typing import Any

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

# Operadores del dashboard Calidad Inventario (tarjetas, conciliación, estadísticas).
CALIDAD_OPERATORS: tuple[dict[str, str | tuple[str, ...]], ...] = (
    {"id": "1001", "label": "TASA", "vno": "1001"},
    {"id": "3001", "label": "DTV", "vno": "3001"},
    {"id": "3950", "label": "iPlan", "vno": "3950"},
    {"id": "4000", "label": "Metrotel", "vno": "4000", "member_ids": ("4000", "4010")},
    {"id": "2800", "label": "ATC", "vno": "2800", "member_ids": ("2800", "2805", "2806")},
    {"id": "962", "label": "SION", "vno": "962", "member_ids": ("962", "963")},
)

_CALIDAD_RAW_TO_CANONICAL: dict[str, str] = {}
for _calidad_op in CALIDAD_OPERATORS:
    _canon = str(_calidad_op["id"])
    _members = _calidad_op.get("member_ids") or (_canon,)
    for _mid in _members:
        _CALIDAD_RAW_TO_CANONICAL[str(_mid)] = _canon


def calidad_operator_member_ids(meta: dict) -> tuple[str, ...]:
    """IDs en inventario/Altiplano que agrupan bajo un operador lógico del dashboard."""
    extra = meta.get("member_ids")
    if extra:
        return tuple(str(x) for x in extra)
    return (str(meta["id"]),)


def all_calidad_operator_member_ids() -> list[str]:
    seen: list[str] = []
    for op in CALIDAD_OPERATORS:
        for mid in calidad_operator_member_ids(op):
            if mid not in seen:
                seen.append(mid)
    return seen


def canonical_calidad_operator_id(raw) -> str:
    oid = str(raw or "").strip()
    return _CALIDAD_RAW_TO_CANONICAL.get(oid, "")


def calidad_operator_label(op_id: str) -> str:
    if not op_id:
        return "Todos"
    for op in CALIDAD_OPERATORS:
        if op["id"] == op_id:
            return op["label"]
    return op_id


OPERADORES_CONSULTA_ORDEN = ("TASA", "DIRECTV", "METROTEL", "IPLAN", "ATC", "SION")

_OPERADOR_CONSULTA_ALIASES: dict[str, str] = {
    "TASA": "TASA",
    "DIRECTV": "DIRECTV",
    "METROTEL": "METROTEL",
    "IPLAN": "IPLAN",
    "ATC": "ATC",
    "SION": "SION",
}

_OPERADOR_CONSULTA_OMITIR = frozenset({
    "",
    "-",
    "—",
    "0",
    "NONE",
    "NULL",
    "NAN",
    "N/A",
    "NA",
})

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
    if op_id is None:
        return ""
    if isinstance(op_id, int):
        return OPERADORES.get(op_id, str(op_id))
    s = str(op_id).strip()
    if not s:
        return ""
    if s.isdigit():
        n = int(s)
        if n in OPERADORES:
            return OPERADORES[n]
    return OPERADORES.get(op_id, s)


def _operador_consulta_key(op: str) -> str:
    return re.sub(r"\s+", "", (op or "").strip().upper())


def canonical_operador_consulta(op: str | None) -> str | None:
    """Etiqueta canónica de operador en Consulta, o None si no es válido (omitir 0, -, etc.)."""
    raw = (op or "").strip()
    if not raw:
        return None
    key = _operador_consulta_key(raw)
    if key in _OPERADOR_CONSULTA_OMITIR or raw in ("-", "—", "0"):
        return None
    return _OPERADOR_CONSULTA_ALIASES.get(key)


def operadores_consulta_coinciden(row_operador: str | None, filtro: str | None) -> bool:
    """True si el filtro es ALL o el operador de fila coincide (p. ej. DIRECTV en inventario)."""
    filt = (filtro or "").strip()
    if not filt or filt.upper() == "ALL":
        return True
    row_c = canonical_operador_consulta(row_operador)
    filt_c = canonical_operador_consulta(filt)
    return row_c is not None and filt_c is not None and row_c == filt_c


def sort_operadores_consulta(operadores) -> list[str]:
    """Operadores válidos en orden fijo para chips y totales."""
    seen: set[str] = set()
    valid: list[str] = []
    for raw in operadores or []:
        op = canonical_operador_consulta(str(raw).strip() if raw is not None else "")
        if not op or op in seen:
            continue
        seen.add(op)
        valid.append(op)
    order = {name: i for i, name in enumerate(OPERADORES_CONSULTA_ORDEN)}
    return sorted(valid, key=lambda x: order.get(x, 99))


def natural_sort_key_str(s: str | None):
    """Genera clave de orden natural (texto + números)."""
    if s is None:
        return ()
    parts = re.split(r"(\d+)", str(s))
    key = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            key.append((0, int(p)))
        else:
            key.append((1, p.lower()))
    return tuple(key)


def calcular_ne(object_name_raw: str) -> str:
    """Deriva el NE (`<OLT>.LT<n>`) desde `object_name` de Altiplano."""
    p = object_name_raw.split("-")
    return f"{p[0]}.LT{p[1]}"


def lt_desde_object_name(object_name_raw: str | None) -> str | None:
    """Deriva LT lógica desde `object_name`; retorna `None` si no aplica."""
    if not object_name_raw:
        return None
    p = object_name_raw.split("-")
    if len(p) < 2:
        return None
    return f"{p[0]}.LT{p[1]}"


def principal_y_sitio_desde_olt(olt_logico: str) -> tuple[str, str, str]:
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


def clasificar_rx_dbm(rx: Any) -> str | None:
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


def resumen_semaforo_desde_rx_values(rx_values) -> dict[str, int]:
    """Cuenta ROJAS / AMARILLAS / VERDES a partir de valores RX (``clasificar_rx_dbm``)."""
    out = {"ROJAS": 0, "AMARILLAS": 0, "VERDES": 0}
    for rx in rx_values:
        cat = clasificar_rx_dbm(rx)
        if cat == "rojo":
            out["ROJAS"] += 1
        elif cat == "amarillo":
            out["AMARILLAS"] += 1
        elif cat == "verde":
            out["VERDES"] += 1
    return out


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
