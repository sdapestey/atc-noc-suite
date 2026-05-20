"""Exportación CSV (reutiliza servicios de inventario y dashboards)."""
import csv
import io

from db import db_cursor
from .dashboard_olt import dashboard_olts
from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    canonical_operador_consulta,
    nombre_operador,
    operadores_consulta_coinciden,
    region_desde_rama,
    split_index_query_tokens,
)
from .inventory import (
    _access_lookup_token_ok,
    consultar_access_id_baja_o_ausente,
    consultar_access_id_detalle_desde_bajada_inventario,
    consultar_cto_estructura,
    consultar_rama_estructura,
)

_IN_SERVICE_STATUS = "IN SERVICE"


def _export_row_in_service(row: dict) -> bool:
    st = row.get("STATUS") if row.get("STATUS") is not None else row.get("Status")
    return str(st or "").strip().upper() == _IN_SERVICE_STATUS


def _export_operador_ok(row: dict, operador: str | None) -> bool:
    return operadores_consulta_coinciden(row.get("OPERADOR"), operador)


def _export_index_inventory_rows(rows, operador: str | None = None):
    for r in rows or []:
        if not _export_row_in_service(r):
            continue
        if not _export_operador_ok(r, operador):
            continue
        yield r


def export_dashboard_ramas_csv() -> str:
    """Genera CSV plano del dashboard RAMA.

    Returns:
        String CSV UTF-8 (sin BOM) listo para enviar en response HTTP.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["PRINCIPAL", "RAMA", "CTO", "AID", "OPERADOR", "ONT", "TX", "RX"])
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT
                f.path_atc AS rama,
                f.location_description AS cto,
                f.access_id,
                o.invocator_system,
                REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui
            FROM cm.inventory_fat_occupation f
            JOIN cm.inventory_olt_occupation o
              ON o.access_id = f.access_id
            LEFT JOIN altiplano.serial s
              ON s.access_id = f.access_id
            WHERE f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
              AND f.path_atc IS NOT NULL
            ORDER BY f.path_atc, f.location_description, f.access_id
            """
        )
        rows = cur.fetchall()

    for rama, cto, aid, op_id, object_name_ui in rows:
        reg = region_desde_rama(rama)
        principal = SITIO_PRINCIPAL_POR_REGION.get(reg, SITIO_PRINCIPAL_DEFAULT)
        w.writerow([
            principal,
            rama,
            cto,
            str(aid),
            nombre_operador(op_id),
            (object_name_ui or "").strip() or "—",
            "",
            "",
        ])
    return buf.getvalue()


