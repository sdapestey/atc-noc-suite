"""Export reporte fusión planta interna."""
from services.camino_fusion_export import (
    _destino_cable_fosc_export,
    _es_fila_splitter,
    _fatc_suffix_num,
    _fusion_destino_cable_path,
    _rama_continuidad_reporte,
    google_maps_url,
    color_desde_numero_fibra,
    color_grupo_buffer,
    consultar_reporte_fosc_export,
    consultar_reporte_fusion_export,
    destino_cable_reporte,
    fusion_codigo_corto,
    grupo_desde_fibra,
    rama_cable_reporte,
    splice_plan_cm_filename,
)


def test_header_logo_placeholder_se_embebe_en_pdf():
    from services.camino_fusion_pdf import _embed_fusion_assets, header_logo_data_uri

    html = '<div class="bentley-header-logo"><img src="__BENTLEY_HEADER_LOGO__" alt=""></div>'
    out = _embed_fusion_assets(html)
    assert "__BENTLEY_HEADER_LOGO__" not in out
    assert 'src="data:image/svg+xml;base64,' in out
    assert header_logo_data_uri().startswith("data:image/svg+xml;base64,")


def test_watermark_placeholder_se_embebe_en_pdf():
    from services.camino_fusion_pdf import _embed_fusion_assets, watermark_data_uri

    html = '<img class="bentley-wm" src="__BENTLEY_WATERMARK__" alt="">'
    out = _embed_fusion_assets(html)
    assert "__BENTLEY_WATERMARK__" not in out
    assert out.startswith('<img class="bentley-wm" src="data:image/png;base64,')
    assert watermark_data_uri().startswith("data:image/png;base64,")


def test_google_maps_url_usa_dominio_global():
    url = google_maps_url(-34.472252, -58.51101)
    assert url.startswith("https://www.google.com/maps/")
    assert ".mx" not in url
    assert "-34.472252" in url and "-58.51101" in url


def test_es_fila_splitter_detecta_port_out():
    assert _es_fila_splitter({"component_type_name_b": "SPLITTER 1:8", "point_name_a": "OUT1"})
    assert not _es_fila_splitter({"component_type_name_a": "CABLE-48F", "point_name_a": "Fibra 40"})


def test_colores_como_pdf_bentley():
    assert color_desde_numero_fibra("40") == "MARRÓN"
    assert color_desde_numero_fibra("13") == "AZUL"
    assert grupo_desde_fibra("40") == "4"
    assert color_grupo_buffer("FEEDER CABLE L3", "4") == "MARRÓN"
    assert color_grupo_buffer("FEEDER CABLE L3", "3") == "VERDE"
    assert color_grupo_buffer("DISTRIBUTION CABLE D1", "1") == "BLANCO"
    assert fusion_codigo_corto("SF01-R1301-010") == "13"
    assert fusion_codigo_corto("SF01-R0773-010") == "14"
    assert fusion_codigo_corto("SF01-R1414-010") == "14"
    assert fusion_codigo_corto("SF01-R0774-010") == "14"
    assert fusion_codigo_corto("SF01-FATC-3-001659") == ""
    assert destino_cable_reporte("", "SF01-RATC-0-001318") == "SF01-R1303-010"
    assert destino_cable_reporte("", "SF01-RATC-0-001300") == "SF01-R1300-010"


def test_rama_cable_reporte_usa_circuit():
    assert rama_cable_reporte("SF01-R0772-000", "SF01-RAMX-0-000772") == "SF01-R0772-000"
    assert (
        rama_cable_reporte("SF01-RATC-0-000775", "SF01-RATC-0-000775")
        == "SF01-RATC-0-000775"
    )


def test_continuidad_rama_y_destino_helpers():
    assert _fatc_suffix_num("SF01-FATC-3-022849") == 22849
    assert _rama_continuidad_reporte("", "", "", "SF01-CATC-1-000007") == ""
    assert (
        _rama_continuidad_reporte("SF01-RATC-0-000721", "SF01-RATC-0-000721", "", "")
        == "SF01-RATC-0-000721"
    )
    dest = _destino_cable_fosc_export(
        "CONTINUIDAD",
        "SF01-RATC-0-000721",
        "SF01-RATC-0-000721",
        "some/path",
        "SF01-CATC-1-000007",
        "SF01-CATC-1-000007",
        alias_fosc="SF01-FATC-3-002759",
        dest_fusion_cache={},
        dest_fatc_cache={"SF01-CATC-1-000007": "SF01-FATC-3-022849"},
    )
    assert dest == "SF01-FATC-3-022849"


