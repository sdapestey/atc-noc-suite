"""Exportación CSV (reutiliza servicios de inventario y dashboards)."""
import csv
import io

from db import db_cursor
from .dashboard_olt import dashboard_olts
from .domain import (
    SITIO_PRINCIPAL_DEFAULT,
    SITIO_PRINCIPAL_POR_REGION,
    nombre_operador,
    region_desde_rama,
    split_index_query_tokens,
)
from .inventory import (
    consultar_access_id_baja_o_ausente,
    consultar_access_id_detalle_desde_bajada_inventario,
    consultar_cto_estructura,
    consultar_rama_estructura,
)


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


def _export_index_query_csv_one(value: str) -> str:
    """CSV para un único token de búsqueda del índice (AID, CTO FATC o RAMA RATC)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    value = (value or "").strip()
    value_upper = value.upper()
    if not value:
        w.writerow(["error", "valor vacío"])
        return buf.getvalue()

    if value.isdigit():
        res = consultar_access_id_detalle_desde_bajada_inventario(value)
        if res:
            w.writerow(["AID", "OPERADOR", "Status", "CTO", "RAMA", "ONT", "SN", "fuente"])
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
            return buf.getvalue()
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
            return buf.getvalue()
        if aid_info.get("tipo") == "no_existe":
            w.writerow(["error", "Access ID no encontrado en sistemas ATC"])
            return buf.getvalue()
        w.writerow(["error", "sin datos"])
        return buf.getvalue()
    elif "FATC" in value_upper:
        rows = consultar_cto_estructura(value)
        w.writerow(["OUT", "AID", "OPERADOR", "PRINCIPAL", "RAMA", "ONT", "SN", "STATUS"])
        for i, r in enumerate(rows, start=1):
            w.writerow([
                i,
                r["AID"],
                r["OPERADOR"],
                r.get("PRINCIPAL", ""),
                r["RAMA"],
                r["ONT"],
                r.get("SN", ""),
                r["STATUS"],
            ])
    elif "RATC" in value_upper:
        data = consultar_rama_estructura(value)
        w.writerow(["CTO", "OUT", "AID", "OPERADOR", "ONT", "SN", "STATUS"])
        for cto, rows in data.items():
            for i, r in enumerate(rows, start=1):
                w.writerow([cto, i, r["AID"], r["OPERADOR"], r["ONT"], r.get("SN", ""), r["STATUS"]])
    else:
        w.writerow(["error", "usar ID numérico, FATC o RATC"])
    return buf.getvalue()


def export_index_query_csv(value: str) -> str:
    """Exporta a CSV una búsqueda del índice (`/`).

    Acepta varios valores separados por coma o salto de línea; cada uno se exporta
    en bloques consecutivos con una fila marcadora ``# consulta``.
    """
    tokens = split_index_query_tokens(value)
    if not tokens:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["error", "valor vacío"])
        return buf.getvalue()
    if len(tokens) == 1:
        return _export_index_query_csv_one(tokens[0])

    out_buf = io.StringIO()
    w = csv.writer(out_buf)
    for i, t in enumerate(tokens):
        if i > 0:
            w.writerow([])
        w.writerow(["# consulta", t])
        sub = _export_index_query_csv_one(t)
        for row in csv.reader(io.StringIO(sub)):
            w.writerow(row)
    return out_buf.getvalue()
