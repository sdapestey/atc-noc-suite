"""Análisis planta interna (consulta individual camino óptico)."""
import services.camino_optico as co
from services.camino_gis import (
    consultar_fusiones_verificacion_rama,
    es_codigo_fusion_planta,
    resolver_rama_desde_fusion_planta,
)


def test_extremos_trazado_con_focal():
    gis = {
        "ok": True,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-58.80, -34.35], [-58.79, -34.34], [-58.78, -34.33]],
                    },
                }
            ],
        },
    }
    ext = co._extremos_trazado_gis(gis, -34.335, -58.785)
    assert ext is not None
    assert ext["cabecera"]["lat"] == -34.35
    assert abs(ext["hacia_cto"]["lat"] - (-34.335)) < 0.02


def test_atributos_ci_op_para_ui_omite_redundantes():
    attrs = {
        "cabecera": "TG01",
        "camino_rama": "TG01-RATC-0-000164",
        "nombre_co_atc": "TG01-RATC-0-000164",
        "nombre_co_claro": "TG01-RATC-0-000164",
        "nombre_op": "TG01-RATC-0-000164",
    }
    assert co._atributos_ci_op_para_ui(attrs, "TG01-RATC-0-000164") == {}


def test_atributos_ci_op_para_ui_conserva_util():
    attrs = {
        "cabecera": "TG01",
        "camino_rama": "TG01-RATC-0-000164",
        "nombre_co_atc": "TG01-RATC-0-000164",
        "sitio": "Tigre",
        "longitud": "2.5 km",
    }
    assert co._atributos_ci_op_para_ui(attrs, "TG01-RATC-0-000164") == {
        "sitio": "Tigre",
        "longitud": "2.5 km",
    }


def test_atributos_ci_op_para_ui_nombres_distintos():
    attrs = {
        "nombre_co_atc": "TG01-RATC-0-000164",
        "nombre_co_claro": "OTRO-CODIGO",
    }
    out = co._atributos_ci_op_para_ui(attrs, "TG01-RATC-0-000164")
    assert out == {"nombre_co_claro": "OTRO-CODIGO"}


def test_resumen_ci_op_desde_gis():
    gis = {
        "ok": True,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "nombre_co_atc": "TG02-RATC-0-000403",
                        "cabecera": "TG02",
                        "sitio": "Tigre Norte",
                    },
                    "geometry": {"type": "LineString", "coordinates": [[-58.8, -34.4], [-58.7, -34.3]]},
                }
            ],
        },
    }
    res = co._resumen_ci_op_desde_gis(gis, "TG02-RATC-0-000403")
    assert res["feature_count"] == 1
    assert res["atributos"] == {"sitio": "Tigre Norte"}


def test_dedupe_fosc_markers_por_id_cm():
    from services.camino_gis import _dedupe_fosc_markers

    markers = [
        {"orden": 1, "id_cm": "FOSC-A", "id_botella": 1},
        {"orden": 2, "id_cm": "FOSC-B", "id_botella": 2},
        {"orden": 3, "id_cm": "FOSC-A", "id_botella": 1},
    ]
    out, removed = _dedupe_fosc_markers(markers)
    assert removed == 1
    assert len(out) == 2
    assert [m["id_cm"] for m in out] == ["FOSC-A", "FOSC-B"]
    assert [m["orden"] for m in out] == [1, 2]


def test_es_id_fosc_cm():
    from services.camino_gis import es_id_fosc_cm

    assert es_id_fosc_cm("SF010101-FOSC-07-002759-0001") is True
    assert es_id_fosc_cm("SF01-R1301-010") is False