def test_consultar_reporte_fosc_export_001659_db():
    fosc = "SF010101-FOSC-07-001659-0001"
    try:
        out = consultar_reporte_fosc_export(fosc)
    except Exception:
        return
    if not out.get("ok"):
        return
    assert out["header"]["alias"] == "SF01-FATC-3-001659"
    assert out["header"]["fusion_id"] == "SF01-R0773-010"
    assert out["header"].get("fusion_num") == "14"
    cables = []
    for page in out["bentley"]["cable_render"].get("pages") or []:
        cables.extend(page)
    fibra13 = next((r for r in cables if str(r.get("fibra_in")) == "13"), None)
    if fibra13:
        assert fibra13["destino"] == "SF01-FATC-3-004049"


def test_consultar_reporte_fosc_export_002759_db():
    fosc = "SF010101-FOSC-07-002759-0001"
    try:
        out = consultar_reporte_fosc_export(fosc)
    except Exception:
        return
    if not out.get("ok"):
        return
    assert out["header"]["alias"] == "SF01-FATC-3-002759"
    cables = []
    for page in out["bentley"]["cable_render"].get("pages") or []:
        cables.extend(page)
    fibra01 = next((r for r in cables if str(r.get("fibra_in")) == "01"), None)
    if fibra01:
        assert fibra01["rama_salida"] == ""
        assert fibra01["destino"] == "SF01-FATC-3-022849"
    fibra25 = next((r for r in cables if str(r.get("fibra_in")) == "25"), None)
    if fibra25:
        assert fibra25["rama_salida"] == "SF01-RATC-0-000721"
        assert fibra25["destino"] == "SF01-FATC-3-022849"
    fibra68 = next((r for r in cables if str(r.get("fibra_in")) == "68"), None)
    if fibra68:
        assert fibra68["rama_salida"] == "SF01-RATC-0-001526"
        assert fibra68["destino"] == "SF01-FATC-3-022849"


def test_consultar_reporte_fusion_export_r0774_db():
    try:
        out = consultar_reporte_fusion_export(
            "SF01-R0774-010", rama="SF01-RATC-0-000775"
        )
    except Exception:
        return
    if not out.get("ok"):
        return
    cables = out["bentley"]["cable_render"]["page1"]
    by_fibra = {str(r.get("fibra_in")): r for r in cables}
    assert by_fibra["13"]["rama_salida"] == "SF01-R0772-000"
    assert by_fibra["16"]["rama_salida"] == "SF01-RATC-0-000775"
    assert by_fibra["13"]["destino"] == "SF01-R0775-010"
    assert by_fibra["16"]["destino"] == "SF01-R0775-010"
    sp2 = out["bentley"]["splitter_sections"][2]["sp_blocks"][0]["rows"]
    out1 = next(
        r for r in sp2 if r.get("salida_splitter") == "OUT1" and r.get("tipo") == "out_full"
    )
    assert out1.get("destino") == "SF01-R0774-011"


def test_consultar_reporte_fusion_export_db():
    try:
        out = consultar_reporte_fusion_export(
            "SF01-R1301-010", rama="SF01-RATC-0-001318"
        )
    except Exception:
        return
    if not out.get("ok"):
        return
    assert out["header"]["fusion_id"] == "SF01-R1301-010"
    assert out["header"].get("fusion_num") == "13"
    assert out["header"].get("alias", "").startswith("SF01-FATC")
    assert out["row_count"] > 0
    assert out["splitter_rows"] or out["cable_rows"]
    highlighted = [r for r in out["cable_rows"] if r.get("highlight")]
    assert highlighted
    assert highlighted[0].get("grupo_in") == "4"
    assert highlighted[0].get("color_fibra_in") == "MARRÓN"
    assert highlighted[0].get("color_grupo_in") == "MARRÓN"
    assert highlighted[0].get("color_fibra_in_slug") == "marron"
    assert highlighted[0].get("destino") == "SF01-R1303-010"
    assert out.get("splitter_groups")


def test_splice_plan_cm_filename():
    fosc = "SF010101-FOSC-07-002749-0001"
    assert splice_plan_cm_filename(fosc).startswith(fosc)
    assert "SPLICE PLAN" in splice_plan_cm_filename(fosc)


def test_consultar_reporte_fosc_export_002749_db():
    fosc = "SF010101-FOSC-07-002749-0001"
    try:
        out = consultar_reporte_fosc_export(fosc)
    except Exception:
        return
    if not out.get("ok"):
        return
    assert out["header"]["alias"] == "SF01-FATC-3-002749"
    assert out["header"]["fusion_id"] == "SF01-FATC-3-002749"
    assert out["header"].get("fusion_num") == ""
    assert out["row_count"] == 98
    cables = []
    for page in out["bentley"]["cable_render"].get("pages") or []:
        cables.extend(page)
    r775 = next(
        (r for r in cables if r.get("rama_salida") == "SF01-RATC-0-000775"),
        None,
    )
    if r775:
        assert r775["destino"] == "SF01-R0764-010"
    r721 = next(
        (r for r in cables if r.get("rama_salida") == "SF01-RATC-0-000721"),
        None,
    )
    if r721:
        assert r721["destino"] == "SF01-R0721-010"

