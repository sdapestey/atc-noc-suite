"""Dashboard de calidad de inventario (KPIs + hallazgos + conciliación + histórico)."""
import csv
import io

from config import get_dashboard_calidad_cache_seconds
from db import db_cursor
from services.domain import (
    CALIDAD_OPERATORS,
    all_calidad_operator_member_ids as all_operator_member_ids,
    calidad_operator_member_ids as operator_member_ids,
    canonical_calidad_operator_id as canonical_operator_id,
)

from .dashboard_cache import get_cached_calidad_conciliacion, get_cached_calidad_resumen

RULES = {
    "missing_serial_match": {
        "label": "Sin match en SERIAL",
        "description": (
            "Desde Altiplano: no hay en INP una ONT-connection ni el intent en el VNO para este access_id; "
            "en ConnectMaster el FAT sí está presente. Equivale operativamente a no haber match en "
            "altiplano.serial en este cruce."
        ),
        "kpi_key": "aid_sin_match_serial",
    },
    "missing_olt_match": {
        "label": "Sin match en OLT",
        "description": (
            "Suele coincidir con ausencia de ONT-connection en INP y del intent del VNO en Altiplano, "
            "y en ConnectMaster con punto sin object name u ocupación OLT completa."
        ),
        "kpi_key": "aid_sin_match_olt",
    },
    "missing_path_atc": {
        "label": "Path ATC nulo/vacio",
        "description": (
            "En ConnectMaster (FAT) no viene informado el path ATC para ese access_id (nulo o solo espacios)."
        ),
        "kpi_key": "aid_path_atc_nulo_vacio",
    },
    "blank_serial_number": {
        "label": "Serial nulo/vacio",
        "description": (
            "Suele verse puerto y punto en ConnectMaster; en Altiplano puede haber ONT-connection en INP "
            "y el lado VNO vacío."
        ),
        "kpi_key": "aid_serial_nulo_vacio",
    },
    "casos_rotos_rack": {
        "label": "Casos rotos (rack 1_1__)",
        "description": (
            "En aux.bajada_inventario el rack_shelf_slot_port coincide con patrón 1_1__ "
            "(inconsistencia de datos en inventario)."
        ),
        "kpi_key": "aid_casos_rotos_rack",
    },
    "fat_sin_tag_nfc": {
        "label": "FAT sin TAG NFC",
        "description": (
            "En cm.inventory_fat_occupation, location IN SERVICE sin nfc_tag_id informado."
        ),
        "kpi_key": "aid_fat_sin_tag_nfc",
    },
    "fat_tag_nfc_duplicado": {
        "label": "FAT con TAG NFC duplicado",
        "description": (
            "TAG NFC repetido en más de 8 ubicaciones IN SERVICE (misma regla que tablero Superset)."
        ),
        "kpi_key": "aid_fat_tag_nfc_duplicado",
    },
}

# Alias histórico usado en tests y módulos del dashboard.
OPERATORS = CALIDAD_OPERATORS

_ALTIPLANO_SERIAL_ACTIVE = """
    s.serial_number IS NOT NULL
    AND btrim(s.serial_number) <> ''
    AND s.serial_number NOT LIKE 'ALCL0%%'
"""

ALLOWED_BASE_STATUSES = ("IN SERVICE", "RESERVED", "TO BE DELETED", "FREE")
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


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


def _norm_limit(value, default: int = DEFAULT_PAGE_SIZE, max_allowed: int = MAX_PAGE_SIZE) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(max_allowed, n))


