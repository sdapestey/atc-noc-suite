"""Consulta masiva de ramas en Camino óptico."""
import services.camino_optico as co


def test_parse_rama_masivo_tokens_dedupe_and_filter():
    ramas, invalid = co._parse_rama_masivo_tokens(
        [
            "ES01-RATC-0-000384",
            "ES01-RATC-0-000384",
            "ES01-RATC-0-000385",
            "TG01-FATC-8-100987",
            "not-a-token",
        ]
    )
    assert ramas == ["ES01-RATC-0-000384", "ES01-RATC-0-000385"]
    assert invalid == ["TG01-FATC-8-100987", "not-a-token"]


def test_parse_rama_masivo_multiline_text():
    raw = "ES01-RATC-0-000382\nES01-RATC-0-000387,\nES01-RATC-0-000470"
    ramas, invalid = co._parse_rama_masivo_tokens(raw)
    assert len(ramas) == 3
    assert invalid == []


def test_build_ctos_union_shared_flag():
    ramas_data = [
        {
            "rama": "ES01-RATC-0-000384",
            "ctos": [{"cto": "TG01-FATC-8-100987", "onts": 2}, {"cto": "TG01-FATC-8-100988", "onts": 1}],
        },
        {
            "rama": "ES01-RATC-0-000385",
            "ctos": [{"cto": "TG01-FATC-8-100987", "onts": 3}],
        },
    ]
    union = co._build_ctos_union(ramas_data)
    by_cto = {c["cto"]: c for c in union}
    assert by_cto["TG01-FATC-8-100987"]["onts"] == 5
    assert by_cto["TG01-FATC-8-100987"]["shared"] is True
    assert by_cto["TG01-FATC-8-100987"]["ramas"] == [
        "ES01-RATC-0-000384",
        "ES01-RATC-0-000385",
    ]
    assert by_cto["TG01-FATC-8-100988"]["shared"] is False


def test_dashboard_camino_optico_ramas_masivo_empty():
    out = co.dashboard_camino_optico_ramas_masivo([])
    assert "error" in out


def test_build_rama_colors_stable():
    colors = co._build_rama_colors(["ES01-RATC-0-000384", "ES01-RATC-0-000385"])
    assert colors["ES01-RATC-0-000384"]["index"] == 0
    assert colors["ES01-RATC-0-000385"]["index"] == 1
    assert colors["ES01-RATC-0-000384"]["line"].startswith("#")


def test_sugerir_ctos_medicion_shared_and_first():
    ramas_data = [
        {
            "rama": "ES01-RATC-0-000384",
            "sin_inventario": False,
            "ctos": [{"cto": "TG01-FATC-8-100987", "onts": 2}, {"cto": "TG01-FATC-8-100999", "onts": 1}],
        },
        {
            "rama": "ES01-RATC-0-000385",
            "sin_inventario": False,
            "ctos": [{"cto": "TG01-FATC-8-100987", "onts": 3}],
        },
    ]
    union = co._build_ctos_union(ramas_data)
    sug = co._sugerir_ctos_medicion(ramas_data, union)
    assert sug
    assert sug[0]["cto"] == "TG01-FATC-8-100987"
    assert sug[0]["prioridad"] == "alta"
    ctos = {s["cto"] for s in sug}
    assert "TG01-FATC-8-100987" in ctos


