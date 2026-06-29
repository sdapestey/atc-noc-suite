"""Reporte de rama ConnectMaster (trazado + inventario) para Camino óptico."""
from __future__ import annotations

import re
from typing import Any

from db import db_cursor

from .camino_gis import (
    _env_fusiones_table,
    _env_schema,
    _lookup_ci_fosc_meta,
    _table_exists,
    _validate_ident,
    _quote_ident,
)

_FOSC_RE = re.compile(r"[A-Z]{2}\d{6}-FOSC-", re.I)
_GPON_PORT_RE = re.compile(r"GPON-(\d+)", re.I)


_FOSC_ID_RE = re.compile(
    r"([A-Z]{2}\d{6}-FOSC-[0-9]{2}-[0-9]{6}-[0-9]{4})",
    re.I,
)
_FEL_RE = re.compile(r"FEL\d+", re.I)


def consultar_reporte_rama_cm(rama: str) -> dict[str, Any]:
    """Trazado e inventario de rama como el PDF «RAMA» de ConnectMaster."""
    rama = (rama or "").strip()
    if not rama:
        return {"ok": False, "error": "Rama vacía."}

    trazado: list[dict[str, str]] = []
    inventario: list[dict[str, str]] = []
    isp_osp: dict[str, Any] | None = None
    filas_ruta_fisica: list[dict[str, Any]] = []

    with db_cursor() as cur:
        isp_osp = _fetch_isp_osp(cur, rama)
        if isp_osp:
            trazado.extend(_trazado_cabecera_isp_osp(isp_osp))
            inventario.extend(_inventario_cabecera_isp_osp(isp_osp))

        trazado_campo, inv_campo = _trazado_inventario_campo(cur, rama)
        trazado.extend(trazado_campo)
        inventario.extend(inv_campo)

        inv_e2e = _inventario_e2e(cur, rama)
        inventario = _dedupe_inventario(inventario + inv_e2e)

        trazado_cm = _trazado_rama_cm_canonico(cur, rama, isp_osp)
        if trazado_cm:
            trazado = trazado_cm
            inventario = _inventario_alineado_trazado(inventario, trazado)

        filas_ruta_fisica = _filas_ruta_fisica(trazado, inventario, isp_osp, cur, rama)

    if not trazado and not inventario:
        return {
            "ok": False,
            "error": f"Sin datos de reporte CM para la rama «{rama}».",
            "rama": rama,
        }

    return {
        "ok": True,
        "rama": rama,
        "trazado": trazado,
        "inventario": inventario,
        "filas_ruta_fisica": filas_ruta_fisica,
        "isp_osp": isp_osp,
        "fuente": "cm_report_isp + report_isp_osp + report_fusiones + report_e2e",
    }