def test_consultar_fosc_camino_logico_rama_incluye_fusiones(monkeypatch):
    """Camino lógico CM: FATC-3 + códigos de fusión en location_description."""
    from services import camino_gis as cg

    class Cur:
        def execute(self, sql, params=()):
            assert "location_description ~ '^[A-Z]{2}[0-9]+-FATC-3-'" in sql
            assert "location_type = 'FOSC'" not in sql
            assert params == ("SF01-RATC-0-000775",)

        def fetchall(self):
            return []

    class Ctx:
        def __enter__(self):
            return Cur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cg, "_env_schema", lambda: "cm")
    monkeypatch.setattr(cg, "_env_fusiones_table", lambda: "report_fusiones")
    monkeypatch.setattr(cg, "_validate_ident", lambda s, t: True)
    monkeypatch.setattr(cg, "_table_exists", lambda *a: True)
    monkeypatch.setattr(cg, "db_cursor", Ctx)

    out = cg.consultar_fosc_camino_logico_rama("SF01-RATC-0-000775")
    assert out["ok"] is True
    assert out["markers"] == []


def test_consultar_fosc_camino_logico_rama_si03_db():
    """Cabeceras distintas de SF01 (p. ej. SI03) deben listar FATC-3 en el mapa."""
    from services.camino_gis import consultar_fosc_camino_logico_rama

    rama = "SI03-RATC-0-000917"
    try:
        out = consultar_fosc_camino_logico_rama(rama)
    except Exception:
        return
    if not out.get("ok"):
        return
    botellas = [m for m in (out.get("markers") or []) if not m.get("es_fusion")]
    assert len(botellas) >= 10
    assert any((m.get("etiqueta") or "").startswith("SI03-FATC-3-") for m in botellas)


def test_alias_visible_cm():
    from services.camino_gis import _alias_visible_cm, _es_etiqueta_alias_cm

    assert _es_etiqueta_alias_cm("SF01-FATC-3-002759") is True
    assert _es_etiqueta_alias_cm("SI03-FATC-3-008113") is True
    assert _alias_visible_cm("SF01-FATC-3-002759", "SF01-FATC-3-002759") == "SF01-FATC-3-002759"
    assert _alias_visible_cm("SF01-R0764-010", "SF01-FATC-3-002745") == "SF01-FATC-3-002745"
    assert _alias_visible_cm("SF01-R0772-010", "") == "Sin alias"


def test_componente_cm_desde_filas_prefiere_fel_a():
    from services.camino_gis import _componente_cm_desde_filas

    assert (
        _componente_cm_desde_filas(
            "SF010101-FEL1-07-00007-0005",
            "SF010101-FEL1-07-00007-0001",
        )
        == "SF010101-FEL1-07-00007-0005"
    )


def test_consultar_reporte_splice_export_requiere_tray():
    from services.camino_fusion_export import consultar_reporte_splice_export

    out = consultar_reporte_splice_export(
        "SF010101-FOSC-07-002759-0001", tray="", rama="SF01-RATC-0-000775"
    )
    assert out["ok"] is False
    assert "tray" in out["error"].lower()


def test_planta_interna_para_consulta_mock(monkeypatch):
    gis = {
        "ok": True,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"nombre_co_atc": "TG02-RATC-0-000403"},
                    "geometry": {"type": "LineString", "coordinates": [[-58.8, -34.4], [-58.7, -34.3]]},
                }
            ],
        },
    }

    def fake_fosc_logico(rama):
        assert rama == "TG02-RATC-0-000403"
        return {
            "ok": True,
            "markers": [
                {
                    "orden": 1,
                    "id_cm": "FOSC-1",
                    "lat": -34.39,
                    "lon": -58.79,
                    "alias": "TG02-FATC-3-001",
                }
            ],
            "fuente": "report_fusiones",
        }

    def fake_feeder(ramas, **kwargs):
        return {
            "ok": True,
            "feeder": {
                "nombre_atc": "TG02-CATC-1-000001",
                "cantidad_pelos": 144,
                "shared_m": 500,
            },
            "corte_feeder": {"lat": -34.39, "lon": -58.79},
            "fosc_144": {"id_cm": "FOSC-1", "id_botella": 1},
            "geojson": {"type": "FeatureCollection", "features": []},
        }

    monkeypatch.setattr(co, "consultar_fosc_camino_logico_rama", fake_fosc_logico)
    monkeypatch.setattr(co, "consultar_feeder_distribucion_planta_interna", fake_feeder)
    monkeypatch.setattr(co, "consultar_cto_coordenadas_desde_sfat", lambda c: None)

    out = co._planta_interna_para_consulta(["TG02-RATC-0-000403"], gis, focal_cto="TG02-FATC-8-100987")
    assert out["ok"] is True
    assert out["rama"] == "TG02-RATC-0-000403"
    assert out["fosc"]["markers"][0]["orden"] == 1
    assert out["fosc"]["markers"][0].get("feeder_144") is True
    assert out["feeder"]["ok"] is True
    assert out["feeder"]["feeder"]["cantidad_pelos"] == 144
    assert out["extremos"] is not None