def export_dashboard_olts_csv() -> str:
    """Genera CSV de filas LT por OLT.

    Returns:
        String CSV UTF-8 (sin BOM) con métricas por LT.
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "PRINCIPAL", "SITIO_CODIGO", "OLT_LOGICO", "LT",
        "RAMAS", "CTO_COUNT", "ONT_COUNT", "ROJAS", "AMARILLAS", "VERDES", "PEOR_RX",
    ])
    for bloque in dashboard_olts():
        principal = bloque["PRINCIPAL"]
        for o in bloque["OLTS"]:
            for row in o["LTS"]:
                pr = row.get("PEOR_RX")
                w.writerow([
                    principal,
                    o["SITIO_CODIGO"],
                    o["OLT_LOGICO"],
                    row["LT"],
                    row["RAMAS"],
                    row["CTO_COUNT"],
                    row["ONT_COUNT"],
                    row["ROJAS"],
                    row["AMARILLAS"],
                    row["VERDES"],
                    pr if pr is not None else "",
                ])
    return buf.getvalue()


def _export_csv_append_in_service_summary(body: str, ont_count: int, *, operador: str | None = None) -> str:
    """Añade al final del CSV una fila con el total de ONT IN SERVICE exportadas."""
    out_buf = io.StringIO()
    w = csv.writer(out_buf)
    for row in csv.reader(io.StringIO(body)):
        w.writerow(row)
    w.writerow([])
    op_filter = (operador or "").strip()
    if op_filter and op_filter.upper() != "ALL":
        w.writerow(["# resumen", f"ONT IN SERVICE ({op_filter})", ont_count])
    else:
        w.writerow(["# resumen", "ONT IN SERVICE", ont_count])
    return out_buf.getvalue()


def _export_index_query_csv_one(value: str, *, operador: str | None = None) -> tuple[str, int]:
    """CSV para un único token (AID, CTO FATC o RAMA RATC).

    Solo filas IN SERVICE; ``operador`` opcional filtra por OPERADOR (omitir o ALL = todos).
    Returns:
        Par (contenido CSV sin pie de resumen, cantidad de filas IN SERVICE exportadas).
    """
    buf = io.StringIO()
    w = csv.writer(buf)
    ont_exported = 0
    value = (value or "").strip()
    value_upper = value.upper()
    if not value:
        w.writerow(["error", "valor vacío"])
        return buf.getvalue(), 0

    is_access_id_lookup = value.isdigit() or (
        _access_lookup_token_ok(value)
        and "FATC" not in value_upper
        and "RATC" not in value_upper
    )

    if is_access_id_lookup:
        res = consultar_access_id_detalle_desde_bajada_inventario(value)
        if res:
            w.writerow(["AID", "OPERADOR", "Status", "CTO", "RAMA", "ONT", "SN", "fuente"])
            if _export_row_in_service(res) and _export_operador_ok(res, operador):
                w.writerow([
                    res["AID"],
                    res["OPERADOR"],
                    res["Status"],
                    res["CTO"],
                    res.get("RAMA") or "",
                    res["ONT"],
                    res.get("SN", ""),
                    res.get("fuente_detalle", ""),
                ])
                ont_exported = 1
            return buf.getvalue(), ont_exported
        aid_info = consultar_access_id_baja_o_ausente(value)
        if aid_info.get("tipo") == "baja":
            w.writerow([
                "estado",
                "AID",
                "OPERADOR",
                "fecha_baja",
                "CTO",
                "ONT",
                "fuente_baja",
            ])
            w.writerow([
                "baja",
                aid_info.get("AID", ""),
                aid_info.get("OPERADOR", ""),
                aid_info.get("fecha_baja_fmt", ""),
                aid_info.get("CTO") or "",
                aid_info.get("ONT") or "",
                aid_info.get("fuente_baja", ""),
            ])
            return buf.getvalue(), 0
        if aid_info.get("tipo") == "no_existe":
            w.writerow(["error", "Access ID no encontrado en sistemas ATC"])
            return buf.getvalue(), 0
        w.writerow(["error", "sin datos"])
        return buf.getvalue(), 0
    elif "FATC" in value_upper:
        rows = consultar_cto_estructura(value)
        w.writerow(["OUT", "AID", "OPERADOR", "PRINCIPAL", "RAMA", "ONT", "STATUS"])
        for i, r in enumerate(_export_index_inventory_rows(rows, operador), start=1):
            ont_exported += 1
            w.writerow([
                i,
                r["AID"],
                r["OPERADOR"],
                r.get("PRINCIPAL", ""),
                r["RAMA"],
                r["ONT"],
                r["STATUS"],
            ])
    elif "RATC" in value_upper:
        data = consultar_rama_estructura(value)
        w.writerow(["CTO", "OUT", "AID", "OPERADOR", "SITIO", "ONT", "STATUS"])
        for cto, rows in data.items():
            out_i = 0
            for r in _export_index_inventory_rows(rows, operador):
                out_i += 1
                ont_exported += 1
                w.writerow([
                    cto,
                    out_i,
                    r["AID"],
                    r["OPERADOR"],
                    r.get("PRINCIPAL", ""),
                    r["ONT"],
                    r["STATUS"],
                ])
    else:
        w.writerow(["error", "usar Access ID, FATC o RATC"])
    return buf.getvalue(), ont_exported


def export_index_csv_filename(value: str, *, operador: str | None = None) -> str:
    """Nombre de archivo para exportación del índice (consulta masiva / individual)."""
    op_raw = (operador or "").strip()
    if op_raw and op_raw.upper() != "ALL":
        op_name = canonical_operador_consulta(op_raw) or op_raw.upper()
        return f"Clientes {op_name}.csv"
    tokens = split_index_query_tokens(value)
    n_ramas = sum(1 for t in tokens if "RATC" in (t or "").upper())
    if n_ramas == 0:
        n_ramas = len(tokens) or 1
    return f"Clientes {n_ramas} ramas.csv"


def export_index_query_csv(value: str, *, operador: str | None = None) -> str:
    """Exporta a CSV una búsqueda del índice (`/`).

    Acepta varios valores separados por coma o salto de línea; cada uno se exporta
    en bloques consecutivos con una fila marcadora ``# consulta``.
    Solo incluye filas IN SERVICE; ``operador`` filtra por OPERADOR si se indica.
    """
    tokens = split_index_query_tokens(value)
    if not tokens:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["error", "valor vacío"])
        return buf.getvalue()
    if len(tokens) == 1:
        body, ont_total = _export_index_query_csv_one(tokens[0], operador=operador)
        return _export_csv_append_in_service_summary(body, ont_total, operador=operador)

    out_buf = io.StringIO()
    w = csv.writer(out_buf)
    ont_total = 0
    for i, t in enumerate(tokens):
        if i > 0:
            w.writerow([])
        w.writerow(["# consulta", t])
        sub, sub_n = _export_index_query_csv_one(t, operador=operador)
        ont_total += sub_n
        for row in csv.reader(io.StringIO(sub)):
            w.writerow(row)
    return _export_csv_append_in_service_summary(out_buf.getvalue(), ont_total, operador=operador)
