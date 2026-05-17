from contextlib import contextmanager
from pathlib import Path

import pytest


def _fake_cto_fat_cursor():
    cols = [
        "access_id",
        "status",
        "site_fullname",
        "site_description",
        "site_type",
        "physical_path",
        "path_atc",
        "feeder_bentley",
        "feeder_cm",
        "fiber_feeder",
        "location_fullname",
        "location_description",
        "location_name",
        "location_type",
        "alias_atc",
        "component_name",
        "componente_fullname",
        "port_name",
        "port_number",
        "olt_odf_fiber",
        "object_name_ui",
        "invocator_system",
    ]
    desc = [(c, None, None, None, None, None, None) for c in cols]
    vals = [None] * len(cols)
    vals[cols.index("access_id")] = "1"
    vals[cols.index("status")] = "IN SERVICE"
    vals[cols.index("path_atc")] = "SF01-RATC-0-000001"
    vals[cols.index("location_description")] = "SF01-FATC-8-200189"
    vals[cols.index("object_name_ui")] = "BA_OLTA_SF01_01-1-1-3-6-35"
    vals[cols.index("site_fullname")] = "San Fernando · Site X"
    vals[cols.index("physical_path")] = "SF01 / path"

    class FakeCur:
        def execute(self, sql, params=None):
            if "inventory_fat_occupation" in sql and "location_description = %s" in sql:
                self.description = desc
                self._rows = [tuple(vals)]
            elif "cm_report_isp" in sql:
                self.description = [
                    ("headend", None, None, None, None, None, None),
                ]
                self._fetchone = None

        def fetchall(self):
            return self._rows

        def fetchone(self):
            return getattr(self, "_fetchone", None)

    @contextmanager
    def ctx():
        yield FakeCur()

    return ctx


def test_camino_optico_template_has_no_text_maps_links():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "Ver en Maps" not in tpl
    assert "camino-maps-hint" not in tpl
    assert "gmapsSearchUrl" not in tpl
    assert "mapsLinkHref" not in tpl
    assert "cableMaps" not in tpl
    assert "Ubicación (CTO)" in tpl
    assert "camino-ubicacion-cto" in tpl
    assert "camino-path-badge" in tpl
    assert "camino-popup-addr" in tpl


def test_camino_optico_consultar_access_id_includes_cto_maps_url(client, monkeypatch):
    import web.routes as routes

    def fake_access_id(_aid):
        return {
            "tipo": "access_id",
            "detalle": {
                "access_id": "105",
                "location_description": "SF01-FATC-8-200189",
                "path_atc": "SF01-RATC-0-000001",
                "OPERADOR": "TASA",
            },
            "cto_maps_url": "https://www.google.com/maps/search/?api=1&query=-34.5%2C-58.6",
        }

    monkeypatch.setattr(routes, "dashboard_camino_optico_access_id", fake_access_id)

    r = client.post(
        "/dashboard/camino-optico/consultar",
        json={"tipo": "access_id", "valor": "105"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["cto_maps_url"] == "https://www.google.com/maps/search/?api=1&query=-34.5%2C-58.6"
    assert data["tipo"] == "access_id"


def test_camino_optico_template_access_id_loads_map():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    idx_access = tpl.find('data.tipo === "access_id"')
    idx_load = tpl.find("loadCaminoRamaMap", idx_access)
    assert idx_access != -1
    assert idx_load != -1
    assert "GIS_HEAD_ACCESS" in tpl


def test_dashboard_camino_optico_cto_camino_contexto(monkeypatch):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_cto_fat_cursor())
    monkeypatch.setattr(co, "consultar_cto_coordenadas", lambda _cto: None)
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda _cto: "Bolivia 4836 (BA Moreno)")
    monkeypatch.setattr(co, "_cto_markers_para_ramas", lambda *_a, **_k: [])
    monkeypatch.setattr(
        co,
        "_gis_merge_para_ramas",
        lambda _ramas: {"ok": False, "error": "sin GIS en test"},
    )

    out = co.dashboard_camino_optico_cto("SF01-FATC-8-200189")
    ctx = out.get("camino_contexto") or {}
    assert ctx["ramas"] == ["SF01-RATC-0-000001"]
    assert ctx["lt"] == "BA_OLTA_SF01_01.LT1"
    assert ctx["sitio_principal"] == "San Fernando"
    assert ctx["sitio_codigo"] == "SF01_01"
    assert ctx["site_fullname"] == "San Fernando · Site X"
    assert out["direccion_postal"] == "Bolivia 4836 (BA Moreno)"