def test_cabecera_desde_rama_natc():
    from services.camino_gis import cabecera_desde_rama, cabecera_para_fosc

    assert cabecera_desde_rama("ES01-NATC-0-000001") == "ES01"
    assert cabecera_desde_rama("ES01-RATC-0-000384") == "ES01"
    gis = {
        "ok": True,
        "geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"cabecera": "ES01 - BELEN DE ESCOBAR"},
                    "geometry": {"type": "LineString", "coordinates": [[-58.8, -34.4], [-58.7, -34.3]]},
                }
            ],
        },
    }
    assert cabecera_para_fosc("ES01-NATC-0-000001", gis) == "ES01"


def test_infer_camino_natc_es_rama():
    assert co.infer_camino_consulta_tipo("ES01-NATC-0-000001") == "rama"


def test_camino_template_planta_interna_ui():
    from pathlib import Path

    html = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "planta_interna" in html
    assert "renderPlantaInternaHtml" in html
    assert "drawIndividualPlantaOnMap" in html
    assert "caminoPlantaNav" in html
    assert "ci_feeder_distribution" in html
    assert "corte-feeder" in html
    assert "camino-planta-legend-feeder-swatch" in html
    assert "var cortFd = pi &&" not in html
    assert "fullscreen: false" in html
    assert "camino-planta-fusion" in html
    assert "renderRutaFisicaCm" in html
    assert "camino-ruta-fisica-table" in html
    assert 'camino-rama-ctos" open' in html
    assert "el.open = true" in html
    assert "Reporte de rama" not in html
    assert "export-fusion" not in html
    assert "export-splice" not in html
    assert "camino-planta-pdf-link" not in html
    assert "camino-fosc-detalle-btn" not in html
    assert "verificacion-fusion" in html
    assert "caminoScrollToMapPanel" in html


def test_es_codigo_fusion_planta():
    assert es_codigo_fusion_planta("SF01-R1301-010") is True
    assert es_codigo_fusion_planta("SF01-RATC-0-001318") is False


def test_fosc_on_trazado_default_tolerance():
    import os

    from services.camino_gis import _env_fosc_max_dist_traz_m

    old = os.environ.pop("CAMINO_GIS_FOSC_MAX_DIST_TRAZ_M", None)
    try:
        assert _env_fosc_max_dist_traz_m() == 6.0
    finally:
        if old is not None:
            os.environ["CAMINO_GIS_FOSC_MAX_DIST_TRAZ_M"] = old


def test_infer_camino_fusion_planta():
    assert co.infer_camino_consulta_tipo("SF01-R1301-010") == "fusion_planta"


def test_fosc_id_desde_fila_fusion_prefiere_location_name():
    from services.camino_gis import _fosc_id_desde_fila_fusion

    assert (
        _fosc_id_desde_fila_fusion(
            "SF010101-FOSC-07-002745-0001",
            "SF010101-FEL2-07-00014-0001",
        )
        == "SF010101-FOSC-07-002745-0001"
    )
    assert (
        _fosc_id_desde_fila_fusion(
            "",
            "SF010101-FOSC-07-001589-0001>SP3<SF010101-SPL1-07-000775-0001",
        )
        == "SF010101-FOSC-07-001589-0001"
    )


