import csv
import psycopg2

SQL = """
WITH ramas AS (
  SELECT DISTINCT btrim(path_atc) AS ratc
  FROM cm.inventory_fat_occupation
  WHERE path_atc IS NOT NULL
    AND btrim(path_atc) <> ''
),
pon_por_rama AS (
  SELECT
    r.ratc,
    (regexp_match(btrim(b.object_name), '^(.*?):1-1-(\\d+)-(\\d+)-'))[1]
      || '-' ||
    (regexp_match(btrim(b.object_name), '^(.*?):1-1-(\\d+)-(\\d+)-'))[2]
      || '-' ||
    (regexp_match(btrim(b.object_name), '^(.*?):1-1-(\\d+)-(\\d+)-'))[3]
      AS pon
  FROM ramas r
  JOIN LATERAL (
    SELECT physical_path
    FROM cm.inventory_fat_occupation
    WHERE path_atc = r.ratc
    ORDER BY access_id
    LIMIT 1
  ) occ ON TRUE
  LEFT JOIN LATERAL (
    SELECT btrim(object_name) AS object_name
    FROM aux.bajada_inventario b
    WHERE b.fibra_f01_f02_f03 = occ.physical_path
      AND b.object_name IS NOT NULL
      AND btrim(b.object_name) <> ''
    ORDER BY b.reserved_date DESC NULLS LAST, b.provided_date DESC NULLS LAST
    LIMIT 1
  ) b ON TRUE
),
muestras_24h AS (
  SELECT DISTINCT p.ratc
  FROM pon_por_rama p
  JOIN altiplano.potencias a
    ON p.pon IS NOT NULL
   AND a.objectname LIKE ('%' || p.pon || '-%')
   AND a."ont-pwr_rx_updated_on" >= NOW() - INTERVAL '1 day'
),
muestras_7d AS (
  SELECT DISTINCT p.ratc
  FROM pon_por_rama p
  JOIN altiplano.potencias a
    ON p.pon IS NOT NULL
   AND a.objectname LIKE ('%' || p.pon || '-%')
   AND a."ont-pwr_rx_updated_on" >= NOW() - INTERVAL '7 days'
)
SELECT
  p.ratc,
  p.pon,
  CASE WHEN p.pon IS NULL THEN 'NO_RESUELVE_PON' ELSE 'OK' END AS pon_status,
  CASE WHEN m24.ratc IS NULL THEN 0 ELSE 1 END AS tiene_24h,
  CASE WHEN m7.ratc  IS NULL THEN 0 ELSE 1 END AS tiene_7d
FROM pon_por_rama p
LEFT JOIN muestras_24h m24 ON m24.ratc = p.ratc
LEFT JOIN muestras_7d  m7  ON m7.ratc  = p.ratc
ORDER BY p.ratc;
"""

def main():
    conn = psycopg2.connect(
        host="10.90.1.198",
        port=5432,
        dbname="postgres",
        user="om_read",
        password="Fiber2021#",
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SQL)
            rows = cur.fetchall()

        # Ajustá el nombre del archivo si querés
        out_name = "ramas_potencias_historico_24h_7d.csv"
        with open(out_name, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ratc", "pon", "pon_status", "tiene_24h", "tiene_7d"])
            for ratc, pon, pon_status, tiene_24h, tiene_7d in rows:
                w.writerow([
                    ratc,
                    pon or "",
                    pon_status,
                    int(tiene_24h),
                    int(tiene_7d),
                ])
        print(f"Generado {out_name} con {len(rows)} filas.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