def test_dashboard_camino_optico_cto_cto_maps_url_with_coords(monkeypatch):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_cto_fat_cursor())
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda _cto: None)
    monkeypatch.setattr(
        co,
        "consultar_cto_coordenadas",
        lambda _cto: {"lat": -34.5, "lon": -58.6},
    )
    monkeypatch.setattr(co, "_cto_markers_para_ramas", lambda *_a, **_k: [])
    monkeypatch.setattr(
        co,
        "_gis_merge_para_ramas",
        lambda _ramas: {"ok": False, "error": "sin GIS en test"},
    )

    out = co.dashboard_camino_optico_cto("SF01-FATC-8-200189")
    assert out["tipo"] == "cto"
    assert (
        out["cto_maps_url"]
        == "https://www.google.com/maps/search/?api=1&query=-34.5%2C-58.6"
    )


def test_dashboard_camino_optico_cto_cto_maps_url_without_coords(monkeypatch):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_cto_fat_cursor())
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda _cto: None)
    monkeypatch.setattr(co, "consultar_cto_coordenadas", lambda _cto: None)
    monkeypatch.setattr(co, "_cto_markers_para_ramas", lambda *_a, **_k: [])
    monkeypatch.setattr(
        co,
        "_gis_merge_para_ramas",
        lambda _ramas: {"ok": False, "error": "sin GIS en test"},
    )

    out = co.dashboard_camino_optico_cto("SF01-FATC-8-200189")
    assert out["tipo"] == "cto"
    assert out.get("cto_maps_url") is None


def test_camino_optico_template_cto_branch_renders_contexto():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert 'data.tipo === "cto"' in tpl
    assert "camino_contexto" in tpl
    assert "camino-contexto-path" in tpl
    assert "renderJerarquiaNavBar" in tpl
    assert "data-camino-nav-tipo" in tpl


def test_camino_optico_template_rama_loads_map():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "loadCaminoRamaMap" in tpl
    assert "cto_markers" in tpl
    assert "gis-rama" not in tpl


def test_camino_optico_template_lt_overlay_controls():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "camino-lt-overlay-controls" in tpl
    assert "gis-por-lt" in tpl
    assert "setupLtSiblingUi" in tpl


def test_camino_optico_template_map_before_results_no_arbol_panel():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert "camino-consulta-stack" in tpl
    idx_map = tpl.find('id="camino-rama-map-panel"')
    idx_out = tpl.find('id="out"')
    assert idx_map != -1 and idx_out != -1
    assert idx_map < idx_out
    assert "camino-arbol-panel" not in tpl
    assert "renderCaminoTree" not in tpl
    assert 'id="camino-gis-fs-toggle"' in tpl
    assert "requestFullscreen" in tpl or "webkitRequestFullscreen" in tpl


def test_camino_optico_template_cto_loads_map():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert 'data.tipo === "cto"' in tpl
    idx_cto = tpl.find('data.tipo === "cto"')
    idx_load = tpl.find("loadCaminoRamaMap", idx_cto)
    assert idx_load != -1
    assert "ctoMarkerFocalOpts" in tpl
    assert "focal" in tpl
    assert "wireCaminoCtoMarker" in tpl


