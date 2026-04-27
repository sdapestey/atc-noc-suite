"""Exportación CSV (reutiliza servicios de inventario y dashboards)."""
import csv
import io

from .dashboard_olt import dashboard_olts
from .dashboard_rama import dashboard_ramas, inventario_dashboard_rama
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
    for bloque in dashboard_ramas():
        principal = bloque["PRINCIPAL"]
        for r in bloque["RAMAS"]:
            rama = r["RAMA"]
            inventario = inventario_dashboard_rama(rama)
            for cto, onts in inventario.items():
                for o in onts:
                    w.writerow([
                        principal,
                        rama,
                        cto,
                        o["AID"],
                        o["OPERADOR"],
                        o.get("ONT") or "",
                        o.get("TX") if o.get("TX") is not None else "",
                        o.get("RX") if o.get("RX") is not None else "",
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


def export_index_query_csv(value: str) -> str:
    """Exporta a CSV una búsqueda del índice (`/`).

    Args:
        value: Valor buscado por el usuario (AID, FATC o RATC).

    Returns:
        String CSV con el resultado normalizado.

    Notes:
        Si no hay datos, devuelve una fila con `error` para facilitar lectura
        operativa en planillas.
    """
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
        w.writerow(["AID", "OPERADOR", "PRINCIPAL", "RAMA", "ONT", "SN", "STATUS"])
        for r in rows:
            w.writerow([
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
        w.writerow(["CTO", "AID", "OPERADOR", "ONT", "SN", "STATUS"])
        for cto, rows in data.items():
            for r in rows:
                w.writerow([cto, r["AID"], r["OPERADOR"], r["ONT"], r.get("SN", ""), r["STATUS"]])
    else:
        w.writerow(["error", "usar ID numérico, FATC o RATC"])
    return buf.getvalue()
