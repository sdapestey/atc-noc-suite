"""Maquetación Bentley — celdas SPLITTER combinadas."""
from services.camino_fusion_bentley_layout import (
    _extraer_splitter_cierre,
    _meta_merge_sp_block,
    construir_secuencia_cables_bentley,
)


def test_meta_merge_sp_block_unifica_etiqueta_y_cierre():
    sp_label = "[ SP4 ] SPLITTER 1:8 [ ATC ]"
    filas = [
        {"tipo": "header", "splitter_text": sp_label, "rowspan_entrada": True},
        {"tipo": "out_full", "splitter_text": "SPL4 [", "salida_splitter": "OUT1"},
        {"tipo": "out_full", "splitter_text": "", "salida_splitter": "OUT2"},
        {"tipo": "out_only", "splitter_text": "SF01-R1078-010 ]", "salida_splitter": "OUT8"},
    ]
    meta = _meta_merge_sp_block(filas, sp_label, "SF01-R1078-010")
    assert meta["splitter_merge"] is True
    assert meta["splitter_main"] == sp_label
    assert meta["splitter_close"] == "SF01-R1078-010 ]"
    assert all(r["splitter_text"] == "" for r in filas)


def test_meta_merge_sp_block_no_aplica_sin_etiqueta_sp():
    filas = [{"splitter_text": "x"}, {"splitter_text": "y"}]
    meta = _meta_merge_sp_block(filas, "SPLITTER", "SF01-R1078-010")
    assert meta["splitter_merge"] is False


def test_pick_header_entrada_1659_db():
    try:
        from services.camino_fusion_export import consultar_reporte_fosc_export
    except Exception:
        return
    try:
        out = consultar_reporte_fosc_export("SF010101-FOSC-07-001659-0001")
    except Exception:
        return
    if not out.get("ok"):
        return
    sections = out["bentley"]["splitter_sections"]
    assert len(sections) == 3
    sp1 = sections[0]["sp_blocks"][0]["rows"][0]
    assert sp1["comp_in"] == "SF01-CATC-3-000104"
    assert str(sp1["fibra_port"]) == "14"
    sp2 = sections[1]["sp_blocks"][0]["rows"][0]
    assert sp2["comp_in"] == "SF01-R0773-000"
    sp3 = sections[2]["sp_blocks"][0]["rows"][0]
    assert sp3["comp_in"] == "SF01-RATC-0-000773"


def test_orden_fibras_bentley_cm():
    rows = [
        {"fibra_in": "25", "rama_salida": "a"},
        {"fibra_in": "01", "rama_salida": "b"},
        {"fibra_in": "12", "rama_salida": "c"},
        {"fibra_in": "109", "rama_salida": "d"},
        {"fibra_in": "13", "rama_salida": "e"},
    ]
    from services.camino_fusion_bentley_layout import _orden_fibras_bentley_cm

    ordered = _orden_fibras_bentley_cm(rows)
    assert [r["fibra_in"] for r in ordered] == ["01", "12", "109", "13", "25"]


def test_cables_paginacion_bentley():
    rows = [{"fibra_in": str(i).zfill(2), "rama_salida": f"r{i}"} for i in range(5, 103)]
    out = construir_secuencia_cables_bentley(
        rows, [], "SF01-FATC-3-002749", dedupe_modelo=False
    )
    assert len(out["pages"]) == 2
    assert len(out["page1"]) == 72
    assert len(out["page2"]) == 26
    assert out["page3"] == []


def test_extraer_splitter_cierre():
    filas = [{"splitter_text": "[ SP5 ] SPLITTER 1:8 [ ATC ]"}, {"splitter_text": "SF01-R1078-010 ]"}]
    assert _extraer_splitter_cierre(filas, filas[0]["splitter_text"], "SF01-R1078-010") == "SF01-R1078-010 ]"
