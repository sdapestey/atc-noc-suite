"""Dashboard de calidad de inventario (KPIs + hallazgos)."""
import csv
import io

from config import get_dashboard_calidad_cache_seconds
from db import db_cursor

from .dashboard_cache import get_cached_calidad_resumen

RULES = {
    "missing_serial_match": {"label": "Sin match en SERIAL", "severity": "alta"},
    "missing_olt_match": {"label": "Sin match en OLT", "severity": "alta"},
    "missing_path_atc": {"label": "Path ATC nulo/vacio", "severity": "media"},
    "missing_cto": {"label": "CTO nulo/vacio", "severity": "media"},
    "blank_serial_number": {"label": "Serial nulo/vacio", "severity": "media"},
    "null_invocator_system": {"label": "invocator_system nulo en OLT", "severity": "media"},
}


def _norm_rule(value: str | None) -> str:
    v = (value or "").strip()
    return v if v in RULES else ""


def _norm_operator(value: str | None) -> str:
    return (value or "").strip()


def _norm_q(value: str | None) -> str:
    return (value or "").strip()


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
            MAX(NULLIF(btrim(f.path_atc), '')) AS path_atc,
            MAX(NULLIF(btrim(f.location_description), '')) AS cto
        FROM cm.inventory_fat_occupation f
        WHERE f.status = 'IN SERVICE'
          AND btrim(COALESCE(f.access_id, '')) <> ''
        GROUP BY btrim(f.access_id)
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
        SELECT
            COUNT(*)::int AS total_aid_in_service,
            COUNT(*) FILTER (WHERE s.access_id IS NULL)::int AS aid_sin_match_serial,
            COUNT(*) FILTER (WHERE o.access_id IS NULL)::int AS aid_sin_match_olt,
            COUNT(*) FILTER (WHERE f.path_atc IS NULL)::int AS aid_path_atc_nulo_vacio,
            COUNT(*) FILTER (WHERE f.cto IS NULL)::int AS aid_cto_nulo_vacio,
            COUNT(*) FILTER (
                WHERE s.access_id IS NOT NULL
                  AND COALESCE(s.has_serial_number, FALSE) = FALSE
            )::int AS aid_serial_nulo_vacio,
            COUNT(*) FILTER (
                WHERE o.access_id IS NOT NULL
                  AND COALESCE(o.has_invocator_system, FALSE) = FALSE
            )::int AS aid_invocator_system_nulo_en_olt
        FROM fat_active f
        LEFT JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
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
            no_cto,
            blank_serial,
            null_invocator,
        ) = row
        return {
            "total_aid_in_service": int(total or 0),
            "aid_sin_match_serial": int(no_serial_match or 0),
            "aid_sin_match_olt": int(no_olt_match or 0),
            "aid_path_atc_nulo_vacio": int(no_path or 0),
            "aid_cto_nulo_vacio": int(no_cto or 0),
            "aid_serial_nulo_vacio": int(blank_serial or 0),
            "aid_invocator_system_nulo_en_olt": int(null_invocator or 0),
        }

    return get_cached_calidad_resumen(get_dashboard_calidad_cache_seconds(), _compute)


def dashboard_calidad_inventario_hallazgos(
    regla: str | None = None,
    operador: str | None = None,
    q: str | None = None,
    limit=500,
) -> dict:
    """Detalle de hallazgos de calidad por regla."""
    regla_norm = _norm_rule(regla)
    operador_norm = _norm_operator(operador)
    q_norm = _norm_q(q)
    limit_norm = _norm_limit(limit)

    sql = (
        _base_cte_sql()
        + """
    , findings AS (
        SELECT
            'missing_serial_match'::text AS regla_id,
            %s::text AS regla,
            %s::text AS severidad,
            f.access_id,
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
            %s::text AS severidad,
            f.access_id,
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
            %s::text AS severidad,
            f.access_id,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE f.path_atc IS NULL

        UNION ALL

        SELECT
            'missing_cto'::text AS regla_id,
            %s::text AS regla,
            %s::text AS severidad,
            f.access_id,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE f.cto IS NULL

        UNION ALL

        SELECT
            'blank_serial_number'::text AS regla_id,
            %s::text AS regla,
            %s::text AS severidad,
            f.access_id,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—') AS operador
        FROM fat_active f
        JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE COALESCE(s.has_serial_number, FALSE) = FALSE

        UNION ALL

        SELECT
            'null_invocator_system'::text AS regla_id,
            %s::text AS regla,
            %s::text AS severidad,
            f.access_id,
            f.path_atc,
            f.cto,
            '—'::text AS operador
        FROM fat_active f
        JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE COALESCE(o.has_invocator_system, FALSE) = FALSE
    )
    SELECT
        regla_id,
        regla,
        access_id,
        COALESCE(path_atc, '—') AS path_atc,
        COALESCE(cto, '—') AS cto,
        operador,
        severidad
    FROM findings
    WHERE (%s = '' OR regla_id = %s)
      AND (%s = '' OR operador = %s)
      AND (
          %s = ''
          OR access_id ILIKE ('%%' || %s || '%%')
          OR COALESCE(path_atc, '') ILIKE ('%%' || %s || '%%')
          OR COALESCE(cto, '') ILIKE ('%%' || %s || '%%')
      )
    ORDER BY
        CASE severidad WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
        regla,
        access_id
    LIMIT %s
    """
    )

    params = (
        RULES["missing_serial_match"]["label"],
        RULES["missing_serial_match"]["severity"],
        RULES["missing_olt_match"]["label"],
        RULES["missing_olt_match"]["severity"],
        RULES["missing_path_atc"]["label"],
        RULES["missing_path_atc"]["severity"],
        RULES["missing_cto"]["label"],
        RULES["missing_cto"]["severity"],
        RULES["blank_serial_number"]["label"],
        RULES["blank_serial_number"]["severity"],
        RULES["null_invocator_system"]["label"],
        RULES["null_invocator_system"]["severity"],
        regla_norm,
        regla_norm,
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
        regla_id, regla_label, access_id, path_atc, cto, operador_val, severidad = row
        findings.append({
            "regla_id": regla_id,
            "regla": regla_label,
            "access_id": access_id,
            "path_atc": path_atc,
            "cto": cto,
            "operador": operador_val,
            "severidad": severidad,
        })

    return {
        "rules": [{"id": rid, "label": meta["label"]} for rid, meta in RULES.items()],
        "filters": {
            "regla": regla_norm,
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
    q: str | None = None,
) -> str:
    """Exporta CSV de hallazgos para los filtros aplicados."""
    data = dashboard_calidad_inventario_hallazgos(
        regla=regla,
        operador=operador,
        q=q,
        limit=200000,
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["regla", "access_id", "path_atc", "cto", "operador", "severidad"])
    for item in data["findings"]:
        writer.writerow([
            item["regla"],
            item["access_id"],
            item["path_atc"],
            item["cto"],
            item["operador"],
            item["severidad"],
        ])
    return out.getvalue()