def test_dashboard_camino_optico_ramas_masivo_route(client, monkeypatch):
    import web.routes as routes

    def fake_masivo(raw):
        return {
            "tipo": "ramas_masivo",
            "ramas": [{"rama": "ES01-RATC-0-000384", "resumen": {"cto_count": 1, "ont_count": 2}}],
            "resumen": {"rama_count": 1, "cto_unique": 1, "cto_shared": 0, "ont_count": 2},
            "ctos_union": [],
            "cto_markers": [],
            "cto_markers_by_rama": [],
            "rama_colors": {},
            "sugerencias_medicion": [],
            "gis": {"ok": True, "geojson": {"type": "FeatureCollection", "features": []}},
        }

    monkeypatch.setattr(routes, "dashboard_camino_optico_ramas_masivo", fake_masivo)

    r = client.post(
        "/dashboard/camino-optico/consultar-masivo",
        json={"values": ["ES01-RATC-0-000384"]},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["tipo"] == "ramas_masivo"


def test_camino_template_has_masivo_ui():
    from pathlib import Path

    html = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "caminoApplyDeepLinkFromUrl" in html
    assert "consultar-masivo" in html
    assert "camino-panel-masivo" in html
    assert "camino-masivo-meta" in html
    assert "parseCaminoMasivoTokens" in html
    assert "camino-leyenda-details" in html
    assert "Ctrl" in html
    assert "ramas_masivo" in html
    assert "sugerencias_medicion" in html
    assert "zonas_corte_probable" in html
    assert "drawMasivoColoredOnMap" in html
    assert "drawMasivoCorteZones" in html
    assert "camino-masivo-legend-corte-swatch" in html
    assert "drawMasivoFoscOnMap" in html
    assert "CAMINO_FOSC_ICON_URL" in html
    assert "masivoFoscDivIcon" in html
    assert "masivoFoscLayer" in html
    assert "infra_fosc" in html
    assert "destroyGisMapForMasivo" in html
    assert "masivoPathsLayer" in html
    assert "troncal_length_m" in html


def test_zonas_corte_probable_troncal_compartida():
    shared = [
        [-58.801, -34.352],
        [-58.800, -34.351],
        [-58.799, -34.350],
    ]
    features = []
    for i, rama in enumerate(["ES01-RATC-0-000388", "ES01-RATC-0-000389", "ES01-RATC-0-000390"]):
        tail = [[-58.798 + i * 0.002, -34.349 + i * 0.001]]
        features.append(
            {
                "type": "Feature",
                "properties": {"camino_rama": rama},
                "geometry": {
                    "type": "LineString",
                    "coordinates": shared + tail,
                },
            }
        )
    gis = {"ok": True, "geojson": {"type": "FeatureCollection", "features": features}}
    ramas = ["ES01-RATC-0-000388", "ES01-RATC-0-000389", "ES01-RATC-0-000390"]
    zonas, troncal = co._analisis_corte_masivo_gis(gis, ramas)
    assert len(zonas) == 1
    assert zonas[0]["rama_count"] >= 3
    assert zonas[0]["tipo"] == "reparto"
    assert zonas[0]["prioridad"] in ("critica", "alta", "media")
    assert zonas[0].get("troncal_length_m", 0) > 0
    assert troncal.get("ok") is True
    assert len(troncal.get("points") or []) >= 2
    # Punto de reparto al final del tramo común (más lejos del origen que el inicio).
    assert zonas[0]["lat"] > -34.351


def test_analisis_corte_una_sola_zona():
    shared = [[-58.70, -34.40], [-58.69, -34.39]]
    features = [
        {
            "type": "Feature",
            "properties": {"camino_rama": "TG02-RATC-0-000403"},
            "geometry": {"type": "LineString", "coordinates": shared + [[-58.68, -34.38]]},
        },
        {
            "type": "Feature",
            "properties": {"camino_rama": "TG02-RATC-0-000404"},
            "geometry": {"type": "LineString", "coordinates": shared + [[-58.67, -34.37]]},
        },
    ]
    gis = {"ok": True, "geojson": {"type": "FeatureCollection", "features": features}}
    zonas, troncal = co._analisis_corte_masivo_gis(gis, ["TG02-RATC-0-000403", "TG02-RATC-0-000404"])
    assert len(zonas) == 1
    assert troncal["ok"] is True
    bif = troncal["bifurcacion"]
    assert bif["lat"] >= troncal["origen"]["lat"] - 0.001


def test_zonas_corte_probable_sin_gis():
    zonas, troncal = co._analisis_corte_masivo_gis({"ok": False}, ["A", "B"])
    assert zonas == []
    assert troncal.get("ok") is False


def test_cabecera_desde_rama():
    from services.camino_gis import cabecera_desde_rama

    assert cabecera_desde_rama("TG02-RATC-0-000403") == "TG02"
    assert cabecera_desde_rama("ES01-RATC-0-000384") == "ES01"
    assert cabecera_desde_rama("") == ""


def test_enriquecer_masivo_con_infra_fosc_snap(monkeypatch):
    zonas = [
        {
            "lat": -34.35,
            "lon": -58.80,
            "motivo": "Reparto común.",
            "rama_count": 16,
        }
    ]
    gis = {"ok": True}

    def fake_fosc(ramas, cabecera):
        assert cabecera == "TG02"
        return {
            "ok": True,
            "markers": [
                {"id_botella": 1, "id_cm": "FOSC-001", "lat": -34.351, "lon": -58.801, "tipo": "FOSC"},
                {"id_botella": 2, "id_cm": "FOSC-002", "lat": -34.352, "lon": -58.802, "tipo": "FOSC"},
            ],
        }

    def fake_snap(ramas, la, lo, cabecera):
        return {
            "ok": True,
            "id_botella": 1,
            "id_cm": "FOSC-001",
            "tipo": "FOSC",
            "direccion": "Emilio Lamarca",
            "lat": -34.351,
            "lon": -58.801,
            "dist_snap_m": 12.5,
            "maps_url": "https://www.google.com/maps?q=-34.351,-58.801",
        }

    monkeypatch.setattr(co, "consultar_fosc_cerca_trazado_ramas", fake_fosc)
    monkeypatch.setattr(co, "snap_corte_a_fosc", fake_snap)

    out = co._enriquecer_masivo_con_infra_fosc(["TG02-RATC-0-000403"], gis, zonas)
    assert out["fosc"]["ok"] is True
    assert len(out["fosc"]["markers"]) == 2
    assert out["snap_corte"]["ok"] is True
    assert zonas[0]["lat"] == -34.351
    assert zonas[0]["lat_heuristica"] == -34.35
    assert zonas[0]["snap_fosc"]["id_cm"] == "FOSC-001"
    assert out["fosc"]["markers"][0]["snap_target"] is True
    assert "Snap FOSC" in zonas[0]["motivo"]


def test_enriquecer_masivo_sin_gis():
    out = co._enriquecer_masivo_con_infra_fosc(["TG02-RATC-0-000403"], {"ok": False}, [])
    assert out["fosc"]["ok"] is False
    assert out["snap_corte"] is None