def _norm_offset(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, n)


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
    ),
    nfc_dup_tags AS (
        SELECT nfc_tag_id
        FROM cm.inventory_fat_occupation
        WHERE nfc_tag_id IS NOT NULL
          AND location_status = 'IN SERVICE'
        GROUP BY nfc_tag_id
        HAVING COUNT(*) > 8
    )
    """


def _findings_union_sql() -> str:
    return (
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
            'missing_olt_match'::text,
            %s::text,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            '—'::text
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE o.access_id IS NULL

        UNION ALL

        SELECT
            'missing_path_atc'::text,
            %s::text,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—')
        FROM fat_active f
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE f.path_atc IS NULL

        UNION ALL

        SELECT
            'blank_serial_number'::text,
            %s::text,
            f.access_id,
            f.base_status,
            f.path_atc,
            f.cto,
            COALESCE(o.operador, '—')
        FROM fat_active f
        JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        WHERE COALESCE(s.has_serial_number, FALSE) = FALSE

        UNION ALL

        SELECT
            'casos_rotos_rack'::text,
            %s::text,
            btrim(bi.access_id),
            COALESCE(bi.observaciones, '—'),
            NULLIF(btrim(bi.rack_shelf_slot_port), ''),
            NULLIF(btrim(bi.nombre_red_olt), ''),
            COALESCE(btrim(bi.operatorid::text), '—')
        FROM aux.bajada_inventario bi
        WHERE btrim(COALESCE(bi.access_id, '')) <> ''
          AND bi.rack_shelf_slot_port LIKE '1_1__'

        UNION ALL

        SELECT
            'fat_sin_tag_nfc'::text,
            %s::text,
            btrim(f.location_description),
            'IN SERVICE',
            NULL,
            btrim(f.location_description),
            '—'
        FROM cm.inventory_fat_occupation f
        WHERE f.nfc_tag_id IS NULL
          AND f.location_status = 'IN SERVICE'
          AND btrim(COALESCE(f.location_description, '')) <> ''

        UNION ALL

        SELECT
            'fat_tag_nfc_duplicado'::text,
            %s::text,
            btrim(f.location_description),
            'IN SERVICE',
            btrim(f.nfc_tag_id::text),
            btrim(f.location_description),
            '—'
        FROM cm.inventory_fat_occupation f
        WHERE f.nfc_tag_id IS NOT NULL
          AND f.location_status = 'IN SERVICE'
          AND f.nfc_tag_id IN (SELECT nfc_tag_id FROM nfc_dup_tags)
    )
    """
    )


def _findings_filter_params(
    regla_norm: str,
    estado_base_norm: str,
    operador_norm: str,
    q_norm: str,
) -> tuple:
    return (
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
    )


def dashboard_calidad_inventario_resumen() -> dict:
    """KPIs agregados de calidad sobre inventario."""

    def _compute():
        sql = (
            _base_cte_sql()
            + """
        , fat_status_counts AS (
            SELECT
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'IN SERVICE')::int AS total_aid_in_service,
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'RESERVED')::int AS total_aid_reserved,
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'TO BE DELETED')::int AS total_aid_to_be_deleted,
                COUNT(DISTINCT btrim(f.access_id)) FILTER (WHERE f.status = 'FREE')::int AS total_aid_free
            FROM cm.inventory_fat_occupation f
            WHERE btrim(COALESCE(f.access_id, '')) <> ''
        ),
        nfc_sin AS (
            SELECT COUNT(DISTINCT btrim(location_description))::int AS n
            FROM cm.inventory_fat_occupation
            WHERE nfc_tag_id IS NULL
              AND location_status = 'IN SERVICE'
              AND btrim(COALESCE(location_description, '')) <> ''
        ),
        nfc_dup AS (
            SELECT COUNT(DISTINCT btrim(f.location_description))::int AS n
            FROM cm.inventory_fat_occupation f
            WHERE f.nfc_tag_id IS NOT NULL
              AND f.location_status = 'IN SERVICE'
              AND f.nfc_tag_id IN (SELECT nfc_tag_id FROM nfc_dup_tags)
        ),
        rotos AS (
            SELECT COUNT(DISTINCT btrim(access_id))::int AS n
            FROM aux.bajada_inventario bi
            WHERE btrim(COALESCE(bi.access_id, '')) <> ''
              AND bi.rack_shelf_slot_port LIKE '1_1__'
        )
        SELECT
            MAX(sc.total_aid_in_service)::int,
            MAX(sc.total_aid_reserved)::int,
            MAX(sc.total_aid_to_be_deleted)::int,
            MAX(sc.total_aid_free)::int,
            COUNT(*) FILTER (
                WHERE f.base_status = 'IN SERVICE' AND s.access_id IS NULL
            )::int,
            COUNT(*) FILTER (
                WHERE f.base_status = 'IN SERVICE' AND o.access_id IS NULL
            )::int,
            COUNT(*) FILTER (
                WHERE f.base_status = 'IN SERVICE' AND f.path_atc IS NULL
            )::int,
            COUNT(*) FILTER (
                WHERE f.base_status = 'IN SERVICE'
                  AND s.access_id IS NOT NULL
                  AND COALESCE(s.has_serial_number, FALSE) = FALSE
            )::int,
            MAX(r.n)::int,
            MAX(ns.n)::int,
            MAX(nd.n)::int
        FROM fat_active f
        LEFT JOIN serial_by_aid s ON s.access_id = f.access_id
        LEFT JOIN olt_by_aid o ON o.access_id = f.access_id
        CROSS JOIN fat_status_counts sc
        CROSS JOIN rotos r
        CROSS JOIN nfc_sin ns
        CROSS JOIN nfc_dup nd
        """
        )
        with db_cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

        (
            total_in_service,
            total_reserved,
            total_to_be_deleted,
            total_free,
            no_serial_match,
            no_olt_match,
            no_path,
            blank_serial,
            casos_rotos,
            fat_sin_nfc,
            fat_dup_nfc,
        ) = row
        rule_counts = {
            "missing_serial_match": int(no_serial_match or 0),
            "missing_olt_match": int(no_olt_match or 0),
            "missing_path_atc": int(no_path or 0),
            "blank_serial_number": int(blank_serial or 0),
            "casos_rotos_rack": int(casos_rotos or 0),
            "fat_sin_tag_nfc": int(fat_sin_nfc or 0),
            "fat_tag_nfc_duplicado": int(fat_dup_nfc or 0),
        }
        return {
            "total_aid_in_service": int(total_in_service or 0),
            "total_aid_reserved": int(total_reserved or 0),
            "total_aid_to_be_deleted": int(total_to_be_deleted or 0),
            "total_aid_free": int(total_free or 0),
            "aid_sin_match_serial": rule_counts["missing_serial_match"],
            "aid_sin_match_olt": rule_counts["missing_olt_match"],
            "aid_path_atc_nulo_vacio": rule_counts["missing_path_atc"],
            "aid_serial_nulo_vacio": rule_counts["blank_serial_number"],
            "aid_casos_rotos_rack": rule_counts["casos_rotos_rack"],
            "aid_fat_sin_tag_nfc": rule_counts["fat_sin_tag_nfc"],
            "aid_fat_tag_nfc_duplicado": rule_counts["fat_tag_nfc_duplicado"],
            "rule_counts": rule_counts,
            "rules": [
                {
                    "id": rid,
                    "label": meta["label"],
                    "kpi_key": meta.get("kpi_key"),
                    "count": rule_counts.get(rid, 0),
                    **({"description": meta["description"]} if meta.get("description") else {}),
                }
                for rid, meta in RULES.items()
            ],
        }

    return get_cached_calidad_resumen(get_dashboard_calidad_cache_seconds(), _compute)