def test_dashboard_camino_optico_lt_jerarquia_includes_equipo_pasos(monkeypatch):
    import services.camino_optico as co

    def fake_olts():
        return [
            {
                "PRINCIPAL": "Moreno",
                "OLTS": [
                    {"OLT_LOGICO": "BA_OLTA_MR01_01", "SITIO_CODIGO": "MR01_01", "LTS": []},
                    {"OLT_LOGICO": "BA_OLTA_MR01_02", "SITIO_CODIGO": "MR01_02", "LTS": []},
                ],
            }
        ]

    monkeypatch.setattr(co, "dashboard_olts", fake_olts)
    monkeypatch.setattr(
        co,
        "gis_payload_para_lt",
        lambda _lt: {
            "ok": True,
            "lt": "BA_OLTA_MR01_01.LT1",
            "resumen": {"rama_count": 1, "ramas": ["MR01-RATC-0-000001"]},
            "cto_markers": [],
            "gis": {"ok": True, "geojson": {"type": "FeatureCollection", "features": []}},
        },
    )
    monkeypatch.setattr(co, "list_lts_mismo_olt", lambda _olt: ["BA_OLTA_MR01_01.LT1"])

    out = co.dashboard_camino_optico_lt("BA_OLTA_MR01_01.LT1")
    pasos = (out.get("jerarquia_nav") or {}).get("pasos") or []
    tipos = [p["tipo"] for p in pasos]
    assert tipos[:4] == ["sitio", "equipo", "equipo", "lt"]
    assert pasos[1].get("titulo") == "MR01_01"
    assert pasos[1]["valor"] == "BA_OLTA_MR01_01"


def test_dashboard_camino_optico_cto_includes_gis_and_markers(monkeypatch):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_cto_fat_cursor())
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda _cto: None)
    monkeypatch.setattr(
        co,
        "consultar_cto_coordenadas",
        lambda _cto: {"lat": -34.5, "lon": -58.6},
    )
    monkeypatch.setattr(
        co,
        "_cto_markers_para_ramas",
        lambda ramas, focal: [
            {
                "cto": "SF01-FATC-8-200189",
                "lat": -34.5,
                "lon": -58.6,
                "onts": 1,
                "source": "bajada_inventario",
                "focal": True,
            },
            {
                "cto": "SF01-FATC-8-OTHER",
                "lat": -34.4,
                "lon": -58.5,
                "onts": 2,
                "source": "bajada_inventario",
                "focal": False,
            },
        ],
    )
    monkeypatch.setattr(
        co,
        "_gis_merge_para_ramas",
        lambda _ramas: {
            "ok": True,
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[-58.6, -34.5], [-58.5, -34.4]],
                        },
                        "properties": {},
                    }
                ],
            },
        },
    )

    out = co.dashboard_camino_optico_cto("SF01-FATC-8-200189")
    assert out["tipo"] == "cto"
    assert len(out["cto_markers"]) == 2
    assert out["cto_markers"][0]["focal"] is True
    assert out["cto_markers"][1]["focal"] is False
    assert out["gis"]["ok"] is True
    assert len(out["gis"]["geojson"]["features"]) == 1


