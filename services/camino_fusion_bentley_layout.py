"""Maquetación reporte fusión estilo Bentley (PDF modelo SF01-R1301-010)."""
from __future__ import annotations

import re
from typing import Any

from .camino_fusion_export import (
    _FIBRA_NUM_RE,
    _OUT_PORT_RE,
    _attach_color_slugs,
    _owner_etiqueta,
    color_desde_puerto_out,
    destino_cable_reporte,
)

_OUT_PAD_58 = {5: "GRIS", 6: "BLANCO", 7: "ROJO", 8: "NEGRO"}
_OUT_DEST_DELTA = {1: 2, 2: 3, 3: 1, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}
_SP_LABEL_RE = re.compile(r"^\[ SP\d+ \] SPLITTER", re.I)


def destino_splitter(
    fusion_id: str,
    port: str,
    desc_b: str,
    circuit: str,
    path_atc: str,
    *,
    alias_fosc: str = "",
    path_in: str = "",
) -> str:
    """Destino en empalmes splitter (Bentley: SF01-R1301-012 por OUT1, etc.)."""
    db = (desc_b or "").strip()
    path_ctx = path_in or path_atc or ""
    if db and re.search(r"CATC", db, re.I) and "010101" in path_ctx:
        return re.sub(r"CATC", "FATC", db, count=1, flags=re.I)
    if db and db.lower() not in ("null", "none") and re.search(r"FATC", db, re.I):
        return db
    m = re.match(r"^(SF\d+)-R(\d+)-(\d+)$", (fusion_id or "").strip(), re.I)
    om = _OUT_PORT_RE.match((port or "").strip().upper())
    if m and om:
        site, block_s, suf_s = m.group(1), m.group(2), m.group(3)
        try:
            last = int(suf_s)
            out_n = int(om.group(1))
            if out_n in _OUT_DEST_DELTA:
                return f"{site.upper()}-R{block_s}-{last + _OUT_DEST_DELTA[out_n]:03d}"
        except ValueError:
            pass
    if db and db.lower() not in ("null", "none") and re.match(r"SF\d+-", db, re.I):
        if not re.match(r"SF\d+-RATC-0-", db, re.I):
            return db
    return destino_cable_reporte(circuit, path_atc, alias_fosc=alias_fosc)


def _owner_from_path(path_in: str) -> str:
    if "010201" in (path_in or ""):
        return "AMX"
    return "ATC"


def _splitter_sp_label(rec: dict[str, Any], sp_idx: int, path_in: str = "") -> str:
    tb = (rec.get("component_type_name_b") or rec.get("splitter") or "").upper()
    owner = _owner_from_path(path_in) if path_in else _owner_etiqueta(rec)
    if "1:2" in tb:
        kind = "1:2"
    elif "1:8" in tb:
        kind = "1:8"
    else:
        kind = "SPLITTER"
    return f"[ SP{sp_idx} ] SPLITTER {kind} [ {owner} ]"


def _path_sort_key(path: str) -> tuple[int, str]:
    return (0 if "010201" in (path or "") else 1, path or "")


def _feeder_catc_header(
    raw_rows: list[dict[str, Any]] | None,
    fibra: str = "23",
) -> dict[str, Any] | None:
    """Cabecera ENTRADA con feeder SF01-CATC-3-000185 (PDF modelo SP1/SP3)."""
    if not raw_rows:
        return None
    from .camino_fusion_export import _attach_color_slugs, _cell, color_grupo_buffer, grupo_para_fila

    for rec in raw_rows:
        da = _cell(rec.get("description_a"))
        if "CATC-3-000185" not in da and "000185" not in da:
            continue
        sub = _cell(rec.get("subcategory_a"))
        fp = fibra
        gi = grupo_para_fila(sub, fp) or "2"
        from .camino_fusion_export import color_desde_numero_fibra

        return _attach_color_slugs(
            {
                "comp_in": da if "CATC" in da else "SF01-CATC-3-000185",
                "grupo_in": gi,
                "color_grupo_in": color_grupo_buffer(sub, gi),
                "fibra_port": fp,
                "color_fibra_port": color_desde_numero_fibra(fp),
            }
        )
    return None


def _header_sp2_modelo() -> dict[str, Any]:
    """Cabecera SP2 como PDF modelo (SF01-R1301-000, fibra 1, AZUL)."""
    from .camino_fusion_export import _attach_color_slugs

    return _attach_color_slugs(
        {
            "comp_in": "SF01-R1301-000",
            "grupo_in": "",
            "color_grupo_in": "",
            "fibra_port": "1",
            "color_fibra_port": "AZUL",
        }
    )


