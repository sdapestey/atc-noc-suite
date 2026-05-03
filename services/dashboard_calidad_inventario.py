"""Dashboard de calidad de inventario (KPIs + hallazgos)."""
import csv
import io

from config import get_dashboard_calidad_cache_seconds
from db import db_cursor

from .dashboard_cache import get_cached_calidad_resumen

RULES = {
    "missing_serial_match": {
        "label": "Sin match en SERIAL",
        "description": (
            "Desde Altiplano: no hay en INP una ONT-connection ni el intent en el VNO para este access_id; "
            "en ConnectMaster el FAT sí está presente. Equivale operativamente a no haber match en "
            "altiplano.serial en este cruce."
        ),
    },
    "missing_olt_match": {
        "label": "Sin match en OLT",
        "description": (
            "Suele coincidir con ausencia de ONT-connection en INP y del intent del VNO en Altiplano, "
            "y en ConnectMaster con punto sin object name u ocupación OLT completa."
        ),
    },
    "missing_path_atc": {
        "label": "Path ATC nulo/vacio",
        "description": (
            "En ConnectMaster (FAT) no viene informado el path ATC para ese access_id (nulo o solo espacios)."
        ),
    },
    "blank_serial_number": {
        "label": "Serial nulo/vacio",
        "description": (
            "Suele verse puerto y punto en ConnectMaster; en Altiplano puede haber ONT-connection en INP y el lado VNO vacío."
        ),
    },
}
ALLOWED_BASE_STATUSES = ("IN SERVICE", "RESERVED", "TO BE DELETED", "FREE")


def _norm_rule(value: str | None) -> str:
    v = (value or "").strip()
    return v if v in RULES else ""


def _norm_operator(value: str | None) -> str:
    return (value or "").strip()


def _norm_q(value: str | None) -> str:
    return (value or "").strip()


def _norm_base_status(value: str | None) -> str:
    v = (value or "").strip().upper()
    return v if v in ALLOWED_BASE_STATUSES else ""


def _norm_limit(value, default: int = 500, max_allowed: int = 5000) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(max_allowed, n))


def _base_cte_sql() -> str:
    return """
    WITH fat_active AS (
        SELECT
            btrim(f.access_id) AS access_id,
            f.status AS base_status,
            MAX(NULLIF(btrim(f.path_atc), '')) AS path_atc,
            MAX(NULLIF(btrim(f.location_description), '')) AS cto
        FROM cm.inventory_fat_occupation f
        WHERE f.status IN ('IN SERVICE', 'RESERVED', 'TO BE DELETED', 'FREE')
          AND btrim(COALESCE(f.access_id, '')) <> ''
        GROUP BY btrim(f.access_id), f.status
    ),
    serial_by_aid AS (
        SELECT
            btrim(s.access_id) AS access_id,
            BOOL_OR(NULLIF(btrim(COALESCE(s.serial_number, '')), '') IS NOT NULL) AS has_serial_number
        FROM altiplano.serial s
        WHERE btrim(COALESCE(s.access_id, '')) <> ''
        GROUP BY btrim(s.access_id)
    ),
    olt_by_aid AS (
        SELECT
            btrim(o.access_id) AS access_id,
            BOOL_OR(o.invocator_system IS NOT NULL) AS has_invocator_system,
            MAX(CASE WHEN o.invocator_system IS NOT NULL THEN o.invocator_system::text END) AS operador
        FROM cm.inventory_olt_occupation o
        WHERE btrim(COALESCE(o.access_id, '')) <> ''
        GROUP BY btrim(o.access_id)
    )
    """


def dashboard_calidad_inventario_resumen() -> dict:
    """KPIs agregados de calidad sobre inventario IN SERVICE."""

    def _compute():
        sql = (
            _base_cte_sql()
            + """
        , fat_status_counts AS (
            SELECT
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'RESERVED')::int AS total_aid_reserved,
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'TO BE DELETED')::int AS total_aid_to_be_deleted,
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'FREE')::int AS total_aid_free
            FROM cm.inventory_fat_occupation f
            WHERE btrim(COALESCE(f.access_id, '')) <> ''
        )
        SELECT
            COUNT(*)::int AS total_aid_in_service,
            COUNT(*) FILTER (WHERE s.access_id IS NULL)::int AS aid_sin_match_serial,
            COUNT(*) FILTER (WHERE o.access_id IS NULL)::int AS aid_sin_match_olt,
            COUNT(*) FILTER (WHERE f.path_atc IS NULL)::int AS aid_path_atc_nulo_vacio,
            COUNT(*) FILTER (
                WHERE s.access_id IS NOT NULL
                  AND COALESCE(s.has_serial_number, FALSE) = FALSE
            )::int AS aid_serial_nulo_vacio,
            MAX(sc.total_aid_reserved)::int AS total_aid_reserved,
            MAX(sc.total_aid_to_be_deleted)::int AS total_aid_to_be_deleted,
            MAX(sc.total_aid_free)::int AS total_aid_free
        FROM fat_active f
        LEFT JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        CROSS JOIN fat_status_counts sc
        """
        )
        with db_cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

        (
            total,
            no_serial_match,
            no_olt_match,
            no_path,
            blank_serial,
            total_reserved,
            total_to_be_deleted,
            total_free,
        ) = row
        return {
            "total_aid_in_service": int(total or 0),
            "total_aid_reserved": int(total_reserved or 0),
            "total_aid_to_be_deleted": int(total_to_be_deleted or 0),
            "total_aid_free": int(total_free or 0),
            "aid_sin_match_serial": int(no_serial_match or 0),
            "aid_sin_match_olt": int(no_olt_match or 0),
            "aid_path_atc_nulo_vacio": int(no_path or 0),
            "aid_serial_nulo_vacio": int(blank_serial or 0),
        }

    return get_cached_calidad_resumen(get_dashboard_calidad_cache_seconds(), _compute)