def dashboard_calidad_inventario_hallazgos(
    regla: str | None = None,
    operador: str | None = None,
    estado_base: str | None = None,
    q: str | None = None,
    limit=DEFAULT_PAGE_SIZE,
    offset=0,
    max_limit: int | None = None,
) -> dict:
    """Detalle de hallazgos de calidad por regla (paginado)."""
    regla_norm = _norm_rule(regla)
    operador_norm = _norm_operator(operador)
    estado_base_norm = _norm_base_status(estado_base)
    q_norm = _norm_q(q)
    limit_norm = _norm_limit(
        limit,
        default=DEFAULT_PAGE_SIZE,
        max_allowed=max_limit if max_limit is not None else MAX_PAGE_SIZE,
    )
    offset_norm = _norm_offset(offset)

    label_params = (
        RULES["missing_serial_match"]["label"],
        RULES["missing_olt_match"]["label"],
        RULES["missing_path_atc"]["label"],
        RULES["blank_serial_number"]["label"],
        RULES["casos_rotos_rack"]["label"],
        RULES["fat_sin_tag_nfc"]["label"],
        RULES["fat_tag_nfc_duplicado"]["label"],
    )
    filter_params = _findings_filter_params(
        regla_norm, estado_base_norm, operador_norm, q_norm
    )

    count_sql = (
        _findings_union_sql()
        + """
    SELECT COUNT(*)::int
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
    """
    )

    data_sql = (
        _findings_union_sql()
        + """
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
    ORDER BY regla, access_id
    LIMIT %s OFFSET %s
    """
    )

    params_base = label_params + filter_params
    count_params = params_base
    data_params = params_base + (limit_norm, offset_norm)

    with db_cursor() as cur:
        cur.execute(count_sql, count_params)
        total_count = int(cur.fetchone()[0] or 0)
        cur.execute(data_sql, data_params)
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
                "kpi_key": meta.get("kpi_key"),
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
            "offset": offset_norm,
        },
        "total_count": total_count,
        "count": len(findings),
        "findings": findings,
    }