def test_dashboard_camino_optico_access_id_includes_gis_and_markers(monkeypatch):
    import services.camino_optico as co

    @contextmanager
    def _fake_access_cursor():
        cols = [
            "access_id",
            "status",
            "site_fullname",
            "site_description",
            "site_type",
            "physical_path",
            "path_atc",
            "feeder_bentley",
            "feeder_cm",
            "fiber_feeder",
            "location_fullname",
            "location_description",
            "location_name",
            "location_type",
            "alias_atc",
            "component_name",
            "componente_fullname",
            "port_name",
            "port_number",
            "olt_odf_fiber",
            "object_name_ui",
            "invocator_system",
        ]
        desc = [(c, None, None, None, None, None, None) for c in cols]
        vals = [None] * len(cols)
        vals[cols.index("access_id")] = "1057109390"
        vals[cols.index("status")] = "IN SERVICE"
        vals[cols.index("path_atc")] = "SF01-RATC-0-000001"
        vals[cols.index("location_description")] = "SF01-FATC-8-100189"

        class FakeCur:
            def execute(self, sql, params=None):
                if "WHERE f.access_id = %s" in sql:
                    self.description = desc
                    self._fetchone = tuple(vals)
                elif "cm_report_isp" in sql:
                    self.description = [("headend", None, None, None, None, None, None)]
                    self._fetchone = None

            def fetchone(self):
                return getattr(self, "_fetchone", None)

        yield FakeCur()

    monkeypatch.setattr(co, "db_cursor", _fake_access_cursor)
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda _cto: "Dir test (CM)")
    monkeypatch.setattr(
        co,
        "consultar_cto_coordenadas",
        lambda _cto: {"lat": -34.5, "lon": -58.6},
    )
    monkeypatch.setattr(
        co,
        "_cto_markers_para_ramas",
        lambda ramas, focal: [
            {
                "cto": focal,
                "lat": -34.5,
                "lon": -58.6,
                "onts": 1,
                "source": "bajada_inventario",
                "focal": True,
            }
        ],
    )
    monkeypatch.setattr(
        co,
        "_gis_merge_para_ramas",
        lambda _ramas: {
            "ok": True,
            "geojson": {"type": "FeatureCollection", "features": []},
        },
    )

    out = co.dashboard_camino_optico_access_id("1057109390")
    assert out["tipo"] == "access_id"
    assert out["direccion_postal"] == "Dir test (CM)"
    assert out["cto_markers"][0]["focal"] is True
    assert out["gis"]["ok"] is True
    assert out["jerarquia_nav"]["foco"]["tipo"] == "access_id"
    assert out["camino_contexto"]["cto"] == "SF01-FATC-8-100189"


@pytest.fixture
def _fake_rama_db_cursor():
    class FC:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params=None):
            self.sql = sql or ""

        def fetchone(self):
            if "COUNT(DISTINCT" in self.sql:
                return (2, 5)
            if "cm_report_isp" in self.sql:
                return None
            if "s.object_name" in self.sql and "LIMIT 1" in self.sql:
                return ("BA_OLTA_ES01_01-1-1",)
            return None

        def fetchall(self):
            if "GROUP BY" in self.sql:
                return [("ES01-FATC-8-A", 2), ("ES01-FATC-8-B", 3)]
            return []

    @contextmanager
    def ctx():
        yield FC()

    return ctx


def test_dashboard_camino_optico_rama_includes_markers_and_gis(monkeypatch, _fake_rama_db_cursor):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_rama_db_cursor)
    monkeypatch.setattr(
        co,
        "consultar_cto_coordenadas",
        lambda cto: {"lat": -34.1, "lon": -58.2},
    )
    monkeypatch.setattr(co, "consultar_cto_direccion_postal", lambda cto: f"Dir postal {cto}")
    monkeypatch.setattr(
        co,
        "consultar_ci_op_por_rama",
        lambda rama: {
            "ok": True,
            "table": "cm.ci_op",
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": [[-58.3, -34.2], [-58.2, -34.2]]},
                        "properties": {"nombre_op": "ES01-RATC-0-000001"},
                    }
                ],
            },
        },
    )

    out = co.dashboard_camino_optico_rama("ES01-RATC-0-000001")
    assert out["tipo"] == "rama"
    assert len(out["cto_markers"]) == 2
    assert out["cto_markers"][0]["cto"] == "ES01-FATC-8-A"
    assert out["cto_markers"][0]["lat"] == -34.1
    assert out["cto_markers"][0]["direccion_postal"] == "Dir postal ES01-FATC-8-A"
    assert out["gis"]["ok"] is True
    assert out["gis"]["geojson"]["features"][0]["properties"]["nombre_op"] == "ES01-RATC-0-000001"