def dashboard_calidad_inventario_hallazgos(
    regla: str | None = None,
    operador: str | None = None,
    estado_base: str | None = None,
    q: str | None = None,
    limit=500,
) -> dict:
    """Detalle de hallazgos de calidad por regla."""
    regla_norm = _norm_rule(regla)
    operador_norm = _norm_operator(operador)
    estado_base_norm = _norm_base_status(estado_base)
    q_norm = _norm_q(q)
    limit_norm = _norm_limit(limit)

    sql = (
        _base_cte_sql()
        + """
    , findings AS (
        SELECT
            'missing_serial_match'::text AS regla_id,
            %s::text AS regla,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        LEFT JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE s.access_id IS NULL

        UNION ALL

        SELECT
            'missing_olt_match'::text AS regla_id,
            %s::text AS regla,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            '—'::text AS operador
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE o.access_id IS NULL

        UNION ALL

        SELECT
            'missing_path_atc'::text AS regla_id,
            %s::text AS regla,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE f.path_atc IS NULL

        UNION ALL

        SELECT
            'blank_serial_number'::text AS regla_id,
            %s::text AS regla,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE COALESCE(s.has_serial_number, FALSE) = FALSE
    )
    SELECT
        regla_id,
        regla,
        access_id,
        base_status,
        COALESCE(path_atc, '—') AS path_atc,
        COALESCE(cto, '—') AS cto,
        operador
    FROM findings
    WHERE (%s = '' OR regla_id = %s)
      AND (%s = '' OR base_status = %s)
      AND (%s = '' OR operador = %s)
      AND (
          %s = ''
          OR access_id ILIKE ('%%' || %s || '%%')
          OR COALESCE(path_atc, '') ILIKE ('%%' || %s || '%%')
          OR COALESCE(cto, '') ILIKE ('%%' || %s || '%%')
      )
    ORDER BY
        regla,
        access_id
    LIMIT %s
    """
    )

    params = (
        RULES["missing_serial_match"]["label"],
        RULES["missing_olt_match"]["label"],
        RULES["missing_path_atc"]["label"],
        RULES["blank_serial_number"]["label"],
        regla_norm,
        regla_norm,
        estado_base_norm,
        estado_base_norm,
        operador_norm,
        operador_norm,
        q_norm,
        q_norm,
        q_norm,
        q_norm,
        limit_norm,
    )

    with db_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    findings = []
    for row in rows:
        regla_id, regla_label, access_id, base_status, path_atc, cto, operador_val = row
        findings.append({
            "regla_id": regla_id,
            "regla": regla_label,
            "access_id": access_id,
            "base_status": base_status,
            "path_atc": path_atc,
            "cto": cto,
            "operador": operador_val,
        })

    return {
        "rules": [
            {
                "id": rid,
                "label": meta["label"],
                **({"description": meta["description"]} if meta.get("description") else {}),
            }
            for rid, meta in RULES.items()
        ],
        "base_statuses": [{"id": s, "label": s} for s in ALLOWED_BASE_STATUSES],
        "filters": {
            "regla": regla_norm,
            "estado_base": estado_base_norm,
            "operador": operador_norm,
            "q": q_norm,
            "limit": limit_norm,
        },
        "count": len(findings),
        "findings": findings,
    }


def export_dashboard_calidad_inventario_csv(
    regla: str | None = None,
    operador: str | None = None,
    estado_base: str | None = None,
    q: str | None = None,
) -> str:
    """Exporta CSV de hallazgos para los filtros aplicados."""
    data = dashboard_calidad_inventario_hallazgos(
        regla=regla,
        operador=operador,
        estado_base=estado_base,
        q=q,
        limit=200000,
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["regla", "access_id", "estado_base", "path_atc", "cto", "operador"])
    for item in data["findings"]:
        writer.writerow([
            item["regla"],
            item["access_id"],
            item["base_status"],
            item["path_atc"],
            item["cto"],
            item["operador"],
        ])
    return out.getvalue()