def dashboard_calidad_inventario_conciliacion() -> dict:
    """Conteos estilo Superset: totales, activos por operador CM y Altiplano."""
    return get_cached_calidad_conciliacion(
        get_dashboard_calidad_cache_seconds(),
        _dashboard_calidad_inventario_conciliacion_compute,
    )


def _dashboard_calidad_inventario_conciliacion_compute() -> dict:
    member_ids = all_operator_member_ids()
    placeholders = ", ".join(["%s"] * len(member_ids))

    sql = f"""
    WITH in_service AS (
        SELECT btrim(operatorid::text) AS operator_id, COUNT(*)::int AS n
        FROM aux.bajada_inventario
        WHERE observaciones = 'IN SERVICE'
          AND btrim(operatorid::text) IN ({placeholders})
        GROUP BY 1
    ),
    reserved AS (
        SELECT btrim(operatorid::text) AS operator_id, COUNT(*)::int AS n
        FROM aux.bajada_inventario
        WHERE observaciones = 'RESERVED'
          AND btrim(operatorid::text) IN ({placeholders})
        GROUP BY 1
    )
    SELECT
        COALESCE(i.operator_id, r.operator_id) AS operator_id,
        COALESCE(i.n, 0),
        COALESCE(r.n, 0)
    FROM in_service i
    FULL OUTER JOIN reserved r ON r.operator_id = i.operator_id
    ORDER BY 1
    """
    altiplano_by_vno_sql = f"""
    SELECT btrim(s.vno::text) AS vno, COUNT(*)::int AS n
    FROM altiplano.serial s
    WHERE {_ALTIPLANO_SERIAL_ACTIVE}
      AND btrim(s.vno::text) IN ({placeholders})
    GROUP BY 1
    """
    altiplano_total_sql = f"""
    SELECT COUNT(*)::int
    FROM altiplano.serial s
    WHERE {_ALTIPLANO_SERIAL_ACTIVE}
    """
    cm_total_sql = """
    SELECT COUNT(*)::int
    FROM aux.bajada_inventario bi
    WHERE bi.observaciones = 'IN SERVICE'
    """
    with db_cursor() as cur:
        cur.execute(sql, member_ids + member_ids)
        cm_rows = cur.fetchall()
        cur.execute(altiplano_by_vno_sql, member_ids)
        altiplano_by_vno = {r[0]: int(r[1] or 0) for r in cur.fetchall()}
        cur.execute(altiplano_total_sql)
        altiplano_total = int(cur.fetchone()[0] or 0)
        cur.execute(cm_total_sql)
        cm_in_service_total = int(cur.fetchone()[0] or 0)

    by_id = {r[0]: {"in_service": r[1], "reserved": r[2]} for r in cm_rows}
    operators = []
    for meta in OPERATORS:
        members = operator_member_ids(meta)
        cm_n = sum(int(by_id.get(mid, {}).get("in_service", 0) or 0) for mid in members)
        alt_n = sum(int(altiplano_by_vno.get(mid, 0) or 0) for mid in members)
        reserved_n = sum(int(by_id.get(mid, {}).get("reserved", 0) or 0) for mid in members)
        operators.append({
            "id": meta["id"],
            "label": meta["label"],
            "vno": meta["vno"],
            "connect_master": cm_n,
            "altiplano": alt_n,
            "in_service": cm_n,
            "reserved": reserved_n,
        })

    return {
        "operators": operators,
        "totals": {
            "connect_master_in_service": cm_in_service_total,
            "altiplano_activos": altiplano_total,
            "bajada_inventario_in_service": cm_in_service_total,
        },
    }


def dashboard_calidad_total_casos_rotos() -> int:
    """Total access_id con rack 1_1__ en bajada_inventario (Superset: Total ID con inconsistencia)."""
    sql = """
    SELECT COUNT(DISTINCT btrim(access_id))::int
    FROM aux.bajada_inventario bi
    WHERE btrim(COALESCE(bi.access_id, '')) <> ''
      AND bi.rack_shelf_slot_port LIKE '1_1__'
    """
    with db_cursor() as cur:
        cur.execute(sql)
        return int(cur.fetchone()[0] or 0)


