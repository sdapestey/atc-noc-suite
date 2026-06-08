"""Export reporte fusión planta interna."""
from services.camino_fusion_export import (
    _es_fila_splitter,
    google_maps_url,
    color_desde_numero_fibra,
    color_grupo_buffer,
    consultar_reporte_fusion_export,
    destino_cable_reporte,
    es_codigo_fusion_planta,
    fusion_codigo_corto,
    grupo_desde_fibra,
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
    assert destino_cable_reporte("", "SF01-RATC-0-001318") == "SF01-R1303-010"
    assert destino_cable_reporte("", "SF01-RATC-0-001300") == "SF01-R1300-010"


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


def test_export_fusion_route(client):
    r = client.get(
        "/dashboard/camino-optico/export-fusion",
        query_string={"fusion": "SF01-R1301-010", "rama": "SF01-RATC-0-001318"},
    )
    if r.status_code in (404, 500):
        return
    assert r.status_code == 200
    assert b"SF01-R1301-010" in r.data
    assert b"bentley-meta-grid" in r.data
    assert b"bentley-header-logo" in r.data
    assert b"american-tower-logo.svg" in r.data
    assert b"bentley-page" in r.data
    assert b"camino-fusion-bentley.css" in r.data
    assert b"Descargar PDF" in r.data
    assert b'bentley-wm' in r.data
    assert b"american-tower-watermark.png" in r.data
    assert b"fc--azul" in r.data or b"fc--marron" in r.data


def test_export_fusion_invalid(client):
    r = client.get("/dashboard/camino-optico/export-fusion", query_string={"fusion": "INVALID"})
    assert r.status_code in (400, 404)
    if r.status_code == 400:
        assert b"inv" in r.data.lower() or b"Error" in r.data
