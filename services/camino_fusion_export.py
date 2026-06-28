"""Exportación reporte de fusión planta interna (equivalente PDF Bentley / report_fusiones)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

from db import db_cursor

from .camino_gis import (
    _env_fusiones_table,
    _env_schema,
    _fosc_id_desde_component_fullname,
    _list_data_columns,
    _quote_ident,
    _table_exists,
    _validate_ident,
    cabecera_desde_rama,
    es_codigo_fusion_planta,
    es_id_fosc_cm,
)

_FIBRA_NUM_RE = re.compile(r"(\d+)", re.I)
_OUT_PORT_RE = re.compile(r"^OUT(\d+)$", re.I)
_FUSION_ID_RE = re.compile(r"^SF\d+-R(\d+)-\d+$", re.I)

_COLORES_12 = (
    "AZUL",
    "NARANJA",
    "VERDE",
    "MARRÓN",
    "GRIS",
    "BLANCO",
    "ROJO",
    "NEGRO",
    "AMARILLO",
    "VIOLETA",
    "ROSA",
    "CELESTE",
)

_HEADEND_LOCALIDAD: dict[str, str] = {
    "SF01": "SAN FERNANDO",
}


def _cell(val: object) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return s


def color_indice_12(n: int) -> str:
    """Color estándar de tubo/fibra (1–12) como en reportes Bentley."""
    if n < 1:
        return ""
    return _COLORES_12[(n - 1) % 12]


def color_desde_numero_fibra(fibra: str) -> str:
    m = _FIBRA_NUM_RE.search((fibra or "").strip())
    if not m:
        return ""
    return color_indice_12(int(m.group(1)))


def color_desde_puerto_out(port: str) -> str:
    m = _OUT_PORT_RE.match((port or "").strip().upper())
    if not m:
        return ""
    return color_indice_12(int(m.group(1)))


def _grupo_desde_subcategoria(subcat: str) -> str:
    s = (subcat or "").strip()
    if not s:
        return ""
    m = re.search(r"L(\d+)", s, re.I)
    if m:
        return m.group(1)
    m = re.search(r"D(\d+)", s, re.I)
    if m:
        return m.group(1)
    return ""


def grupo_desde_fibra(fibra: str) -> str:
    """Tubo/buffer (1–12 pelos) según número de fibra, como en PDF Bentley."""
    m = _FIBRA_NUM_RE.search((fibra or "").strip())
    if not m:
        return ""
    n = int(m.group(1))
    if n < 1:
        return ""
    return str((n - 1) // 12 + 1)


def grupo_para_fila(subcat: str, fibra: str) -> str:
    """Grupo mostrado: tubo por número de fibra; si no hay, subcategoría L/D."""
    return grupo_desde_fibra(fibra) or _grupo_desde_subcategoria(subcat)


def color_grupo_buffer(subcat: str, grupo: str) -> str:
    """Color de buffer/grupo: D* → BLANCO (Bentley); L* → paleta por número."""
    sc = (subcat or "").upper()
    if "DISTRIBUTION" in sc or re.search(r"\bD\d", sc):
        return "BLANCO"
    try:
        gi = int(grupo) if grupo else 0
    except (TypeError, ValueError):
        gi = 0
    if "BACKHAUL" in sc:
        return color_indice_12(gi or 1)
    if gi < 1:
        return ""
    return color_indice_12(gi)


def fibra_display(val: str) -> str:
    p = (val or "").strip()
    if not p:
        return ""
    if p.upper().startswith("OUT") or p.upper() == "IN":
        return p.upper()
    m = _FIBRA_NUM_RE.search(p.replace("Fibra", "", 1))
    if m:
        n = int(m.group(1))
        return f"{n:02d}" if n < 100 else str(n)
    return p


def color_slug(name: str) -> str:
    s = (
        (name or "")
        .lower()
        .replace("ó", "o")
        .replace("á", "a")
        .replace("ñ", "n")
    )
    return re.sub(r"[^a-z0-9-]", "", s)


def _suffix_rama(path_atc: str) -> int | None:
    m = re.search(r"-0-0*(\d+)$", (path_atc or "").strip(), re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _fusion_block_num(fusion_id: str) -> int | None:
    m = re.search(r"-R(\d+)-", (fusion_id or "").strip(), re.I)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _precargar_fusion_destino_map(
    cur,
    schema: str,
    table: str,
    physical_paths: set[str] | list[str],
) -> dict[tuple[str, str], str]:
    """Mapa (path físico, cable) → primera fusión R####-010 (una sola consulta)."""
    paths = sorted({(p or "").strip() for p in physical_paths if (p or "").strip()})
    if not paths:
        return {}
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    cur.execute(
        f"""
        SELECT physical_path, description_a, description_b, location_description
        FROM {schema_q}.{table_q}
        WHERE physical_path = ANY(%s)
          AND location_description ~ '^[A-Za-z0-9]{{2,12}}-R[0-9]+-[0-9]{{3}}$'
        ORDER BY location_description
        """,
        (paths,),
    )
    cache: dict[tuple[str, str], str] = {}
    for path, da, db, ld in cur.fetchall():
        path_s = (path or "").strip()
        ld_s = (ld or "").strip().upper()
        if not path_s or not ld_s:
            continue
        for cable in (da, db):
            c = (cable or "").strip()
            if not c:
                continue
            key = (path_s, c)
            if key not in cache:
                cache[key] = ld_s
    return cache