def dashboard_calidad_comparativa_operadores(conciliacion_data: dict | None = None) -> list[dict]:
    """Tabla Resumen de Inconsistencia: Altiplano vs Connect Master por operador."""
    data = conciliacion_data if conciliacion_data is not None else dashboard_calidad_inventario_conciliacion()
    rows = []
    for op in data.get("operators", []):
        alt = int(op.get("altiplano") or 0)
        cm = int(op.get("connect_master") or op.get("in_service") or 0)
        rows.append({
            "vno": op["label"],
            "altiplano": alt,
            "connect_master": cm,
            "diferencia": alt - cm,
        })
    return rows


def _table_page(
    count_sql: str,
    data_sql: str,
    count_params: tuple,
    data_params: tuple,
    columns: list[str],
    row_mapper,
    limit: int,
    offset: int,
) -> dict:
    limit_n = _norm_limit(limit)
    offset_n = _norm_offset(offset)
    with db_cursor() as cur:
        cur.execute(count_sql, count_params)
        total = int(cur.fetchone()[0] or 0)
        cur.execute(data_sql, data_params + (limit_n, offset_n))
        rows = [row_mapper(r) for r in cur.fetchall()]
    return {
        "columns": columns,
        "total_count": total,
        "count": len(rows),
        "limit": limit_n,
        "offset": offset_n,
        "rows": rows,
    }


