QUERIES = {
    # ===============================
    # Información completa por Access ID
    # ===============================
    "access_id_topologia": """
        SELECT
            f.access_id,
            f.status,
            f.location_description AS cto,
            f.path_atc AS rama,

            -- Object name REAL para Altiplano (NO tocar)
            s.object_name AS object_name_raw,

            -- Object name limpio solo para UI
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,

            -- Serial real de ONT (fuente principal para SN en UI)
            s.serial_number AS serial_number,

            COALESCE(o.invocator_system, b_aid.operatorid) AS invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
               ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
               ON o.access_id = f.access_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                    THEN trim(b2.operatorid::text)::bigint
                    ELSE NULL
                END AS operatorid
            FROM aux.bajada_inventario b2
            WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(f.access_id::text))
              AND trim(b2.operatorid::text) ~ '^[0-9]+$'
              AND trim(b2.operatorid::text) <> '0'
            ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
            LIMIT 1
        ) b_aid ON true
        WHERE LOWER(btrim(f.access_id::text)) = LOWER(btrim(%s))
    """,

    "access_id_serial_y_olt": """
        SELECT
            s.object_name AS object_name_raw,
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,
            o.invocator_system
        FROM altiplano.serial s
        LEFT JOIN cm.inventory_olt_occupation o
               ON o.access_id::text = btrim(s.access_id::text)
        WHERE LOWER(btrim(s.access_id::text)) = LOWER(btrim(%s))
        LIMIT 1
    """,

    "access_id_bajada_object": """
        SELECT b.object_name, b.operatorid
        FROM aux.bajada_inventario b
        WHERE LOWER(btrim(b.access_id::text)) = LOWER(btrim(%s))
        ORDER BY b.reserved_date DESC NULLS LAST, b.provided_date DESC NULLS LAST
        LIMIT 1
    """,

    # ===============================
    # Access ID por alias/identificador no numérico (ej: Srvc_loc_*, RES_MT_*)
    # ===============================
    "access_id_desde_alias": """
        SELECT
            f.access_id,
            f.status,
            f.location_description AS cto,
            f.path_atc AS rama,
            s.object_name AS object_name_raw,
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,
            s.serial_number AS serial_number,
            o.invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
               ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
               ON o.access_id = f.access_id
        WHERE LOWER(btrim(SPLIT_PART(COALESCE(s.object_name, ''), ':', 1))) = LOWER(btrim(%s))
        ORDER BY f.access_id
        LIMIT 1
    """,

    # ===============================
    # Fallback de alias en aux.bajada_inventario.access_id
    # ===============================
    "access_id_desde_alias_bajada": """
        WITH b AS (
            SELECT
                btrim(access_id) AS alias_access_id,
                btrim(cto) AS aid_candidate,
                btrim(object_name) AS object_name_raw
            FROM aux.bajada_inventario
            WHERE LOWER(btrim(access_id)) = LOWER(btrim(%s))
            ORDER BY reserved_date DESC NULLS LAST, provided_date DESC NULLS LAST
            LIMIT 1
        )
        SELECT
            f.access_id,
            f.status,
            f.location_description AS cto,
            f.path_atc AS rama,
            s.object_name AS object_name_raw,
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,
            s.serial_number AS serial_number,
            o.invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
               ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
               ON o.access_id = f.access_id
        JOIN b ON (
            (b.aid_candidate ~ '^[0-9]+$' AND f.access_id::text = b.aid_candidate)
            OR
            (
                LOWER(btrim(SPLIT_PART(COALESCE(s.object_name, ''), ':', 1))) =
                LOWER(btrim(SPLIT_PART(COALESCE(b.object_name_raw, ''), ':', 1)))
            )
        )
        ORDER BY
            CASE
                WHEN (b.aid_candidate ~ '^[0-9]+$' AND f.access_id::text = b.aid_candidate)
                THEN 0
                ELSE 1
            END,
            f.access_id
        LIMIT 1
    """,

    # ===============================
    # ONT por CTO (todas las ONT de una CTO)
    # ===============================
    "onts_por_cto": """
        SELECT
            f.access_id,
            f.status,
            f.location_description AS cto,
            f.path_atc AS rama,

            -- Object name REAL para Altiplano
            s.object_name AS object_name_raw,

            -- Object name limpio para UI
            REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui,

            -- Serial real de ONT (fuente principal para SN en UI)
            s.serial_number AS serial_number,

            COALESCE(o.invocator_system, b_aid.operatorid) AS invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
             ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
             ON o.access_id = f.access_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                    THEN trim(b2.operatorid::text)::bigint
                    ELSE NULL
                END AS operatorid
                FROM aux.bajada_inventario b2
                WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(f.access_id::text))
                ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
                LIMIT 1
        ) b_aid ON true
        WHERE f.location_description = %s
          AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
        -- Orden tipo ConnectMaster (OUT1…OUT8): posición física del splitter en CM viene en
        -- inventory_fat_occupation.port_number y/o port_name (OUTn). Si en CM tenés fo_out_split_2,
        -- suele reflejarse en estos campos del FAT; sin match de posición va al final.
        ORDER BY
            COALESCE(
                f.port_number,
                NULLIF(regexp_replace(COALESCE(f.port_name, ''), '[^0-9]', '', 'g'), '')::bigint
            ) NULLS LAST,
            f.access_id
    """,

    # ===============================
    # Todas las ONT de una rama (mismas columnas que onts_por_cto)
    # ===============================
    "onts_por_rama": """
        SELECT
            f.access_id,
            f.status,
            f.location_description AS cto,
            f.path_atc AS rama,
            s.object_name AS object_name_raw,
            REPLACE(COALESCE(s.object_name, ''), ':1-1', '') AS object_name_ui,
            s.serial_number AS serial_number,
            COALESCE(o.invocator_system, b_aid.operatorid) AS invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
             ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
             ON o.access_id = f.access_id
        LEFT JOIN LATERAL (
            SELECT
                CASE
                    WHEN trim(b2.operatorid::text) ~ '^[0-9]+$'
                    THEN trim(b2.operatorid::text)::bigint
                    ELSE NULL
                END AS operatorid
                FROM aux.bajada_inventario b2
                WHERE LOWER(btrim(b2.access_id::text)) = LOWER(btrim(f.access_id::text))
                ORDER BY b2.reserved_date DESC NULLS LAST, b2.provided_date DESC NULLS LAST
                LIMIT 1
        ) b_aid ON true
        WHERE f.path_atc = %s
          AND f.status IN ('IN SERVICE', 'RESERVED', 'FREE')
        ORDER BY
            f.location_description,
            COALESCE(
                f.port_number,
                NULLIF(regexp_replace(COALESCE(f.port_name, ''), '[^0-9]', '', 'g'), '')::bigint
            ) NULLS LAST,
            f.access_id
    """,
    # ===============================
    # Histórico de potencias por rama (RATC)
    # ===============================
    "historico_resolver_pon_desde_rama": """
        WITH r AS (
            SELECT physical_path
            FROM cm.inventory_fat_occupation
            WHERE path_atc = %s
            ORDER BY access_id
            LIMIT 1
        )
        SELECT btrim(b.object_name)
        FROM aux.bajada_inventario b
        JOIN r ON b.fibra_f01_f02_f03 = r.physical_path
        WHERE b.object_name IS NOT NULL
          AND btrim(b.object_name) <> ''
        ORDER BY b.reserved_date DESC NULLS LAST, b.provided_date DESC NULLS LAST
        LIMIT 1
    """,
    "historico_potencias_por_pon": """
        SELECT
            "ont-pwr_rx_updated_on" AS ts,
            objectname,
            ("ont-pwr_rx" / 10.0)::float8 AS rx
        FROM altiplano.potencias
        WHERE objectname LIKE %s
          AND "ont-pwr_rx_updated_on" >= NOW() - make_interval(days => %s)
        ORDER BY "ont-pwr_rx_updated_on" ASC
    """,
}