def _fusion_destino_desde_cache(
    cache: dict[tuple[str, str], str],
    physical_path: str,
    *cables: str,
) -> str:
    path = (physical_path or "").strip()
    if not path:
        return ""
    for cable in cables:
        c = (cable or "").strip()
        if not c:
            continue
        dest = cache.get((path, c))
        if dest:
            return dest
    return ""


def _fusion_destino_cable_path(
    cur,
    schema: str,
    table: str,
    physical_path: str,
    *cables: str,
    cache: dict[tuple[str, str], str] | None = None,
) -> str:
    """Primera fusión R####-010 en el path físico para alguno de los cables (destino CM)."""
    physical_path = (physical_path or "").strip()
    if not physical_path:
        return ""
    for cable in cables:
        cable = (cable or "").strip()
        if not cable:
            continue
        key = (physical_path, cable)
        if cache is not None and key in cache:
            dest = cache[key]
            if dest:
                return dest
            continue
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT DISTINCT location_description
            FROM {schema_q}.{table_q}
            WHERE physical_path = %s
              AND (description_a = %s OR description_b = %s)
              AND location_description ~ '^[A-Za-z0-9]{{2,12}}-R[0-9]+-[0-9]{{3}}$'
            ORDER BY location_description
            LIMIT 1
            """,
            (physical_path, cable, cable),
        )
        row = cur.fetchone()
        dest = (row[0] or "").strip().upper() if row else ""
        if cache is not None:
            cache[key] = dest
        if dest:
            return dest
    return ""


def _fatc_suffix_num(alias: str) -> int:
    m = re.search(r"-FATC-\d+-(\d+)$", (alias or "").strip(), re.I)
    if not m:
        return -1
    try:
        return int(m.group(1))
    except ValueError:
        return -1


def _precargar_destino_fatc_continuidad(
    cur,
    schema: str,
    table: str,
    *,
    usedby: str,
    alias_actual: str,
    cables: set[str] | list[str],
) -> dict[str, str]:
    """FATC destino CM en CONTINUIDAD (mismo cable + usedby, mayor sufijo del grupo)."""
    usedby = (usedby or "").strip()
    alias_actual = (alias_actual or "").strip().upper()
    if not usedby:
        return {}
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    out: dict[str, str] = {}
    for cable in sorted({(c or "").strip() for c in cables if (c or "").strip()}):
        cur.execute(
            f"""
            SELECT DISTINCT location_description
            FROM {schema_q}.{table_q}
            WHERE usedby = %s
              AND (description_a = %s OR description_b = %s)
              AND location_description ~ '^SF[0-9]+-FATC-[0-9]+-[0-9]+$'
              AND UPPER(TRIM(location_description)) <> %s
            """,
            (usedby, cable, cable, alias_actual),
        )
        best = ""
        best_n = -1
        for (ld,) in cur.fetchall():
            ld_s = (ld or "").strip().upper()
            n = _fatc_suffix_num(ld_s)
            if n > best_n:
                best_n = n
                best = ld_s
        if best:
            out[cable] = best
    return out


def _rama_continuidad_reporte(
    circuit: str,
    path_atc: str,
    cable_out: str,
    cable_in: str,
) -> str:
    r = rama_cable_reporte(circuit, path_atc)
    if r:
        return r
    return ""


def _destino_cable_fosc_export(
    splice: str,
    circuit: str,
    path_atc: str,
    physical_path: str,
    cable_in: str,
    cable_out: str,
    *,
    alias_fosc: str,
    dest_fusion_cache: dict[tuple[str, str], str],
    dest_fatc_cache: dict[str, str],
) -> str:
    if (splice or "").strip().upper() == "CONTINUIDAD":
        for cable in (cable_out, cable_in):
            c = (cable or "").strip()
            if c and dest_fatc_cache.get(c):
                return dest_fatc_cache[c]
        return alias_fosc
    destino = _fusion_destino_desde_cache(
        dest_fusion_cache, physical_path, cable_out, cable_in
    )
    if destino:
        return destino
    return destino_cable_reporte(circuit, path_atc, alias_fosc=alias_fosc)


def _siguiente_fusion_en_path(
    cur,
    schema: str,
    table: str,
    physical_path: str,
    cable: str,
    fusion_actual: str,
) -> str:
    """Siguiente fusión en el mismo path físico y cable (destino CM en splice plan)."""
    physical_path = (physical_path or "").strip()
    cable = (cable or "").strip()
    fusion_actual = (fusion_actual or "").strip().upper()
    if not physical_path or not cable or not fusion_actual:
        return ""
    cur_block = _fusion_block_num(fusion_actual)
    if cur_block is None:
        return ""
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    cur.execute(
        f"""
        SELECT DISTINCT location_description
        FROM {schema_q}.{table_q}
        WHERE physical_path = %s
          AND (description_a = %s OR description_b = %s)
          AND location_description ~ '^[A-Za-z0-9]{{2,12}}-R[0-9]+-[0-9]{{3}}$'
        ORDER BY location_description
        """,
        (physical_path, cable, cable),
    )
    for (ld,) in cur.fetchall():
        ld_s = (ld or "").strip().upper()
        block = _fusion_block_num(ld_s)
        if block is not None and block > cur_block:
            return ld_s
    return ""


def rama_cable_reporte(circuit: str, path_atc: str) -> str:
    """Rama columna cable: prioriza ``circuit`` (CM) y normaliza RAMX → R0772-000."""
    c = (circuit or "").strip()
    p = (path_atc or "").strip()
    for val in (c, p):
        if val and re.match(r"SF\d+-RATC-", val, re.I):
            return val
    if c and re.match(r"SF\d+-R\d+-000$", c, re.I):
        return c.upper()
    m = re.search(r"-0-0*(\d+)$", p, re.I)
    site_m = re.match(r"(SF\d+)", p, re.I)
    if m and site_m and re.match(r"SF\d+-RAMX-", p, re.I):
        try:
            n = int(m.group(1))
            return f"{site_m.group(1).upper()}-R{n:04d}-000"
        except ValueError:
            pass
    return c or p


def _destino_cable_fusion_export(
    cur,
    schema: str,
    table: str,
    fusion_id: str,
    circuit: str,
    path_atc: str,
    physical_path: str,
    cable: str,
    *,
    alias_fosc: str = "",
) -> str:
    nxt = _siguiente_fusion_en_path(cur, schema, table, physical_path, cable, fusion_id)
    if nxt:
        return nxt
    return destino_cable_reporte(circuit, path_atc, alias_fosc=alias_fosc)


def destino_cable_reporte(
    circuit: str,
    path_atc: str,
    *,
    alias_fosc: str = "",
) -> str:
    """Destino columna OUT como en PDF Bentley (SF01-R1300/1303-010, FATC, EDN)."""
    c = (circuit or "").strip()
    path = (path_atc or "").strip()
    if "EDN_CT" in c or "EDN_CT" in path:
        if alias_fosc and "FATC" in alias_fosc:
            return re.sub(r"(\d{4})$", "3977", alias_fosc) if alias_fosc.endswith("3503") else "SF01-FATC-3-003977"
        return "SF01-FATC-3-003977"
    if c and re.match(r"SF\d+-FATC-", c, re.I):
        return c
    if c and re.match(r"SF\d+-R\d+-010$", c, re.I):
        return c
    site_m = re.match(r"(SF\d+)", path or c, re.I)
    site = site_m.group(1).upper() if site_m else "SF01"
    n = _suffix_rama(path or c)
    if n is None:
        return c or path
    if n in (1300, 1302):
        return f"{site}-R1300-010"
    if n >= 1291 or n >= 1303:
        return f"{site}-R1303-010"
    return c or path


def _fibra_sort_key(row: dict[str, Any]) -> tuple[int, int, str, str]:
    m = _FIBRA_NUM_RE.search(str(row.get("fibra_in") or ""))
    n = int(m.group(1)) if m else 9999
    rama = str(row.get("rama_salida") or "")
    edn_first = 0 if "EDN" in rama.upper() else 1
    return (n, edn_first, str(row.get("cable_in") or ""), rama)


def _agrupar_splitter_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa filas por path + circuito (bloques OUT como en Bentley)."""
    groups: list[dict[str, Any]] = []
    current_key: tuple[str, str] | None = None
    current: dict[str, Any] | None = None
    for row in rows:
        key = (str(row.get("path_in") or ""), str(row.get("circuit_in") or ""))
        if key != current_key:
            current = {"path_in": key[0], "circuit_in": key[1], "rows": []}
            groups.append(current)
            current_key = key
        assert current is not None
        sub = dict(row)
        sub["group_head"] = len(current["rows"]) == 0
        current["rows"].append(sub)
    return groups