def dashboard_calidad_dtv_sin_serial(
    q: str | None = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> dict:
    q_norm = _norm_q(q)
    base = """
    FROM altiplano.serial s
    WHERE s.vno = '3001'
      AND (s.serial_number IS NULL OR btrim(s.serial_number) = '')
      AND (%s = '' OR s.access_id::text ILIKE ('%%' || %s || '%%')
           OR COALESCE(s.object_name, '') ILIKE ('%%' || %s || '%%'))
    """
    count_sql = "SELECT COUNT(*)::int " + base
    data_sql = (
        """
    SELECT
        btrim(s.access_id::text) AS access_id,
        COALESCE(s.object_name, '—') AS object_name,
        btrim(s.vno::text) AS vno,
        COALESCE(NULLIF(btrim(s.serial_number), ''), '—') AS serial_number
    """
        + base
        + " ORDER BY access_id LIMIT %s OFFSET %s"
    )
    params = (q_norm, q_norm, q_norm)
    return _table_page(
        count_sql,
        data_sql,
        params,
        params,
        ["access_id", "object_name", "vno", "serial_number"],
        lambda r: {
            "access_id": r[0],
            "object_name": r[1],
            "vno": r[2],
            "serial_number": r[3],
        },
        limit,
        offset,
    )


def dashboard_calidad_aids_inconsistencia_datos(
    q: str | None = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> dict:
    q_norm = _norm_q(q)
    base = """
    FROM aux.bajada_inventario bi
    WHERE bi.rack_shelf_slot_port LIKE '1_1__'
      AND (%s = '' OR btrim(bi.access_id::text) ILIKE ('%%' || %s || '%%')
           OR btrim(bi.operatorid::text) ILIKE ('%%' || %s || '%%'))
    """
    count_sql = "SELECT COUNT(*)::int " + base
    data_sql = (
        """
    SELECT
        btrim(bi.operatorid::text),
        btrim(bi.access_id::text),
        bi.reserved_date,
        bi.provided_date,
        COALESCE(NULLIF(btrim(bi.nombre_red_olt), ''), '—'),
        COALESCE(NULLIF(btrim(bi.marca_olt), ''), '—'),
        COALESCE(NULLIF(btrim(bi.modelo_olt), ''), '—'),
        COALESCE(NULLIF(btrim(bi.rack_shelf_slot_port), ''), '—'),
        COALESCE(bi.observaciones, '—')
    """
        + base
        + " ORDER BY access_id LIMIT %s OFFSET %s"
    )
    params = (q_norm, q_norm, q_norm)

    def _fmt_dt(v):
        if v is None:
            return "—"
        return v.isoformat(sep=" ", timespec="seconds") if hasattr(v, "isoformat") else str(v)

    return _table_page(
        count_sql,
        data_sql,
        params,
        params,
        [
            "operatorid",
            "access_id",
            "reserved_date",
            "provided_date",
            "nombre_red_olt",
            "marca_olt",
            "modelo_olt",
            "rack_shelf_slot_port",
            "observaciones",
        ],
        lambda r: {
            "operatorid": r[0],
            "access_id": r[1],
            "reserved_date": _fmt_dt(r[2]),
            "provided_date": _fmt_dt(r[3]),
            "nombre_red_olt": r[4],
            "marca_olt": r[5],
            "modelo_olt": r[6],
            "rack_shelf_slot_port": r[7],
            "observaciones": r[8],
        },
        limit,
        offset,
    )


def dashboard_calidad_fat_sin_nfc_tabla(
    q: str | None = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> dict:
    q_norm = _norm_q(q)
    base = """
    FROM cm.inventory_fat_occupation f
    WHERE f.nfc_tag_id IS NULL
      AND f.location_status = 'IN SERVICE'
      AND btrim(COALESCE(f.location_description, '')) <> ''
      AND (%s = '' OR btrim(f.location_description) ILIKE ('%%' || %s || '%%'))
    """
    count_sql = "SELECT COUNT(DISTINCT btrim(f.location_description))::int " + base
    data_sql = (
        """
    SELECT DISTINCT
        btrim(f.location_description),
        '—'::text AS nfc_tag_id
    """
        + base
        + " ORDER BY 1 LIMIT %s OFFSET %s"
    )
    params = (q_norm, q_norm)
    return _table_page(
        count_sql,
        data_sql,
        params,
        params,
        ["location_description", "nfc_tag_id"],
        lambda r: {"location_description": r[0], "nfc_tag_id": r[1]},
        limit,
        offset,
    )


def dashboard_calidad_fat_nfc_duplicados_tabla(
    q: str | None = None, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> dict:
    q_norm = _norm_q(q)
    base = """
    FROM cm.inventory_fat_occupation f
    WHERE f.nfc_tag_id IS NOT NULL
      AND f.location_status = 'IN SERVICE'
      AND f.nfc_tag_id IN (
        SELECT nfc_tag_id
        FROM cm.inventory_fat_occupation
        WHERE nfc_tag_id IS NOT NULL AND location_status = 'IN SERVICE'
        GROUP BY nfc_tag_id
        HAVING COUNT(*) > 8
      )
      AND (%s = '' OR btrim(f.location_description) ILIKE ('%%' || %s || '%%')
           OR btrim(f.nfc_tag_id::text) ILIKE ('%%' || %s || '%%'))
    """
    count_sql = (
        "SELECT COUNT(*)::int FROM (SELECT DISTINCT btrim(f.location_description), f.nfc_tag_id "
        + base
        + ") dup_rows"
    )
    data_sql = (
        """
    SELECT DISTINCT
        btrim(f.location_description),
        btrim(f.nfc_tag_id::text)
    """
        + base
        + " ORDER BY 2, 1 LIMIT %s OFFSET %s"
    )
    params = (q_norm, q_norm, q_norm)
    return _table_page(
        count_sql,
        data_sql,
        params,
        params,
        ["location_description", "nfc_tag_id"],
        lambda r: {"location_description": r[0], "nfc_tag_id": r[1]},
        limit,
        offset,
    )


def dashboard_calidad_inventario_resumen_general(days: int = 90) -> dict:
    """Payload agregado del tablero resumen (estilo Superset Conciliaciones ATC)."""
    conciliacion = dashboard_calidad_inventario_conciliacion()
    return {
        "conciliacion": conciliacion,
        "comparativa_operadores": dashboard_calidad_comparativa_operadores(conciliacion),
        "total_casos_rotos": dashboard_calidad_total_casos_rotos(),
        "historico": dashboard_calidad_inventario_historico(days=days),
        "operators": conciliacion.get("operators", []),
        "totals": conciliacion.get("totals", {}),
    }


def dashboard_calidad_inventario_historico(days: int = 90) -> dict:
    """Serie temporal de diferencias entre bases (aux.conciliaciones)."""
    try:
        days_norm = max(7, min(365, int(days)))
    except (TypeError, ValueError):
        days_norm = 90

    sql = """
    SELECT
        fecha::date AS dia,
        COALESCE(SUM(cantidad_cm_no_nokia), 0)::int AS cm_no_nokia,
        COALESCE(SUM(cantidad_nokia_no_cm), 0)::int AS nokia_no_cm
    FROM aux.conciliaciones
    WHERE fecha >= CURRENT_DATE - %s::int
    GROUP BY 1
    ORDER BY 1
    """
    with db_cursor() as cur:
        cur.execute(sql, (days_norm,))
        rows = cur.fetchall()

    points = [
        {
            "fecha": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "cm_no_nokia": int(row[1] or 0),
            "nokia_no_cm": int(row[2] or 0),
        }
        for row in rows
    ]
    return {"days": days_norm, "series": points}


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
        offset=0,
        max_limit=200000,
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
