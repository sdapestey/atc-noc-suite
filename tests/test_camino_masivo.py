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
    assert sug[0]["prioridad"] in ("alta", "critica")
    ctos = {s["cto"] for s in sug}
    assert "TG01-FATC-8-100987" in ctos


def test_sugerir_ctos_medicion_convergencia_todas_ramas(monkeypatch):
    """Prioriza la primera CTO común a todas las ramas (cerca del origen del troncal)."""
    ramas_data = [
        {
            "rama": "SF01-RATC-0-000482",
            "sin_inventario": False,
            "ctos": [
                {"cto": "SF01-FATC-8-100100", "onts": 1},
                {"cto": "SF01-FATC-8-100200", "onts": 2},
                {"cto": "SF01-FATC-8-104032", "onts": 2},
            ],
        },
        {
            "rama": "SF01-RATC-0-000483",
            "sin_inventario": False,
            "ctos": [
                {"cto": "SF01-FATC-8-100100", "onts": 1},
                {"cto": "SF01-FATC-8-100200", "onts": 1},
            ],
        },
        {
            "rama": "SF01-RATC-0-000484",
            "sin_inventario": False,
            "ctos": [
                {"cto": "SF01-FATC-8-100100", "onts": 1},
                {"cto": "SF01-FATC-8-100300", "onts": 1},
            ],
        },
    ]
    union = co._build_ctos_union(ramas_data)
    troncal = {
        "ok": True,
        "points": [
            {"lat": -34.44, "lon": -58.55},
            {"lat": -34.45, "lon": -58.56},
        ],
    }

    def fake_coords(ctos):
        return {
            "SF01-FATC-8-100100": {"lat": -34.4401, "lon": -58.5501},
            "SF01-FATC-8-100200": {"lat": -34.445, "lon": -58.555},
            "SF01-FATC-8-100300": {"lat": -34.45, "lon": -58.56},
            "SF01-FATC-8-104032": {"lat": -34.46, "lon": -58.57},
        }

    monkeypatch.setattr(co, "_resolve_cto_coords_map", fake_coords)
    sug = co._sugerir_ctos_medicion(ramas_data, union, troncal)

    assert sug[0]["cto"] == "SF01-FATC-8-100100"
    assert sug[0]["prioridad"] == "critica"
    assert "común a las 3 ramas" in sug[0]["motivo"]
    ctos = {s["cto"] for s in sug}
    assert "SF01-FATC-8-104032" not in ctos


def test_sugerir_ctos_medicion_foco_gis_sin_cto_comun(monkeypatch):
    """Con varias ramas sin CTO común en inventario, prioriza la CTO más cercana al reparto GIS."""
    ramas_data = [
        {
            "rama": "SF01-RATC-0-000482",
            "sin_inventario": False,
            "ctos": [{"cto": "SF01-FATC-8-102240", "onts": 1}, {"cto": "SF01-FATC-8-104032", "onts": 2}],
        },
        {
            "rama": "SF01-RATC-0-000483",
            "sin_inventario": False,
            "ctos": [{"cto": "SF01-FATC-8-101850", "onts": 1}],
        },
    ]
    union = co._build_ctos_union(ramas_data)
    zonas = [
        {
            "tipo": "reparto",
            "lat": -34.445615,
            "lon": -58.555662,
            "selected": True,
            "rama_count": 2,
        }
    ]

    def fake_coords(ctos):
        return {
            "SF01-FATC-8-104032": {"lat": -34.445615, "lon": -58.555662},
            "SF01-FATC-8-102240": {"lat": -34.44490, "lon": -58.55510},
            "SF01-FATC-8-101850": {"lat": -34.44450, "lon": -58.55450},
        }

    monkeypatch.setattr(co, "_resolve_cto_coords_map", fake_coords)
    sug = co._sugerir_ctos_medicion(ramas_data, union, None, zonas)

    assert sug[0]["cto"] == "SF01-FATC-8-104032"
    assert sug[0]["prioridad"] == "critica"
    assert "convergen las 2 ramas" in sug[0]["motivo"]
    assert all(s["cto"] != "SF01-FATC-8-102240" or s["score"] < sug[0]["score"] for s in sug)


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
    assert "consulta-search-card" in html
    assert "consulta-masivo-input" in html
    assert ">Masivo<" in html
    assert "Ramas masivo" not in html
    assert "empty-state-note" in html
    assert "Lucas Gimenez" not in html
    assert "orquestador-credit" not in html
    assert "parseCaminoMasivoTokens" in html
    assert "ramas_masivo" in html
    assert "sugerencias_medicion" in html
    assert "drawMasivoCtoFocoSugerido" in html
    assert "camino-map-beacon" in html
    assert "addCaminoMapBeacon" in html
    assert "wireMasivoLayerFilterControls" in html
    assert "data-masivo-filter" in html
    assert "Capas del mapa" in html
    assert "Baliza inicio troncal" in html
    assert "CTO sugerida para medir" in html
    assert "function wireCaminoMasivoSugerenciasClick" in html
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
    assert len(zonas) == 2
    tipos = {z["tipo"] for z in zonas}
    assert tipos == {"reparto", "troncal_origen"}
    reparto = next(z for z in zonas if z["tipo"] == "reparto")
    assert reparto["rama_count"] >= 3
    assert reparto["prioridad"] in ("critica", "alta", "media")
    assert reparto.get("troncal_length_m", 0) > 0
    assert troncal.get("ok") is True
    assert len(troncal.get("points") or []) >= 2
    # Punto de reparto al final del tramo común (más lejos del origen que el inicio).
    assert reparto["lat"] > -34.351


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
    assert len(zonas) == 2
    assert troncal["ok"] is True
    bif = troncal["bifurcacion"]
    assert bif["lat"] >= troncal["origen"]["lat"] - 0.001


