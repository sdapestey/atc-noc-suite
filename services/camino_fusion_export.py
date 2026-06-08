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
    """Ej. SF01-R1301-010 → «13» (como PDF Bentley)."""
    m = _FUSION_ID_RE.match((fusion_id or "").strip().upper())
    if not m:
        return ""
    block = m.group(1)
    return block[:2] if len(block) >= 2 else block


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
