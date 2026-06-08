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


def test_cables_en_una_sola_hoja():
    rows = [
        {"fibra_in": "10", "rama_salida": "x"},
        {"fibra_in": "40", "rama_salida": "y"},
    ]
    out = construir_secuencia_cables_bentley(rows, [], "SF01-R1301-010")
    assert len(out["page1"]) == 2
    assert out["page2"] == []


def test_extraer_splitter_cierre():
    filas = [{"splitter_text": "[ SP5 ] SPLITTER 1:8 [ ATC ]"}, {"splitter_text": "SF01-R1078-010 ]"}]
    assert _extraer_splitter_cierre(filas, filas[0]["splitter_text"], "SF01-R1078-010") == "SF01-R1078-010 ]"