def test_elegir_zona_corte_prefer_origen_con_fosc_cercana():
    zonas = [
        {
            "tipo": "troncal_origen",
            "lat": -34.477737,
            "lon": -58.488882,
            "motivo": "Inicio troncal.",
            "rama_count": 14,
        },
        {
            "tipo": "reparto",
            "lat": -34.501468,
            "lon": -58.497466,
            "motivo": "Reparto.",
            "rama_count": 14,
        },
    ]
    markers = [
        {"id_botella": 1, "lat": -34.47774, "lon": -58.48888},
        {"id_botella": 2, "lat": -34.47780, "lon": -58.48890},
        {"id_botella": 3, "lat": -34.47785, "lon": -58.48891},
        {"id_botella": 4, "lat": -34.47790, "lon": -58.48892},
        {"id_botella": 5, "lat": -34.50104, "lon": -58.49746},
    ]
    troncal = {
        "length_m": 19612,
        "points": [
            {"lat": -34.47767, "lon": -58.48887},
            {"lat": -34.48, "lon": -58.49},
            {"lat": -34.501468, "lon": -58.497466},
        ],
    }
    out = co._elegir_zona_corte_principal(zonas, markers, troncal)
    assert out[0]["tipo"] == "troncal_origen"
    assert out[0]["selected"] is True
    assert out[1]["tipo"] == "reparto"
    assert out[1]["selected"] is False


def test_elegir_zona_corte_prefer_reparto_corte_distribucion():
    """Corte aguas abajo del reparto: más FOSC hacia distribución que en cabecera."""
    zonas = [
        {
            "tipo": "troncal_origen",
            "lat": -34.504132,
            "lon": -58.52383,
            "motivo": "Inicio.",
            "rama_count": 4,
        },
        {
            "tipo": "reparto",
            "lat": -34.501043,
            "lon": -58.53833,
            "motivo": "Reparto.",
            "rama_count": 4,
        },
    ]
    markers = [{"id_botella": i, "lat": -34.50413 + i * 0.00001, "lon": -58.52383} for i in range(7)]
    markers += [{"id_botella": 20 + i, "lat": -34.50104, "lon": -58.53833 + i * 0.00001} for i in range(6)]
    troncal = {
        "length_m": 24000,
        "points": [{"lat": -34.504132, "lon": -58.52383}, {"lat": -34.501043, "lon": -58.53833}],
    }
    out = co._elegir_zona_corte_principal(zonas, markers, troncal)
    assert out[0]["tipo"] == "reparto"
    assert out[0]["selected"] is True


def test_elegir_zona_corte_prefer_reparto_troncal_corto():
    zonas = [
        {"tipo": "troncal_origen", "lat": -34.40, "lon": -58.70, "motivo": "Inicio.", "rama_count": 2},
        {"tipo": "reparto", "lat": -34.39, "lon": -58.69, "motivo": "Reparto.", "rama_count": 2},
    ]
    markers = [{"id_botella": 1, "lat": -34.39, "lon": -58.69}]
    troncal = {
        "length_m": 400,
        "points": [
            {"lat": -34.40, "lon": -58.70},
            {"lat": -34.39, "lon": -58.69},
        ],
    }
    out = co._elegir_zona_corte_principal(zonas, markers, troncal)
    assert out[0]["tipo"] == "reparto"
    assert out[0]["selected"] is True


def test_zonas_corte_probable_sin_gis():
    zonas, troncal = co._analisis_corte_masivo_gis({"ok": False}, ["A", "B"])
    assert zonas == []
    assert troncal.get("ok") is False


def test_cabecera_desde_rama():
    from services.camino_gis import cabecera_desde_rama

    assert cabecera_desde_rama("TG02-RATC-0-000403") == "TG02"
    assert cabecera_desde_rama("ES01-RATC-0-000384") == "ES01"
    assert cabecera_desde_rama("") == ""


def test_normalize_fosc_direccion():
    from services.camino_gis import _normalize_fosc_direccion

    assert _normalize_fosc_direccion("Cuyo, 3400") == "Cuyo, 3400"
    assert _normalize_fosc_direccion("None, None") == ""
    assert _normalize_fosc_direccion(" none , None ") == ""
    assert _normalize_fosc_direccion(None) == ""
    assert _normalize_fosc_direccion("-") == ""


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

    def fake_fosc(ramas, cabecera=None, **kwargs):
        assert kwargs.get("filtrar_cabecera") is False
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

    out = co._enriquecer_masivo_con_infra_fosc(
        ["TG02-RATC-0-000403"], gis, zonas, {"length_m": 5000, "points": []}
    )
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
