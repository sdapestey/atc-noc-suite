from contextlib import contextmanager
from pathlib import Path


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
    assert "cto_maps_url" in tpl
    assert "Ver en Google Maps" in tpl
    assert "Sin coordenadas" in tpl


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


def test_dashboard_camino_optico_cto_cto_maps_url_with_coords(monkeypatch):
    import services.camino_optico as co

    monkeypatch.setattr(co, "db_cursor", _fake_cto_fat_cursor())
    monkeypatch.setattr(
        co,
        "consultar_cto_coordenadas",
        lambda _cto: {"lat": -34.5, "lon": -58.6},
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
    monkeypatch.setattr(co, "consultar_cto_coordenadas", lambda _cto: None)

    out = co.dashboard_camino_optico_cto("SF01-FATC-8-200189")
    assert out["tipo"] == "cto"
    assert out.get("cto_maps_url") is None


def test_camino_optico_template_cto_branch_uses_cto_maps_url():
    tpl = Path("templates/dashboard_camino_optico.html").read_text(encoding="utf-8")
    assert 'data.tipo === "cto"' in tpl
    assert "mapsUrlCto" in tpl
    assert "data.cto_maps_url" in tpl