def _attach_color_slugs(row: dict[str, Any]) -> dict[str, Any]:
    for key in list(row.keys()):
        if key.startswith("color_") and not key.endswith("_slug"):
            row[f"{key}_slug"] = color_slug(str(row.get(key) or ""))
    return row


def fusion_codigo_corto(fusion_id: str) -> str:
    """Número corto FUSIÓN del PDF ConnectMaster (ej. R1301→13, R0773→14)."""
    m = _FUSION_ID_RE.match((fusion_id or "").strip().upper())
    if not m:
        return ""
    n = int(m.group(1))
    if n >= 1000:
        return str(n // 100)
    return str(n // 55)


def _owner_etiqueta(rec: dict[str, Any]) -> str:
    owner = _cell(rec.get("owner")).upper() or "ATC"
    for key in ("component_name_a", "component_name_b", "description_a"):
        cn = _cell(rec.get(key)).upper()
        if "010201" in cn or "-CAMX-" in cn:
            return "AMX"
        if "010101" in cn or "-CATC-" in cn:
            return "ATC"
    return owner if owner in ("ATC", "AMX") else "ATC"


def _splitter_etiqueta(rec: dict[str, Any]) -> str:
    tb = _cell(rec.get("component_type_name_b"))
    ta = _cell(rec.get("component_type_name_a"))
    sp = tb if "SPLITTER" in tb.upper() else ta
    if not sp:
        return ""
    return f"{sp} [ {_owner_etiqueta(rec)} ]"


def _fibra_y_color(point: str, subcat: str = "") -> tuple[str, str]:
    p = (point or "").strip()
    if not p:
        return "", ""
    pu = p.upper()
    if _OUT_PORT_RE.match(pu):
        return pu, color_desde_puerto_out(pu)
    if pu == "IN":
        return "IN", ""
    fibra = fibra_display(p)
    return fibra, color_desde_numero_fibra(fibra or p)


def _es_fila_splitter(rec: dict[str, Any]) -> bool:
    ta = (rec.get("component_type_name_a") or "").upper()
    tb = (rec.get("component_type_name_b") or "").upper()
    pa = (rec.get("point_name_a") or "").upper()
    return (
        "SPLITTER" in ta
        or "SPLITTER" in tb
        or pa in ("IN", "OUT1", "OUT2", "OUT3", "OUT4", "OUT5", "OUT6", "OUT7", "OUT8")
        or pa.startswith("OUT")
    )


def _cargar_fosc(cur, schema: str, fosc_id: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not fosc_id or not _table_exists(cur, schema, "ci_fosc"):
        return out
    cols = set(_list_data_columns(cur, schema, "ci_fosc"))
    want = [c for c in ("direccion", "nombre_atc", "partido_despliegue", "cabecera") if c in cols]
    if "id_cm" not in cols or not want:
        return out
    sel = ", ".join(_quote_ident(c) for c in want)
    cur.execute(
        f"""
        SELECT {sel}
        FROM {_quote_ident(schema)}.{_quote_ident("ci_fosc")}
        WHERE id_cm = %s LIMIT 1
        """,
        (fosc_id,),
    )
    row = cur.fetchone()
    if not row:
        return out
    for i, c in enumerate(want):
        out[c] = _cell(row[i])
    return out


def google_maps_url(lat: float, lon: float) -> str:
    """URL Google Maps (dominio global; redirige según ubicación del usuario)."""
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{lat},{lon}")


def _partido_display(cabecera: str, partido_raw: str) -> str:
    loc = _HEADEND_LOCALIDAD.get((cabecera or "").strip().upper(), "")
    if loc:
        return loc
    p = (partido_raw or "").strip()
    if p.upper().startswith("BA "):
        return p[3:].strip().title()
    return p


def _construir_header(
    fusion_id: str,
    rama: str | None,
    h0: dict[str, Any],
    fosc: dict[str, str],
    fosc_id: str,
    lat: float | None,
    lon: float | None,
) -> dict[str, Any]:
    cab = (
        fosc.get("cabecera")
        or cabecera_desde_rama(fusion_id)
        or cabecera_desde_rama(rama or "")
    )
    partido = _partido_display(cab, fosc.get("partido_despliegue", ""))
    headend = _HEADEND_LOCALIDAD.get((cab or "").upper(), partido or "")
    backhaul = f"{cab} | HEADEND {headend}".strip() if cab else (f"HEADEND {headend}".strip() if headend else "")
    maps_url = ""
    if lat is not None and lon is not None:
        maps_url = google_maps_url(lat, lon)

    return {
        "fusion_id": fusion_id,
        "rama_filtro": rama,
        "direccion": fosc.get("direccion") or _cell(h0.get("location_name")),
        "lat": lat,
        "lon": lon,
        "maps_url": maps_url,
        "backhaul": backhaul,
        "nombre_fosc": fosc_id or _cell(h0.get("location_name")),
        "tipo": _cell(h0.get("location_type")) or "FOSC",
        "owner": _cell(h0.get("owner")),
        "alias": fosc.get("nombre_atc") or _cell(h0.get("usedby")),
        "status": _cell(h0.get("location_status")),
        "partido": partido,
        "fusion_num": fusion_codigo_corto(fusion_id),
    }


def consultar_reporte_fusion_export(
    fusion_id: str,
    *,
    rama: str | None = None,
) -> dict[str, Any]:
    """Datos completos para exportar un reporte tipo PDF de ``location_description``."""
    fusion_id = (fusion_id or "").strip().upper()
    rama = (rama or "").strip() or None
    if not es_codigo_fusion_planta(fusion_id):
        return {"ok": False, "error": "Código de fusión inválido (ej. SF01-R1301-010)."}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida."}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_FUSIONES_TABLE).",
            }

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT
                location_fullname, location_name, location_description,
                location_type, location_status, owner, usedby,
                geo_x, geo_y,
                component_fullname_a, component_type_name_a, subcategory_a,
                description_a, component_name_a, point_name_a, point_name_b,
                component_name_b, description_b, subcategory_b,
                component_type_name_b, component_fullname_b,
                physical_path, path_atc, phgr_id, splice, circuit
            FROM {schema_q}.{table_q}
            WHERE location_description = %s
            ORDER BY
                CASE splice WHEN 'EMPALME' THEN 0 WHEN 'CONTINUIDAD' THEN 1 ELSE 2 END,
                path_atc NULLS LAST,
                component_name_a NULLS LAST,
                point_name_a NULLS LAST
            """,
            (fusion_id,),
        )
        colnames = [d[0] for d in (cur.description or [])]
        raw_rows = [dict(zip(colnames, row)) for row in cur.fetchall()]

        if not raw_rows:
            return {
                "ok": False,
                "error": f"Sin filas en report_fusiones para «{fusion_id}».",
            }

        h0 = raw_rows[0]
        fosc_id = _cell(h0.get("location_name")) or _fosc_id_desde_component_fullname(
            h0.get("component_fullname_b")
        )
        fosc = _cargar_fosc(cur, schema, fosc_id)
        if fosc_id and not fosc.get("nombre_atc"):
            fosc["nombre_atc"] = fosc_id

    try:
        lat = round(float(h0.get("geo_y")), 6)
        lon = round(float(h0.get("geo_x")), 6)
    except (TypeError, ValueError):
        lat, lon = None, None

    header = _construir_header(fusion_id, rama, h0, fosc, fosc_id, lat, lon)
    alias_fosc = str(header.get("alias") or "")

    splitter_rows: list[dict[str, Any]] = []
    cable_rows: list[dict[str, Any]] = []

    with db_cursor() as cur_dest:
        for rec in raw_rows:
            path_atc = _cell(rec.get("path_atc"))
            highlight = bool(rama and path_atc == rama)
            sub_a = _cell(rec.get("subcategory_a"))
            sub_b = _cell(rec.get("subcategory_b"))
            circuit = _cell(rec.get("circuit"))
            physical_path = _cell(rec.get("physical_path"))
            cable = _cell(rec.get("description_a"))

            if _es_fila_splitter(rec):
                fibra_a_raw = _cell(rec.get("point_name_a"))
                salida = _cell(rec.get("point_name_b"))
                desc_a = _cell(rec.get("description_a"))
                desc_b = _cell(rec.get("description_b"))
                grupo_in = grupo_para_fila(sub_a, fibra_a_raw)
                fibra_a, col_fibra_a = _fibra_y_color(fibra_a_raw, sub_a)
                _, col_salida = _fibra_y_color(salida, sub_b)
                if _OUT_PORT_RE.match(salida.upper()):
                    fibra_b, col_fibra_b = _fibra_y_color(fibra_a_raw, sub_a)
                    if (
                        not fibra_b
                        or fibra_b.upper().startswith("OUT")
                        or fibra_b.upper() == "IN"
                    ):
                        fibra_b = "1"
                        col_fibra_b = color_desde_numero_fibra("1")
                    grupo_out = grupo_para_fila(sub_a, fibra_a_raw)
                    comp_out = desc_a or desc_b or _cell(rec.get("component_name_b"))
                else:
                    fibra_b, col_fibra_b = _fibra_y_color(salida, sub_b)
                    grupo_out = grupo_para_fila(sub_b, salida)
                    comp_out = desc_b or desc_a or _cell(rec.get("component_name_b"))

                splitter_rows.append(
                    _attach_color_slugs(
                        {
                            "path_in": physical_path,
                            "circuit_in": circuit,
                            "comp_in": desc_a or _cell(rec.get("component_name_a")),
                            "component_name": _cell(rec.get("component_name_b"))
                            or _cell(rec.get("component_name_a")),
                            "grupo_in": grupo_in,
                            "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                            "fibra_port": fibra_a or _cell(rec.get("point_name_a")),
                            "color_fibra_port": col_fibra_a,
                            "salida_splitter": salida,
                            "color_salida": col_salida,
                            "splitter": _splitter_etiqueta(rec),
                            "comp_out": comp_out,
                            "grupo_out": grupo_out,
                            "color_grupo_out": color_grupo_buffer(
                                sub_a if _OUT_PORT_RE.match(salida.upper()) else sub_b, grupo_out
                            ),
                            "fibra_out": fibra_b,
                            "color_fibra_out": col_fibra_b,
                            "destino": destino_cable_reporte(
                                circuit, path_atc, alias_fosc=alias_fosc
                            ),
                            "path_atc": path_atc,
                            "highlight": highlight,
                        }
                    )
                )
            else:
                fibra_in, col_in = _fibra_y_color(_cell(rec.get("point_name_a")), sub_a)
                fibra_out, col_out = _fibra_y_color(_cell(rec.get("point_name_b")), sub_b)
                grupo_in = grupo_para_fila(sub_a, fibra_in or _cell(rec.get("point_name_a")))
                grupo_out = grupo_para_fila(sub_b, fibra_out or _cell(rec.get("point_name_b")))
                cable_rows.append(
                    _attach_color_slugs(
                        {
                            "cable_in": cable,
                            "grupo_in": grupo_in,
                            "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                            "fibra_in": fibra_in,
                            "color_fibra_in": col_in,
                            "rama_salida": rama_cable_reporte(circuit, path_atc),
                            "cable_out": _cell(rec.get("description_b")),
                            "grupo_out": grupo_out,
                            "color_grupo_out": color_grupo_buffer(sub_b, grupo_out),
                            "fibra_out": fibra_out,
                            "color_fibra_out": col_out,
                            "destino": _destino_cable_fusion_export(
                                cur_dest,
                                schema,
                                table,
                                fusion_id,
                                circuit,
                                path_atc,
                                physical_path,
                                cable,
                                alias_fosc=alias_fosc,
                            ),
                            "highlight": highlight,
                        }
                    )
                )

    cable_rows.sort(key=_fibra_sort_key)
    splitter_groups = _agrupar_splitter_rows(splitter_rows)

    from .camino_fusion_bentley_layout import construir_layout_bentley

    bentley = construir_layout_bentley(
        header,
        splitter_rows,
        cable_rows,
        raw_rows,
        fusion_id,
        alias_fosc=alias_fosc,
        rama=rama,
    )

    return {
        "ok": True,
        "fusion_id": fusion_id,
        "rama": rama,
        "header": header,
        "splitter_rows": splitter_rows,
        "splitter_groups": splitter_groups,
        "cable_rows": cable_rows,
        "bentley": bentley,
        "row_count": len(raw_rows),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source_table": f"{schema}.{table}",
    }


_REPORT_FUSIONES_SELECT = """
    location_fullname, location_name, location_description,
    location_type, location_status, owner, usedby,
    geo_x, geo_y,
    component_fullname_a, component_type_name_a, subcategory_a,
    description_a, component_name_a, point_name_a, point_name_b,
    component_name_b, description_b, subcategory_b,
    component_type_name_b, component_fullname_b,
    physical_path, path_atc, phgr_id, splice, circuit
"""


def splice_plan_cm_filename(fosc_id: str) -> str:
    """Nombre de archivo como ConnectMaster «SPLICE PLAN (FOSC BACKHAUL | CIRCUITO)»."""
    fosc = (fosc_id or "").strip()
    if not fosc:
        return "splice-plan.pdf"
    return f"{fosc}-ATC - SPLICE PLAN (FOSC BACKHAUL _ CIRCUITO) - V6.0C.pdf"


def consultar_reporte_fosc_export(
    fosc_id: str,
    *,
    rama: str | None = None,
    solo_circuito: bool = False,
) -> dict[str, Any]:
    """Splice plan completo de la botella (todas las filas ``location_name``, como CM)."""
    fosc_id = (fosc_id or "").strip()
    rama = (rama or "").strip() or None
    if not es_id_fosc_cm(fosc_id):
        return {"ok": False, "error": "Id de FOSC inválido."}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida."}

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_FUSIONES_TABLE).",
            }

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT {_REPORT_FUSIONES_SELECT}
            FROM {schema_q}.{table_q}
            WHERE location_name = %s
            ORDER BY
                CASE splice WHEN 'EMPALME' THEN 0 WHEN 'CONTINUIDAD' THEN 1 ELSE 2 END,
                path_atc NULLS LAST,
                component_name_a NULLS LAST,
                point_name_a NULLS LAST
            """,
            (fosc_id,),
        )
        colnames = [d[0] for d in (cur.description or [])]
        raw_rows = [dict(zip(colnames, row)) for row in cur.fetchall()]

        if solo_circuito and rama:
            raw_rows = [r for r in raw_rows if _cell(r.get("path_atc")) == rama]

        if not raw_rows:
            msg = f"Sin filas en report_fusiones para botella «{fosc_id}»"
            if rama and solo_circuito:
                msg += f" y rama «{rama}»"
            return {"ok": False, "error": msg + "."}

        h0 = raw_rows[0]
        fosc_meta = _cargar_fosc(cur, schema, fosc_id)
        if not fosc_meta.get("nombre_atc"):
            fosc_meta["nombre_atc"] = _cell(h0.get("usedby")) or fosc_id

        report_key = (
            _cell(h0.get("location_description"))
            or fosc_meta.get("nombre_atc")
            or fosc_id
        )

    try:
        lat = round(float(h0.get("geo_y")), 6)
        lon = round(float(h0.get("geo_x")), 6)
    except (TypeError, ValueError):
        lat, lon = None, None

    header = _construir_header(report_key, rama, h0, fosc_meta, fosc_id, lat, lon)
    header["fusion_num"] = fusion_codigo_corto(report_key)
    alias_fosc = str(header.get("alias") or "")

    splitter_rows: list[dict[str, Any]] = []
    cable_rows: list[dict[str, Any]] = []

    physical_paths = {_cell(r.get("physical_path")) for r in raw_rows}
    physical_paths.discard("")
    cables_cont = {
        _cell(r.get("description_a"))
        for r in raw_rows
        if _cell(r.get("splice")).upper() == "CONTINUIDAD"
    }
    cables_cont.discard("")
    usedby = _cell(h0.get("usedby"))
    with db_cursor() as cur_dest:
        dest_cache = _precargar_fusion_destino_map(cur_dest, schema, table, physical_paths)
        dest_fatc_cache = _precargar_destino_fatc_continuidad(
            cur_dest,
            schema,
            table,
            usedby=usedby,
            alias_actual=alias_fosc,
            cables=cables_cont,
        )

    for rec in raw_rows:
        path_atc = _cell(rec.get("path_atc"))
        highlight = bool(rama and path_atc == rama)
        sub_a = _cell(rec.get("subcategory_a"))
        sub_b = _cell(rec.get("subcategory_b"))
        circuit = _cell(rec.get("circuit"))
        physical_path = _cell(rec.get("physical_path"))
        cable_out = _cell(rec.get("description_b"))
        cable_in = _cell(rec.get("description_a"))
        splice = _cell(rec.get("splice"))

        if _es_fila_splitter(rec):
            fibra_a_raw = _cell(rec.get("point_name_a"))
            salida = _cell(rec.get("point_name_b"))
            desc_a = _cell(rec.get("description_a"))
            desc_b = _cell(rec.get("description_b"))
            grupo_in = grupo_para_fila(sub_a, fibra_a_raw)
            fibra_a, col_fibra_a = _fibra_y_color(fibra_a_raw, sub_a)
            _, col_salida = _fibra_y_color(salida, sub_b)
            if _OUT_PORT_RE.match(salida.upper()):
                fibra_b, col_fibra_b = _fibra_y_color(fibra_a_raw, sub_a)
                if (
                    not fibra_b
                    or fibra_b.upper().startswith("OUT")
                    or fibra_b.upper() == "IN"
                ):
                    fibra_b = "1"
                    col_fibra_b = color_desde_numero_fibra("1")
                grupo_out = grupo_para_fila(sub_a, fibra_a_raw)
                comp_out = desc_a or desc_b or _cell(rec.get("component_name_b"))
            else:
                fibra_b, col_fibra_b = _fibra_y_color(salida, sub_b)
                grupo_out = grupo_para_fila(sub_b, salida)
                comp_out = desc_b or desc_a or _cell(rec.get("component_name_b"))

            splitter_rows.append(
                _attach_color_slugs(
                    {
                        "path_in": physical_path,
                        "circuit_in": circuit,
                        "comp_in": desc_a or _cell(rec.get("component_name_a")),
                        "component_name": _cell(rec.get("component_name_b"))
                        or _cell(rec.get("component_name_a")),
                        "grupo_in": grupo_in,
                        "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                        "fibra_port": fibra_a or _cell(rec.get("point_name_a")),
                        "color_fibra_port": col_fibra_a,
                        "salida_splitter": salida,
                        "color_salida": col_salida,
                        "splitter": _splitter_etiqueta(rec),
                        "comp_out": comp_out,
                        "grupo_out": grupo_out,
                        "color_grupo_out": color_grupo_buffer(
                            sub_a if _OUT_PORT_RE.match(salida.upper()) else sub_b, grupo_out
                        ),
                        "fibra_out": fibra_b,
                        "color_fibra_out": col_fibra_b,
                        "destino": destino_cable_reporte(
                            circuit, path_atc, alias_fosc=alias_fosc
                        ),
                        "path_atc": path_atc,
                        "highlight": highlight,
                    }
                )
            )
        else:
            fibra_in, col_in = _fibra_y_color(_cell(rec.get("point_name_a")), sub_a)
            fibra_out, col_out = _fibra_y_color(_cell(rec.get("point_name_b")), sub_b)
            grupo_in = grupo_para_fila(sub_a, fibra_in or _cell(rec.get("point_name_a")))
            grupo_out = grupo_para_fila(sub_b, fibra_out or _cell(rec.get("point_name_b")))
            destino = _destino_cable_fosc_export(
                splice,
                circuit,
                path_atc,
                physical_path,
                cable_in,
                cable_out,
                alias_fosc=alias_fosc,
                dest_fusion_cache=dest_cache,
                dest_fatc_cache=dest_fatc_cache,
            )
            rama_sal = (
                _rama_continuidad_reporte(circuit, path_atc, cable_out, cable_in)
                if splice.upper() == "CONTINUIDAD"
                else rama_cable_reporte(circuit, path_atc)
            )
            cable_rows.append(
                _attach_color_slugs(
                    {
                        "cable_in": _cell(rec.get("description_a")),
                        "grupo_in": grupo_in,
                        "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                        "fibra_in": fibra_in,
                        "color_fibra_in": col_in,
                        "rama_salida": rama_sal,
                        "cable_out": cable_out,
                        "grupo_out": grupo_out,
                        "color_grupo_out": color_grupo_buffer(sub_b, grupo_out),
                        "fibra_out": fibra_out,
                        "color_fibra_out": col_out,
                        "destino": destino,
                        "highlight": highlight,
                    }
                )
            )

    cable_rows.sort(key=_fibra_sort_key)
    splitter_groups = _agrupar_splitter_rows(splitter_rows)

    from .camino_fusion_bentley_layout import construir_layout_bentley

    bentley = construir_layout_bentley(
        header,
        splitter_rows,
        cable_rows,
        raw_rows,
        report_key,
        alias_fosc=alias_fosc,
        rama=rama,
        dedupe_modelo=False,
    )

    return {
        "ok": True,
        "fusion_id": report_key,
        "report_tipo": "fosc",
        "fosc_id": fosc_id,
        "rama": rama,
        "header": header,
        "splitter_rows": splitter_rows,
        "splitter_groups": splitter_groups,
        "cable_rows": cable_rows,
        "bentley": bentley,
        "row_count": len(raw_rows),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source_table": f"{schema}.{table}",
    }


def _tray_sql_pattern(tray: str) -> str:
    t = (tray or "").strip()
    if not t:
        return "%SPLICE TRAY%"
    if "SPLICE TRAY" not in t.upper():
        t = f"SPLICE TRAY {t}"
    return f"%{t}%"


def consultar_reporte_splice_export(
    fosc_id: str,
    *,
    tray: str,
    rama: str | None = None,
    solo_circuito: bool = True,
) -> dict[str, Any]:
    """Splice plan por botella + bandeja (equivalente CM «FOSC BACKHAUL | CIRCUITO»)."""
    fosc_id = (fosc_id or "").strip()
    tray = (tray or "").strip()
    rama = (rama or "").strip() or None
    if not es_id_fosc_cm(fosc_id):
        return {"ok": False, "error": "Id de FOSC inválido."}
    if not tray:
        return {"ok": False, "error": "Parámetro tray requerido (ej. 1 SPLICE TRAY 24F-01)."}

    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table):
        return {"ok": False, "error": "Tabla fusiones inválida."}

    report_key = f"{fosc_id} · {tray}"

    with db_cursor() as cur:
        if not _table_exists(cur, schema, table):
            return {
                "ok": False,
                "error": f"No existe {schema}.{table} (CAMINO_GIS_FUSIONES_TABLE).",
            }

        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT {_REPORT_FUSIONES_SELECT}
            FROM {schema_q}.{table_q}
            WHERE location_name = %s
              AND component_name_a ILIKE %s
            ORDER BY
                CASE splice WHEN 'EMPALME' THEN 0 WHEN 'CONTINUIDAD' THEN 1 ELSE 2 END,
                path_atc NULLS LAST,
                point_name_a NULLS LAST
            """,
            (fosc_id, _tray_sql_pattern(tray)),
        )
        colnames = [d[0] for d in (cur.description or [])]
        raw_rows = [dict(zip(colnames, row)) for row in cur.fetchall()]

        if solo_circuito and rama:
            raw_rows = [r for r in raw_rows if _cell(r.get("path_atc")) == rama]

        if not raw_rows:
            msg = f"Sin filas en report_fusiones para «{fosc_id}» bandeja «{tray}»"
            if rama:
                msg += f" y rama «{rama}»"
            return {"ok": False, "error": msg + "."}

        h0 = raw_rows[0]
        fosc_meta = _cargar_fosc(cur, schema, fosc_id)
        if not fosc_meta.get("nombre_atc"):
            fosc_meta["nombre_atc"] = _cell(h0.get("usedby")) or fosc_id

    try:
        lat = round(float(h0.get("geo_y")), 6)
        lon = round(float(h0.get("geo_x")), 6)
    except (TypeError, ValueError):
        lat, lon = None, None

    header = _construir_header(report_key, rama, h0, fosc_meta, fosc_id, lat, lon)
    header["tipo"] = _cell(h0.get("component_name_a")) or tray
    header["fusion_num"] = ""
    header["fusion_id"] = report_key
    alias_fosc = str(header.get("alias") or "")

    splitter_rows: list[dict[str, Any]] = []
    cable_rows: list[dict[str, Any]] = []

    for rec in raw_rows:
        path_atc = _cell(rec.get("path_atc"))
        highlight = bool(rama and path_atc == rama)
        sub_a = _cell(rec.get("subcategory_a"))
        sub_b = _cell(rec.get("subcategory_b"))

        if _es_fila_splitter(rec):
            fibra_a_raw = _cell(rec.get("point_name_a"))
            salida = _cell(rec.get("point_name_b"))
            desc_a = _cell(rec.get("description_a"))
            desc_b = _cell(rec.get("description_b"))
            grupo_in = grupo_para_fila(sub_a, fibra_a_raw)
            fibra_a, col_fibra_a = _fibra_y_color(fibra_a_raw, sub_a)
            _, col_salida = _fibra_y_color(salida, sub_b)
            if _OUT_PORT_RE.match(salida.upper()):
                fibra_b, col_fibra_b = _fibra_y_color(fibra_a_raw, sub_a)
                if (
                    not fibra_b
                    or fibra_b.upper().startswith("OUT")
                    or fibra_b.upper() == "IN"
                ):
                    fibra_b = "1"
                    col_fibra_b = color_desde_numero_fibra("1")
                grupo_out = grupo_para_fila(sub_a, fibra_a_raw)
                comp_out = desc_a or desc_b or _cell(rec.get("component_name_b"))
            else:
                fibra_b, col_fibra_b = _fibra_y_color(salida, sub_b)
                grupo_out = grupo_para_fila(sub_b, salida)
                comp_out = desc_b or desc_a or _cell(rec.get("component_name_b"))

            splitter_rows.append(
                _attach_color_slugs(
                    {
                        "path_in": _cell(rec.get("physical_path")),
                        "circuit_in": _cell(rec.get("circuit")),
                        "comp_in": desc_a or _cell(rec.get("component_name_a")),
                        "component_name": _cell(rec.get("component_name_b"))
                        or _cell(rec.get("component_name_a")),
                        "grupo_in": grupo_in,
                        "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                        "fibra_port": fibra_a or _cell(rec.get("point_name_a")),
                        "color_fibra_port": col_fibra_a,
                        "salida_splitter": salida,
                        "color_salida": col_salida,
                        "splitter": _splitter_etiqueta(rec),
                        "comp_out": comp_out,
                        "grupo_out": grupo_out,
                        "color_grupo_out": color_grupo_buffer(
                            sub_a if _OUT_PORT_RE.match(salida.upper()) else sub_b, grupo_out
                        ),
                        "fibra_out": fibra_b,
                        "color_fibra_out": col_fibra_b,
                        "destino": destino_cable_reporte(
                            _cell(rec.get("circuit")), path_atc, alias_fosc=alias_fosc
                        ),
                        "path_atc": path_atc,
                        "highlight": highlight,
                    }
                )
            )
        else:
            fibra_in, col_in = _fibra_y_color(_cell(rec.get("point_name_a")), sub_a)
            fibra_out, col_out = _fibra_y_color(_cell(rec.get("point_name_b")), sub_b)
            grupo_in = grupo_para_fila(sub_a, fibra_in or _cell(rec.get("point_name_a")))
            grupo_out = grupo_para_fila(sub_b, fibra_out or _cell(rec.get("point_name_b")))
            circuit = _cell(rec.get("circuit"))
            cable_rows.append(
                _attach_color_slugs(
                    {
                        "cable_in": _cell(rec.get("description_a")),
                        "grupo_in": grupo_in,
                        "color_grupo_in": color_grupo_buffer(sub_a, grupo_in),
                        "fibra_in": fibra_in,
                        "color_fibra_in": col_in,
                        "rama_salida": path_atc or circuit,
                        "cable_out": _cell(rec.get("description_b")),
                        "grupo_out": grupo_out,
                        "color_grupo_out": color_grupo_buffer(sub_b, grupo_out),
                        "fibra_out": fibra_out,
                        "color_fibra_out": col_out,
                        "destino": destino_cable_reporte(
                            circuit, path_atc, alias_fosc=alias_fosc
                        ),
                        "highlight": highlight,
                    }
                )
            )

    cable_rows.sort(key=_fibra_sort_key)
    splitter_groups = _agrupar_splitter_rows(splitter_rows)

    from .camino_fusion_bentley_layout import construir_layout_bentley

    bentley = construir_layout_bentley(
        header,
        splitter_rows,
        cable_rows,
        raw_rows,
        report_key,
        alias_fosc=alias_fosc,
        rama=rama,
        dedupe_modelo=False,
    )

    return {
        "ok": True,
        "fusion_id": report_key,
        "report_tipo": "splice",
        "fosc_id": fosc_id,
        "tray": tray,
        "rama": rama,
        "header": header,
        "splitter_rows": splitter_rows,
        "splitter_groups": splitter_groups,
        "cable_rows": cable_rows,
        "bentley": bentley,
        "row_count": len(raw_rows),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source_table": f"{schema}.{table}",
    }