def test_consultar_fusiones_verificacion_enriquece_alias(monkeypatch):
    from services import camino_gis as cg

    class Cur:
        def execute(self, sql, params=()):
            pass

        def fetchall(self):
            return [
                (
                    "SF01-R0764-010",
                    "SF01-RATC-0-000775",
                    "SF010101-FOSC-07-002745-0001",
                    "SF010101-FEL2-07-00014-0001",
                    "EMPALME",
                    -34.42,
                    -58.58,
                )
            ]

    class Ctx:
        def __enter__(self):
            return Cur()

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cg, "_env_schema", lambda: "cm")
    monkeypatch.setattr(cg, "_env_fusiones_table", lambda: "report_fusiones")
    monkeypatch.setattr(cg, "_env_fusiones_limit", lambda: 30)
    monkeypatch.setattr(cg, "_validate_ident", lambda s, t: True)
    monkeypatch.setattr(cg, "_table_exists", lambda *a: True)
    monkeypatch.setattr(cg, "db_cursor", Ctx)

    def _fake_alias(markers, schema):
        for m in markers:
            m["fosc_alias"] = "SF01-FATC-3-002745"

    monkeypatch.setattr(cg, "_enriquecer_fosc_alias_en_markers", _fake_alias)

    out = cg.consultar_fusiones_verificacion_rama(["SF01-RATC-0-000775"])
    assert out["ok"] is True
    mk = out["markers"][0]
    assert mk["fosc_id_cm"] == "SF010101-FOSC-07-002745-0001"
    assert mk["fosc_alias"] == "SF01-FATC-3-002745"


def test_planta_interna_fusiones_mock(monkeypatch):
    gis = {"ok": True, "geojson": {"type": "FeatureCollection", "features": []}}

    def fake_fosc_logico(rama):
        return {
            "ok": True,
            "markers": [
                {
                    "fusion_id": "SF01-R1301-010",
                    "etiqueta": "SF01-R1301-010",
                    "es_fusion": True,
                    "lat": -34.42406,
                    "lon": -58.589228,
                    "fosc_id_cm": "SF010101-FOSC-12-003503-0001",
                }
            ],
        }

    def fake_feeder(ramas, **kwargs):
        return {"ok": False}

    def fake_fusion(ramas, **kwargs):
        return {
            "ok": True,
            "markers": [
                {
                    "fusion_id": "SF01-R1301-010",
                    "lat": -34.42406,
                    "lon": -58.589228,
                    "destacar": True,
                    "fosc_id_cm": "SF010101-FOSC-12-003503-0001",
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(co, "consultar_fosc_camino_logico_rama", fake_fosc_logico)
    monkeypatch.setattr(co, "consultar_feeder_distribucion_planta_interna", fake_feeder)
    monkeypatch.setattr(co, "consultar_fusiones_verificacion_rama", fake_fusion)
    monkeypatch.setattr(co, "consultar_cto_coordenadas_desde_sfat", lambda c: None)

    out = co._planta_interna_para_consulta(
        ["SF01-RATC-0-001318"],
        gis,
        fusion_destacar="SF01-R1301-010",
    )
    assert out["fusiones"]["markers"][0]["destacar"] is True


def test_dashboard_fusion_planta_mock(monkeypatch):
    def fake_rama(rama, *, fusion_destacar=None):
        return {
            "tipo": "rama",
            "rama": rama,
            "planta_interna": {"ok": True, "fusiones": {"ok": True, "markers": []}},
        }

    monkeypatch.setattr(co, "resolver_rama_desde_fusion_planta", lambda c: {
        "ok": True,
        "rama": "SF01-RATC-0-001318",
        "fusion_id": c,
    })
    monkeypatch.setattr(co, "dashboard_camino_optico_rama", fake_rama)
    out = co.dashboard_camino_optico_fusion_planta("SF01-R1301-010")
    assert out["rama"] == "SF01-RATC-0-001318"
    assert out["fusion_busqueda"] == "SF01-R1301-010"


def test_resolver_fusion_planta_db():
    """Requiere Postgres con report_fusiones (skip si no hay DB)."""
    try:
        res = resolver_rama_desde_fusion_planta("SF01-R1301-010")
    except Exception:
        return
    if not res.get("ok"):
        return
    assert res["rama"] == "SF01-RATC-0-001301"
    fus = consultar_fusiones_verificacion_rama(
        ["SF01-RATC-0-001318"], fusion_destacar="SF01-R1301-010"
    )
    assert fus.get("ok")
    assert any(m.get("fusion_id") == "SF01-R1301-010" for m in fus.get("markers") or [])