def _trazado_rama_cm_canonico(
    cur,
    rama: str,
    isp_osp: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """~19 filas del PDF RAMA: cabecera + un salto por botella en el camino principal."""
    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table) or not _table_exists(cur, schema, table):
        return []

    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    cur.execute(
        f"""
        SELECT
            location_fullname,
            location_name,
            component_fullname_a,
            point_name_a,
            component_fullname_b,
            point_name_b,
            splice,
            subcategory_a,
            subcategory_b,
            description_a,
            description_b,
            component_type_name_a,
            component_type_name_b,
            location_status,
            usedby
        FROM {schema_q}.{table_q}
        WHERE path_atc = %s AND circuit = %s
        ORDER BY phgr_id
        """,
        (rama, rama),
    )
    raw_rows = cur.fetchall()
    if not raw_rows:
        return []

    parsed = [_parse_fusion_row(r) for r in raw_rows]
    feeder = str((isp_osp or {}).get("cable_feeder_name") or "").strip()
    if not feeder:
        for p in parsed:
            if _FEL_RE.search(p["comp_a"] or ""):
                feeder = (p["comp_a"] or "").strip()
                break
    if not feeder:
        return []

    cabecera = _trazado_cabecera_isp_osp(isp_osp) if isp_osp else []
    campo = _caminar_trazado_principal(parsed, feeder)
    if not campo:
        return []

    out = list(cabecera)
    seen: set[tuple[str, str, str]] = set()
    for row in out:
        seen.add((row["ubicacion"], row["componente"], row["punto"]))
    for row in campo:
        key = (row["ubicacion"], row["componente"], row["punto"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _parse_fusion_row(row: tuple) -> dict[str, Any]:
    return {
        "loc_full": (row[0] or "").strip(),
        "loc_name": (row[1] or "").strip(),
        "comp_a": (row[2] or "").strip(),
        "pt_a": (row[3] or "").strip(),
        "comp_b": (row[4] or "").strip(),
        "pt_b": (row[5] or "").strip(),
        "splice": (row[6] or "").strip().upper(),
        "sub_a": (row[7] or "").strip(),
        "sub_b": (row[8] or "").strip(),
        "desc_a": (row[9] or "").strip(),
        "desc_b": (row[10] or "").strip(),
        "tipo_a": (row[11] or "").strip(),
        "tipo_b": (row[12] or "").strip(),
        "loc_status": (row[13] or "").strip(),
        "usedby": (row[14] or "").strip(),
    }


def _cable_key(comp: str) -> str:
    return (comp or "").strip().upper()


def _caminar_trazado_principal(rows: list[dict[str, Any]], feeder: str) -> list[dict[str, str]]:
    """Recorre empalmes/continuidad desde el feeder hasta el splitter de la rama."""
    by_cable: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for side in ("a", "b"):
            comp = row[f"comp_{side}"]
            if not comp:
                continue
            by_cable.setdefault(_cable_key(comp), []).append(row)

    current = feeder
    visited_locs: set[str] = set()
    visited_fosc: set[str] = set()
    visited_cables: set[str] = {_cable_key(feeder)}
    trace: list[dict[str, str]] = []
    steps = 0
    max_steps = 40

    while steps < max_steps:
        steps += 1
        hop = _pick_next_hop(
            by_cable.get(_cable_key(current), []),
            current,
            visited_locs,
            visited_fosc,
            visited_cables,
        )
        if not hop:
            spl = _splitter_fin_rama(rows, visited_locs)
            if spl:
                trace.extend(spl)
            break

        loc_key = hop["loc_name"] or hop["loc_full"]
        if hop.get("fosc_id"):
            if hop["fosc_id"] in visited_fosc:
                break
            visited_fosc.add(hop["fosc_id"])
        if loc_key:
            visited_locs.add(loc_key)

        row = {
            "ubicacion": hop["loc_full"] or hop["loc_name"],
            "componente": hop["comp_show"],
            "punto": hop["punto_show"],
            "fosc_id": hop.get("fosc_id") or "",
            "etapa": hop.get("etapa") or "",
        }
        if not trace or (
            trace[-1]["ubicacion"],
            trace[-1]["componente"],
            trace[-1]["punto"],
        ) != (row["ubicacion"], row["componente"], row["punto"]):
            trace.append(row)

        current = hop["comp_fwd"]
        visited_cables.add(_cable_key(hop["comp_show"]))
        if "SPL" in (current or "").upper() and hop.get("etapa") == "splitter":
            spl = _splitter_fin_rama(rows, visited_locs)
            if spl:
                for s in spl:
                    key = (s["ubicacion"], s["componente"], s["punto"])
                    if not trace or (trace[-1]["ubicacion"], trace[-1]["componente"], trace[-1]["punto"]) != key:
                        trace.append(s)
            break
        if not current:
            spl = _splitter_fin_rama(rows, visited_locs)
            if spl:
                trace.extend(spl)
            break

    return trace


def _pick_next_hop(
    candidates: list[dict[str, Any]],
    current: str,
    visited_locs: set[str],
    visited_fosc: set[str],
    visited_cables: set[str],
) -> dict[str, Any] | None:
    cur_k = _cable_key(current)
    best: dict[str, Any] | None = None
    best_score = -999

    for row in candidates:
        if row["comp_a"] and _cable_key(row["comp_a"]) == cur_k:
            other, pt_other = row["comp_b"], row["pt_b"]
            pt_cur = row["pt_a"]
        elif row["comp_b"] and _cable_key(row["comp_b"]) == cur_k:
            other, pt_other = row["comp_a"], row["pt_a"]
            pt_cur = row["pt_b"]
        else:
            continue

        if not other or _cable_key(other) == cur_k:
            continue
        if _cable_key(other) in visited_cables:
            continue

        loc_name = row["loc_name"]
        loc_full = row["loc_full"]
        fm = _FOSC_ID_RE.search(loc_name or loc_full or "")
        fosc_id = fm.group(1) if fm else ""
        if fosc_id and fosc_id in visited_fosc:
            continue
        if loc_name in visited_locs and fosc_id:
            continue

        score = 0
        if row["splice"] == "CONTINUIDAD":
            score += 30
        if _FEL_RE.search(other):
            score += 20
        if "FOSC" in (loc_name or "").upper():
            score += 10
        if "SPL" in other.upper():
            score -= 5
        if "DSL" in other.upper():
            score -= 15
        if "SFAT" in (loc_full or "").upper():
            score -= 20
        if not fosc_id and "FOSC" not in (loc_full or "").upper() and row["splice"] != "CONTINUIDAD":
            score -= 5

        if score > best_score:
            best_score = score
            fosc_id = ""
            fm = _FOSC_ID_RE.search(loc_name or loc_full or "")
            if fm:
                fosc_id = fm.group(1)
            etapa = "cabecera"
            if fosc_id:
                etapa = "fosc"
            elif "SPL" in (other or "").upper():
                etapa = "splitter"
            best = {
                "loc_name": loc_name,
                "loc_full": loc_full or loc_name,
                "comp_show": other,
                "punto_show": pt_other or pt_cur or "",
                "comp_fwd": other,
                "fosc_id": fosc_id,
                "etapa": etapa,
            }

    return best


def _splitter_fin_rama(
    rows: list[dict[str, Any]],
    visited_locs: set[str],
) -> list[dict[str, str]]:
    """Splitter IN + OUT principal (como filas 18–19 del PDF CM)."""
    spl_rows = [
        r
        for r in rows
        if "SPL" in (r["comp_a"] or "").upper()
        and _FOSC_ID_RE.search(r["loc_name"] or "")
        and (r["loc_name"] or "") not in visited_locs
    ]
    if not spl_rows:
        spl_rows = [
            r
            for r in rows
            if "SPL" in (r["comp_a"] or "").upper() and _FOSC_ID_RE.search(r["loc_name"] or "")
        ]
    if not spl_rows:
        return []

    loc_name = spl_rows[0]["loc_name"]
    loc_full = spl_rows[0]["loc_full"]
    visited_locs.add(loc_name)

    in_row = next((r for r in spl_rows if (r["pt_a"] or "").upper() == "IN"), spl_rows[0])
    out_rows = [r for r in spl_rows if (r["pt_a"] or "").upper().startswith("OUT")]
    out_row = None
    if out_rows:
        def _out_num(r: dict[str, Any]) -> int:
            m = re.search(r"OUT(\d+)", str(r.get("pt_a") or ""), re.I)
            return int(m.group(1)) if m else 0

        out_row = max(out_rows, key=_out_num)

    result = [
        {
            "ubicacion": loc_full or loc_name,
            "componente": in_row["comp_a"],
            "punto": in_row["pt_a"] or "IN",
            "fosc_id": _FOSC_ID_RE.search(loc_name or "").group(1) if _FOSC_ID_RE.search(loc_name or "") else "",
            "etapa": "splitter",
        }
    ]
    if out_row:
        result.append(
            {
                "ubicacion": loc_full or loc_name,
                "componente": out_row["comp_a"],
                "punto": out_row["pt_a"] or "OUT",
                "fosc_id": result[0]["fosc_id"],
                "etapa": "splitter",
            }
        )
    return result


def _inventario_alineado_trazado(
    inventario: list[dict[str, str]],
    trazado: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Un ítem de inventario por fila de trazado (como hoja 2 del PDF CM)."""
    by_desc: dict[str, dict[str, str]] = {}
    for item in inventario:
        d = (item.get("descripcion") or "").strip().upper()
        if d and d not in by_desc:
            by_desc[d] = item

    aligned: list[dict[str, str]] = []
    for i, row in enumerate(trazado, start=1):
        comp = (row.get("componente") or "").strip()
        comp_u = comp.upper()
        item = None
        if i <= 6:
            for key, cand in by_desc.items():
                if key in comp_u or comp_u in key:
                    item = cand
                    break
        if not item and "FEL" in comp_u:
            bentley = _bentley_desde_fel(comp)
            if bentley:
                item = by_desc.get(bentley.upper())
        if not item and "SPL" in comp_u:
            item = next((v for k, v in by_desc.items() if "SPLITTER" in k), None)
        if not item:
            item = {
                "punto": row.get("etapa") or "Tramo",
                "tipo": "G30",
                "usado_por": "G30",
                "descripcion": comp[:80] or "—",
                "tipo_componente": row.get("etapa") or "—",
                "status_componente": "",
                "status_fibra": "",
            }
        aligned.append(dict(item))
    return aligned


def _fetch_isp_osp(cur, rama: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *
        FROM cm.report_isp_osp
        WHERE path_atc = %s
        ORDER BY upload_date DESC NULLS LAST
        LIMIT 1
        """,
        (rama,),
    )
    row = cur.fetchone()
    if not row:
        return None
    keys = [d[0] for d in cur.description]
    return {k: (v if v is not None else "") for k, v in zip(keys, row)}


def _ubicacion_isp_osp(r: dict[str, Any]) -> str:
    shelter = str(r.get("shelter") or "").strip()
    if shelter.isdigit():
        shelter = shelter.zfill(2)
    return ";".join(
        [
            str(r.get("state") or "").strip(),
            str(r.get("city") or "").strip(),
            str(r.get("headend") or "").strip(),
            shelter,
        ]
    )


def _trazado_cabecera_isp_osp(r: dict[str, Any]) -> list[dict[str, str]]:
    u = _ubicacion_isp_osp(r)
    rows: list[dict[str, str]] = []
    olt_port = str(r.get("olt_port") or "").strip()
    port_num = _GPON_PORT_RE.search(olt_port)
    port_n = port_num.group(1) if port_num else olt_port.replace("GPON-", "")
    olt_comp = (
        f"{r.get('olt_rack') or ''}>{r.get('ru_rack_olt') or ''}"
        f"<{r.get('olt_name') or ''}>{r.get('olt_slot') or ''}"
        f"<{r.get('olt_card') or ''}>PON Port {port_n}<{olt_port} TX/RX"
    )
    rows.append({"ubicacion": u, "componente": olt_comp, "punto": "TX/RX", "etapa": "cabecera"})

    patch = str(r.get("cable_patch_cord_name") or "").strip()
    if patch:
        rows.append(
            {
                "ubicacion": u,
                "componente": patch,
                "punto": str(r.get("cable_patch_cord_fiber") or "").strip(),
                "etapa": "cabecera",
            }
        )

    odf_rack = str(r.get("odf_rack_name") or "").strip()
    odf_name = str(r.get("odf_name") or "").strip()
    odf_point = str(r.get("odf_point_name") or "").strip()
    if not odf_rack:
        odf_rack = str(r.get("fec_rack_name") or "").strip()
    if odf_rack and odf_name:
        ru = "30"
        rows.append(
            {
                "ubicacion": u,
                "componente": f"{odf_rack}>{ru}<{odf_name}",
                "punto": odf_point,
                "etapa": "cabecera",
            }
        )

    trunk = str(r.get("cable_trunk_name") or "").strip()
    if trunk:
        fib = str(r.get("cable_trunk_fiber") or "").strip()
        rows.append(
            {
                "ubicacion": u,
                "componente": trunk,
                "punto": f"Fibra {fib}" if fib and not fib.lower().startswith("fibra") else fib,
                "etapa": "cabecera",
            }
        )

    fec_rack = str(r.get("fec_rack_name") or "").strip()
    fec_name = str(r.get("fec_name") or "").strip()
    fec_port = str(r.get("fec_port") or "").strip()
    if fec_rack and fec_name:
        ru = str(r.get("fec_rack_ru") or "").strip()
        rows.append(
            {
                "ubicacion": u,
                "componente": f"{fec_rack}>{ru}<{fec_name}",
                "punto": fec_port,
                "etapa": "cabecera",
            }
        )

    feeder = str(r.get("cable_feeder_name") or "").strip()
    if feeder:
        fib = str(r.get("cable_feeder_fibber_color") or r.get("feeder_fiber_group") or "").strip()
        punto = f"Fibra {fib}" if fib and not str(fib).lower().startswith("fibra") else str(fib)
        rows.append({"ubicacion": u, "componente": feeder, "punto": punto, "etapa": "cabecera"})

    return rows


def _bentley_desde_fel(comp: str) -> str:
    m = re.search(r"(SF[0-9]+-(?:CATC|FATC)-[0-9]-[0-9]+)", comp, re.I)
    if m:
        return m.group(1)
    return ""


def _inventario_cabecera_isp_osp(r: dict[str, Any]) -> list[dict[str, str]]:
    g30 = str(r.get("company") or "G30").strip() or "G30"
    rows: list[dict[str, str]] = []

    def add(punto: str, tipo: str, desc: str, tipo_comp: str, st: str = "IN SERVICE", fibra: str = ""):
        if not desc:
            return
        rows.append(
            {
                "punto": punto,
                "tipo": tipo,
                "usado_por": g30,
                "descripcion": desc,
                "tipo_componente": tipo_comp,
                "status_componente": st,
                "status_fibra": fibra or st,
            }
        )

    add("SFP GPON", g30, str(r.get("olt_port_type") or ""), "SFP GPON C+")
    add("PATCH CORD CABLE", g30, str(r.get("cable_patch_cord_type") or ""), "PATCH CORD 1F")
    add("ODF PANEL", g30, str(r.get("odf_name") or ""), "ODF 144F")
    add("TRUNK CABLE", g30, str(r.get("cable_trunk_type") or ""), "TRUNK CABLE 144F", fibra="IN SERVICE")
    add("FEC TRAY", g30, str(r.get("fec_name") or ""), "FEC TRAY 24F")
    desc = str(r.get("cable_feeder_description") or r.get("cable_feeder_name") or "").strip()
    add("FEEDER CABLE L1", g30, desc, str(r.get("cable_feeder_type") or "CABLE-144F"), fibra="IN SERVICE")
    return rows


def _trazado_inventario_campo(cur, rama: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    schema = _env_schema()
    table = _env_fusiones_table()
    if not _validate_ident(schema, table) or not _table_exists(cur, schema, table):
        return [], []

    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    cur.execute(
        f"""
        SELECT
            location_fullname,
            location_name,
            location_description,
            location_status,
            usedby,
            component_fullname_a,
            point_name_a,
            component_fullname_b,
            point_name_b,
            component_type_name_a,
            component_type_name_b,
            subcategory_a,
            subcategory_b,
            description_a,
            description_b,
            splice
        FROM {schema_q}.{table_q}
        WHERE path_atc = %s AND circuit = %s
        ORDER BY
            CASE WHEN splice = 'CONTINUIDAD' THEN 0 WHEN splice = 'EMPALME' THEN 1 ELSE 2 END,
            location_fullname,
            component_fullname_a
        """,
        (rama, rama),
    )
    raw = cur.fetchall()
    trazado: list[dict[str, str]] = []
    inventario: list[dict[str, str]] = []
    seen_trace: set[tuple[str, str, str]] = set()

    for row in raw:
        (
            loc_full,
            loc_name,
            loc_desc,
            loc_status,
            usedby,
            comp_a,
            pt_a,
            comp_b,
            pt_b,
            tipo_a,
            tipo_b,
            sub_a,
            sub_b,
            desc_a,
            desc_b,
            splice,
        ) = row
        ubic = _ubicacion_fila(loc_full, loc_name)
        for comp, punto in ((comp_a, pt_a), (comp_b, pt_b)):
            comp_s = (comp or "").strip()
            pt_s = (punto or "").strip()
            if not comp_s:
                continue
            key = (ubic, comp_s, pt_s)
            if key in seen_trace:
                continue
            if _es_fila_trazado_campo(comp_s, splice):
                seen_trace.add(key)
                trazado.append({"ubicacion": ubic, "componente": comp_s, "punto": pt_s})

        tipo = (usedby or "G30").strip() or "G30"
        for desc, subcat, tipo_comp, st in (
            (desc_a, sub_a, tipo_a, loc_status),
            (desc_b, sub_b, tipo_b, loc_status),
        ):
            desc_s = (desc or "").strip()
            if not desc_s or not subcat:
                continue
            inventario.append(
                {
                    "punto": (loc_desc or loc_name or desc_s).strip(),
                    "tipo": tipo,
                    "usado_por": tipo,
                    "descripcion": desc_s,
                    "tipo_componente": (subcat or tipo_comp or "").strip(),
                    "status_componente": (st or "").strip(),
                    "status_fibra": (st or "").strip() if "CABLE" in str(subcat or "").upper() else "",
                }
            )

    trazado.sort(key=_sort_key_trazado)
    return trazado, inventario


def _ubicacion_fila(loc_full: str | None, loc_name: str | None) -> str:
    loc = (loc_full or "").strip()
    if loc:
        return loc
    name = (loc_name or "").strip()
    if _FOSC_RE.search(name):
        return name
    return name or "—"


def _es_fila_trazado_campo(comp: str, splice: str | None) -> bool:
    c = comp.upper()
    if any(x in c for x in ("RACK_", "PCOR", "TRUN-", "FEL", "FOSC", "DSL", "SPL", "SFAT")):
        return True
    return (splice or "").strip().upper() in ("CONTINUIDAD", "EMPALME")


def _sort_key_trazado(row: dict[str, str]) -> tuple:
    u = row.get("ubicacion") or ""
    c = (row.get("componente") or "").upper()
    fosc_m = re.search(r"FOSC-\d+-(\d+)", u, re.I)
    fosc_ord = int(fosc_m.group(1)) if fosc_m else 0
    tier = 0
    if "RACK_" in c or "PCOR" in c:
        tier = 0
    elif "TRUN" in c:
        tier = 1
    elif "FEL1" in c:
        tier = 2
    elif "FOSC" in u.upper() or "FEL" in c:
        tier = 3 + fosc_ord / 1_000_000
    elif "SPL" in c or "DSL" in c:
        tier = 4
    return (tier, u, c)


def _inventario_e2e(cur, rama: str) -> list[dict[str, str]]:
    if not _table_exists(cur, "cm", "report_e2e"):
        return []
    cur.execute(
        """
        SELECT
            location_description,
            location_usedby,
            component_type_name,
            subcategory,
            location_status,
            status
        FROM cm.report_e2e
        WHERE path_atc = %s
        ORDER BY location_fullname, componente_fullname
        """,
        (rama,),
    )
    rows: list[dict[str, str]] = []
    for loc_desc, usedby, tipo_comp, subcat, loc_st, fib_st in cur.fetchall():
        rows.append(
            {
                "punto": (loc_desc or "").strip(),
                "tipo": (usedby or "G30").strip() or "G30",
                "usado_por": (usedby or "G30").strip() or "G30",
                "descripcion": (tipo_comp or subcat or "").strip(),
                "tipo_componente": (subcat or tipo_comp or "").strip(),
                "status_componente": (loc_st or "").strip(),
                "status_fibra": (fib_st or "").strip(),
            }
        )
    return rows


def _dedupe_inventario(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        key = tuple(str(r.get(k) or "") for k in ("punto", "descripcion", "tipo_componente"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _filas_ruta_fisica(
    trazado: list[dict[str, str]],
    inventario: list[dict[str, str]],
    isp_osp: dict[str, Any] | None,
    cur,
    rama: str,
) -> list[dict[str, Any]]:
    """Filas unificadas como el reporte «Ruta Física» de ConnectMaster."""
    if not trazado:
        return []

    segmentos = _segmentos_longitud_fel(cur, trazado)
    g30 = str((isp_osp or {}).get("company") or "G30").strip() or "G30"
    schema = _env_schema()
    fosc_ids = list({(row.get("fosc_id") or "").strip() for row in trazado if row.get("fosc_id")})
    fosc_meta = _batch_meta_fosc_ruta_fisica(cur, schema, rama, fosc_ids)
    filas: list[dict[str, Any]] = []

    for idx, (row, inv) in enumerate(zip(trazado, inventario or [{}] * len(trazado))):
        inv = inv or {}
        etapa = row.get("etapa") or ""
        comp = (row.get("componente") or "").strip()
        seg_m = float(segmentos.get(idx, 0.0) or 0.0)
        fosc_id = (row.get("fosc_id") or "").strip()
        meta = fosc_meta.get(fosc_id) or {}

        filas.append(
            {
                "marca": _marca_ruta_fisica(idx, len(trazado), row, trazado),
                "ubicacion_alias": _alias_botella_fila(row, meta),
                "direccion": meta.get("direccion") or "",
                "lat": meta.get("lat"),
                "lon": meta.get("lon"),
                "componente": comp,
                "punto": row.get("punto") or "",
                "tipo": inv.get("tipo") or g30,
                "tipo_componente": inv.get("tipo_componente") or "",
                "status_componente": inv.get("status_componente") or "",
                "longitud_m": _fmt_m(seg_m) if seg_m else "0",
                "etapa": etapa,
                "fosc_id": fosc_id,
            }
        )
    return filas


def _batch_meta_fosc_ruta_fisica(
    cur,
    schema: str,
    rama: str,
    fosc_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Alias, dirección y coordenadas por botella (ci_fosc + report_fusiones)."""
    ids = [f for f in fosc_ids if f]
    if not ids:
        return {}

    out: dict[str, dict[str, Any]] = {fid: {} for fid in ids}

    if _table_exists(cur, schema, "ci_fosc"):
        schema_q = _quote_ident(schema)
        cur.execute(
            f"""
            SELECT
                id_cm,
                nombre_atc,
                direccion,
                CASE WHEN geom IS NOT NULL THEN ST_Y(geom::geometry) END AS lat,
                CASE WHEN geom IS NOT NULL THEN ST_X(geom::geometry) END AS lon
            FROM {schema_q}.ci_fosc
            WHERE id_cm = ANY(%s)
            """,
            (ids,),
        )
        for id_cm, nombre_atc, direccion, lat, lon in cur.fetchall():
            fid = (id_cm or "").strip()
            if not fid:
                continue
            rec = out.setdefault(fid, {})
            rec["alias"] = (nombre_atc or "").strip()
            rec["direccion"] = (direccion or "").strip()
            if lat is not None and lon is not None:
                try:
                    rec["lat"] = round(float(lat), 6)
                    rec["lon"] = round(float(lon), 6)
                except (TypeError, ValueError):
                    pass

    table = _env_fusiones_table()
    if rama and _validate_ident(schema, table) and _table_exists(cur, schema, table):
        schema_q = _quote_ident(schema)
        table_q = _quote_ident(table)
        cur.execute(
            f"""
            SELECT
                location_name,
                MIN(geo_y) AS lat,
                MIN(geo_x) AS lon
            FROM {schema_q}.{table_q}
            WHERE path_atc = %s AND location_name = ANY(%s)
              AND geo_y IS NOT NULL AND geo_x IS NOT NULL
            GROUP BY location_name
            """,
            (rama, ids),
        )
        for loc_name, lat, lon in cur.fetchall():
            fid = (loc_name or "").strip()
            if not fid:
                continue
            rec = out.setdefault(fid, {})
            if lat is not None and lon is not None:
                try:
                    if rec.get("lat") is None:
                        rec["lat"] = round(float(lat), 6)
                        rec["lon"] = round(float(lon), 6)
                except (TypeError, ValueError):
                    pass

    for fid in ids:
        if not out.get(fid, {}).get("alias"):
            meta = _lookup_ci_fosc_meta(cur, schema, fid)
            rec = out.setdefault(fid, {})
            if not rec.get("alias"):
                rec["alias"] = (meta.get("nombre_atc") or "").strip()
            if not rec.get("direccion"):
                rec["direccion"] = (meta.get("direccion") or "").strip()

    return out


def _alias_botella_fila(
    row: dict[str, str],
    meta: dict[str, Any] | None = None,
) -> str:
    if (row.get("etapa") or "") == "cabecera":
        return "Cabecera"
    if meta and meta.get("alias"):
        return str(meta["alias"])
    return ""


def _fmt_m(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _marca_ruta_fisica(
    idx: int,
    total: int,
    row: dict[str, str],
    trazado: list[dict[str, str]],
) -> str:
    if idx == 0:
        return "Inicio"
    punto = (row.get("punto") or "").upper()
    comp = (row.get("componente") or "").upper()
    if "SPL" in comp and punto == "IN":
        return "Derivación"
    if idx == total - 1 or ("SPL" in comp and punto.startswith("OUT")):
        return "Fin"
    return ""


def _segmentos_longitud_fel(cur, trazado: list[dict[str, str]]) -> dict[int, float]:
    """Longitud de segmento (m) por fila, desde ci_feeder_distribution."""
    fel_ids = []
    idx_by_id: dict[str, list[int]] = {}
    for i, row in enumerate(trazado):
        comp = (row.get("componente") or "").strip()
        if "FEL" not in comp.upper():
            continue
        m = re.search(r"([A-Z]{2}\d{6}-FEL\d+-\d+-\d+-\d+)", comp, re.I)
        if not m:
            continue
        fel_id = m.group(1).upper()
        fel_ids.append(fel_id)
        idx_by_id.setdefault(fel_id, []).append(i)

    if not fel_ids or not _table_exists(cur, "cm", "ci_feeder_distribution"):
        return {}

    cur.execute(
        """
        SELECT UPPER(id_cm), MAX(largo)
        FROM cm.ci_feeder_distribution
        WHERE UPPER(id_cm) = ANY(%s)
        GROUP BY UPPER(id_cm)
        """,
        (list(set(fel_ids)),),
    )
    largo_by_id = {str(r[0]): float(r[1] or 0) for r in cur.fetchall()}

    out: dict[int, float] = {}
    for fel_id, indices in idx_by_id.items():
        largo = largo_by_id.get(fel_id.upper(), 0.0)
        if largo <= 0:
            continue
        out[indices[0]] = largo
    return out
