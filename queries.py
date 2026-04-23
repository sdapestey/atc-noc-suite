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

            o.invocator_system
        FROM cm.inventory_fat_occupation f
        LEFT JOIN altiplano.serial s
               ON s.access_id = f.access_id
        LEFT JOIN cm.inventory_olt_occupation o
               ON o.access_id = f.access_id
        WHERE f.access_id = %s
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
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,

            o.invocator_system
        FROM cm.inventory_fat_occupation f
        JOIN altiplano.serial s
             ON s.access_id = f.access_id
        JOIN cm.inventory_olt_occupation o
             ON o.access_id = f.access_id
        WHERE f.location_description = %s
        ORDER BY f.access_id
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
            REPLACE(s.object_name, ':1-1', '') AS object_name_ui,
            o.invocator_system
        FROM cm.inventory_fat_occupation f
        JOIN altiplano.serial s
             ON s.access_id = f.access_id
        JOIN cm.inventory_olt_occupation o
             ON o.access_id = f.access_id
        WHERE f.path_atc = %s AND f.status = 'IN SERVICE'
        ORDER BY f.location_description, f.access_id
    """,
}