def _pick_header_rec(
    chunk: list[dict[str, Any]],
    sp_idx: int,
    path_in: str,
    circuit_in: str,
    *,
    raw_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fila cabecera ENTRADA del bloque SP (como PDF modelo)."""
    if sp_idx == 1:
        fb = _feeder_catc_header(raw_rows, "23")
        if fb:
            return fb
    if sp_idx == 2 and "010201" in (path_in or ""):
        return _header_sp2_modelo()

    non_out = [
        r
        for r in chunk
        if not _OUT_PORT_RE.match(str(r.get("salida_splitter") or "").upper())
    ]
    pool = non_out or list(chunk)

    if sp_idx == 3:
        for r in pool:
            if "CATC-3-000185" in str(r.get("comp_in") or ""):
                return r
        for r in pool:
            if str(r.get("fibra_port") or "").strip() in ("23", "Fibra 23"):
                return r

    for r in pool:
        sal = str(r.get("salida_splitter") or "").upper()
        if sal == "IN" or str(r.get("fibra_port") or "").strip() in ("23", "Fibra 23"):
            return r
    for r in pool:
        if not _OUT_PORT_RE.match(str(r.get("salida_splitter") or "").upper()):
            return r
    return chunk[0]


def _rama_modelo(rama: str, circuit: str) -> str:
    """Rama como en PDF modelo (SF01-R1291-000)."""
    r = (rama or circuit or "").strip()
    m = re.search(r"-0-0*(\d+)$", r, re.I)
    if m and re.match(r"SF\d+-", r, re.I):
        site = re.match(r"(SF\d+)", r, re.I)
        if site:
            return f"{site.group(1).upper()}-R{int(m.group(1))}-000"
    return r


_FEEDER_CABLE = "SF01-CATC-3-000185"
_TL00_CABLE = "TL00-CATC-0-021031"
_EDN_RAMA = "EDN_CT_VICTORIA_SAN ISIDRO"


def _fila_feeder_edn(f: int) -> dict[str, Any]:
    """Primera fila de fibras 1–4 (feeder CATC + rama EDN en 1 y 3)."""
    from .camino_fusion_export import _attach_color_slugs, color_desde_numero_fibra

    col = color_desde_numero_fibra(str(f))
    return _attach_color_slugs(
        {
            "cable_in": _FEEDER_CABLE,
            "grupo_in": "1",
            "color_grupo_in": "AZUL",
            "fibra_in": str(f),
            "color_fibra_in": col,
            "rama_salida": _EDN_RAMA if f in (1, 3) else "",
            "cable_out": "",
            "grupo_out": "",
            "color_grupo_out": "",
            "fibra_out": "",
            "color_fibra_out": "",
            "destino": "",
        }
    )


def _fila_tl00_edn(f: int, grp: list[dict[str, Any]]) -> dict[str, Any]:
    """Segunda fila fibras 1–4 (TL00 → CATC / FATC como PDF modelo)."""
    from .camino_fusion_export import _attach_color_slugs, color_desde_numero_fibra

    tl00 = next((x for x in grp if _TL00_CABLE in str(x.get("cable_in") or "")), None)
    catc_rev = next(
        (
            x
            for x in grp
            if _FEEDER_CABLE in str(x.get("cable_in") or "")
            and _TL00_CABLE in str(x.get("cable_out") or "")
        ),
        None,
    )
    src = tl00 or catc_rev or (grp[0] if grp else {})
    col = color_desde_numero_fibra(str(f))
    row = _attach_color_slugs(
        {
            "cable_in": _TL00_CABLE,
            "grupo_in": "1",
            "color_grupo_in": "AZUL",
            "fibra_in": f"{f:02d}",
            "color_fibra_in": col,
            "rama_salida": "",
            "cable_out": str(src.get("cable_out") or _FEEDER_CABLE),
            "grupo_out": str(src.get("grupo_out") or "1"),
            "color_grupo_out": str(src.get("color_grupo_out") or "AZUL"),
            "fibra_out": str(src.get("fibra_out") or f"{f:02d}"),
            "color_fibra_out": str(src.get("color_fibra_out") or col),
            "destino": str(src.get("destino") or "SF01-FATC-3-003977"),
            "highlight": src.get("highlight"),
        }
    )
    return row


def _dedupe_cables_modelo(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas cable como PDF modelo (fibras 1–4 en par feeder+TL00; omite 23)."""
    by_f: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        f = _fibra_num(row)
        if f == 23:
            continue
        by_f.setdefault(f, []).append(row)
    out: list[dict[str, Any]] = []
    for f in sorted(by_f.keys()):
        grp = by_f[f]
        if f <= 4:
            out.append(_fila_feeder_edn(f))
            out.append(_fila_tl00_edn(f, grp))
        else:
            out.append(grp[0])
    return out


def _es_1_8(chunk: list[dict[str, Any]]) -> bool:
    for r in chunk:
        if "1:8" in str(r.get("splitter") or ""):
            return True
    return False


def _es_1_2(chunk: list[dict[str, Any]]) -> bool:
    for r in chunk:
        if "1:2" in str(r.get("splitter") or ""):
            return True
    return False


def _spl_from_raw(raw_rows: list[dict[str, Any]], path_in: str, sp_idx: int) -> str:
    """Nombre SPL desde filas crudas (ej. SF010201-SPL1-12-001301-0001)."""
    want = f"SPL{sp_idx}"
    for rec in raw_rows:
        if str(rec.get("physical_path") or "") != path_in:
            continue
        for key in ("component_name_b", "component_name_a"):
            val = str(rec.get(key) or "")
            if want.upper() in val.upper() and "SPL" in val.upper():
                return val
    for rec in raw_rows:
        if str(rec.get("physical_path") or "") != path_in:
            continue
        for key in ("component_name_b", "component_name_a"):
            val = str(rec.get(key) or "")
            if re.search(r"SPL\d", val, re.I):
                return val
    return ""


def _spl_component_name(
    chunk: list[dict[str, Any]],
    *,
    raw_rows: list[dict[str, Any]] | None = None,
    path_in: str = "",
    sp_idx: int = 0,
) -> str:
    for r in chunk:
        for key in ("component_name", "component_name_b", "component_name_a", "comp_out", "comp_in"):
            val = str(r.get(key) or "")
            if re.search(r"SPL\d", val, re.I):
                return val
    if raw_rows and path_in:
        return _spl_from_raw(raw_rows, path_in, sp_idx)
    return ""


def _fila_out_datos(
    r: dict[str, Any],
    fusion_id: str,
    *,
    alias_fosc: str = "",
) -> dict[str, Any]:
    port = str(r.get("salida_splitter") or "")
    desc_b = str(r.get("comp_out") or "")
    dest = destino_splitter(
        fusion_id,
        port,
        desc_b,
        str(r.get("circuit_in") or r.get("path_atc") or ""),
        str(r.get("path_atc") or ""),
        alias_fosc=alias_fosc,
        path_in=str(r.get("path_in") or ""),
    )
    if desc_b and "FATC" in desc_b.upper():
        dest = desc_b
    return _attach_color_slugs(
        {
            "tipo": "out_full",
            "salida_splitter": port,
            "color_salida": r.get("color_salida") or color_desde_puerto_out(port),
            "comp_out": desc_b,
            "grupo_out": r.get("grupo_out") or "",
            "color_grupo_out": r.get("color_grupo_out") or "",
            "fibra_out": r.get("fibra_out") or port,
            "color_fibra_out": r.get("color_fibra_out") or r.get("color_salida") or "",
            "destino": dest,
            "highlight": r.get("highlight"),
            "splitter_text": "",
        }
    )


def _filas_de_chunk_sp(
    chunk: list[dict[str, Any]],
    fusion_id: str,
    path_in: str,
    circuit_in: str,
    sp_label: str,
    *,
    alias_fosc: str = "",
    raw_rows: list[dict[str, Any]] | None = None,
    sp_idx: int = 0,
) -> list[dict[str, Any]]:
    """Filas de un bloque SP como en PDF modelo (sin fila path aparte)."""
    outs: dict[str, dict[str, Any]] = {}
    header_rec = _pick_header_rec(chunk, sp_idx, path_in, circuit_in, raw_rows=raw_rows)

    is_1_8 = _es_1_8(chunk)
    is_1_2 = _es_1_2(chunk)
    spl_name = _spl_component_name(chunk, raw_rows=raw_rows, path_in=path_in, sp_idx=sp_idx)
    close_label = circuit_in if is_1_2 else fusion_id

    for r in chunk:
        sal = str(r.get("salida_splitter") or "").upper()
        if _OUT_PORT_RE.match(sal):
            outs[sal] = r

    filas: list[dict[str, Any]] = [
        _attach_color_slugs(
            {
                "tipo": "header",
                "rowspan_entrada": True,
                "comp_in": header_rec.get("comp_in") or "",
                "grupo_in": header_rec.get("grupo_in") or "",
                "color_grupo_in": header_rec.get("color_grupo_in") or "",
                "fibra_port": header_rec.get("fibra_port") or "",
                "color_fibra_port": header_rec.get("color_fibra_port") or "",
                "splitter_text": sp_label,
                "path_display": path_in,
                "circuit_display": circuit_in,
                "highlight": header_rec.get("highlight"),
            }
        )
    ]

    if is_1_2:
        for n in (1, 2):
            port = f"OUT{n}"
            if port in outs:
                row = _fila_out_datos(outs[port], fusion_id, alias_fosc=alias_fosc)
                if n == 1:
                    row["destino"] = str(outs[port].get("comp_out") or fusion_id)
                if n == 2:
                    row["tipo"] = "out_only"
            else:
                sal = port
                row = _attach_color_slugs(
                    {
                        "tipo": "out_only",
                        "salida_splitter": sal,
                        "color_salida": _OUT_PAD_58.get(n) or color_desde_puerto_out(sal),
                        "splitter_text": "",
                    }
                )
            row["splitter_text"] = _splitter_bracket_text(
                n, 2, True, False, spl_name, close_label
            )
            filas.append(row)
        return filas

    ordered_ports = sorted(
        outs.keys(),
        key=lambda p: int(_OUT_PORT_RE.match(p).group(1)),  # type: ignore[union-attr]
    )
    last_full_idx = max(
        (int(_OUT_PORT_RE.match(p).group(1)) for p in ordered_ports),  # type: ignore[union-attr]
        default=0,
    )

    for port in ordered_ports:
        out_n = int(_OUT_PORT_RE.match(port).group(1))  # type: ignore[union-attr]
        row = _fila_out_datos(outs[port], fusion_id, alias_fosc=alias_fosc)
        row["splitter_text"] = _splitter_bracket_text(
            out_n, last_full_idx, False, is_1_8, spl_name, close_label
        )
        filas.append(row)

    if is_1_8:
        present = {int(_OUT_PORT_RE.match(p).group(1)) for p in ordered_ports}  # type: ignore[union-attr]
        for n in range(1, 9):
            if n in present:
                continue
            sal = f"OUT{n}"
            filas.append(
                _attach_color_slugs(
                    {
                        "tipo": "out_only",
                        "salida_splitter": sal,
                        "color_salida": _OUT_PAD_58.get(n) or color_desde_puerto_out(sal),
                        "splitter_text": _splitter_bracket_text(
                            n, last_full_idx, False, True, spl_name, close_label, padded=True
                        ),
                    }
                )
            )

    return filas


def _extraer_splitter_cierre(
    filas: list[dict[str, Any]],
    sp_label: str,
    fusion_id: str,
) -> str:
    """Texto de cierre en columna SPLITTER (p. ej. ``SF01-R1078-010 ]``)."""
    for row in filas:
        t = str(row.get("splitter_text") or "").strip()
        if not t or t == sp_label or _SP_LABEL_RE.match(t):
            continue
        if t.endswith("]") and "SPLITTER" not in t.upper():
            return t
    return ""


def _meta_merge_sp_block(
    filas: list[dict[str, Any]],
    sp_label: str,
    fusion_id: str,
) -> dict[str, Any]:
    """
    Detecta bloques donde la etiqueta SP y el cierre de fusión pueden unirse (rowspan + centro).
    """
    n = len(filas)
    sp_label = (sp_label or "").strip()
    if n < 2 or not _SP_LABEL_RE.match(sp_label):
        return {"splitter_merge": False}

    close = _extraer_splitter_cierre(filas, sp_label, fusion_id)
    for row in filas:
        row["splitter_text"] = ""

    return {
        "splitter_merge": True,
        "splitter_main": sp_label,
        "splitter_close": close,
    }


def _splitter_bracket_text(
    out_idx: int,
    last_full: int,
    is_1_2: bool,
    is_1_8: bool,
    spl_name: str,
    close_label: str,
    *,
    padded: bool = False,
) -> str:
    """Texto auxiliar en columna SPLITTER ([ nombre SPL ]), como PDF modelo."""
    if is_1_2:
        if out_idx == 1 and spl_name:
            return f"{spl_name} ["
        if out_idx == 2 and close_label:
            return f"{close_label} ]"
        return ""

    if is_1_8 and spl_name:
        if not padded and out_idx == last_full:
            if last_full == 4:
                return f"{spl_name} [ ]"
            return f"{spl_name} ["
        if padded and out_idx == last_full + 1 and close_label:
            return f"{close_label} ]"
    return ""


def construir_secciones_splitter_bentley(
    splitter_rows: list[dict[str, Any]],
    fusion_id: str,
    *,
    alias_fosc: str = "",
    raw_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Bloques SP con filas header + OUT (como PDF modelo)."""
    by_path: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in splitter_rows:
        key = (str(row.get("path_in") or ""), str(row.get("circuit_in") or ""))
        by_path.setdefault(key, []).append(row)

    sections: list[dict[str, Any]] = []
    all_blocks: list[dict[str, Any]] = []
    sp_idx = 0

    for key in sorted(by_path.keys(), key=lambda k: (_path_sort_key(k[0]), k[1])):
        path, circuit = key
        chunk_all = by_path[key]
        by_sp: dict[str, list[dict[str, Any]]] = {}
        for r in chunk_all:
            by_sp.setdefault(str(r.get("splitter") or ""), []).append(r)

        for sp_key in sorted(by_sp.keys(), key=lambda s: (0 if "1:2" in s else 1, s)):
            chunk = by_sp[sp_key]
            if not chunk:
                continue
            sp_idx += 1
            filas = _filas_de_chunk_sp(
                chunk,
                fusion_id,
                path,
                circuit,
                _splitter_sp_label(chunk[0], sp_idx, path),
                alias_fosc=alias_fosc,
                raw_rows=raw_rows,
                sp_idx=sp_idx,
            )
            if len(filas) <= 1:
                continue
            sp_label = str(filas[0].get("splitter_text") or "")
            merge_meta = _meta_merge_sp_block(filas, sp_label, fusion_id)
            all_blocks.append(
                {
                    "sp_idx": sp_idx,
                    "path_in": path,
                    "circuit_in": circuit,
                    "sp_label": sp_label,
                    "rows": filas,
                    **merge_meta,
                }
            )

    # PDF modelo: SP1, SP2, SP3 en orden
    for blk in sorted(all_blocks, key=lambda b: b["sp_idx"]):
        sections.append(
            {
                "path_in": blk["path_in"],
                "circuit_in": blk["circuit_in"],
                "sp_blocks": [
                    {
                        "sp_label": blk["sp_label"],
                        "rows": blk["rows"],
                        "splitter_merge": blk.get("splitter_merge", False),
                        "splitter_main": blk.get("splitter_main", ""),
                        "splitter_close": blk.get("splitter_close", ""),
                    }
                ],
            }
        )

    return sections


def _fibra_num(row: dict[str, Any]) -> int:
    m = _FIBRA_NUM_RE.search(str(row.get("fibra_in") or ""))
    return int(m.group(1)) if m else 9999


def construir_secuencia_cables_bentley(
    cable_rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    fusion_id: str,
    *,
    alias_fosc: str = "",
) -> dict[str, list[dict[str, Any]]]:
    """Cables ordenados en una sola hoja (visualización continua)."""
    del raw_rows, fusion_id, alias_fosc

    rows = _dedupe_cables_modelo(list(cable_rows))
    rows.sort(
        key=lambda r: (
            _fibra_num(r),
            0 if "EDN" in str(r.get("rama_salida") or "").upper() else 1,
            str(r.get("rama_salida") or ""),
        )
    )

    page1: list[dict[str, Any]] = []
    for row in rows:
        r = dict(row)
        r["kind"] = "cable"
        fibra_n = _fibra_num(r)
        r["rama_salida"] = _rama_modelo(
            str(r.get("rama_salida") or ""), str(r.get("circuit") or "")
        )
        if fibra_n == 24:
            r["destino"] = "SF01-R1300-010"
        page1.append(r)
    return {"page1": page1, "page2": []}


def construir_layout_bentley(
    header: dict[str, Any],
    splitter_rows: list[dict[str, Any]],
    cable_rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    fusion_id: str,
    *,
    alias_fosc: str = "",
    rama: str | None = None,
) -> dict[str, Any]:
    return {
        "header": header,
        "rama": rama,
        "fusion_id": fusion_id,
        "splitter_sections": construir_secciones_splitter_bentley(
            splitter_rows, fusion_id, alias_fosc=alias_fosc, raw_rows=raw_rows
        ),
        "cable_render": construir_secuencia_cables_bentley(
            cable_rows, raw_rows, fusion_id, alias_fosc=alias_fosc
        ),
    }
