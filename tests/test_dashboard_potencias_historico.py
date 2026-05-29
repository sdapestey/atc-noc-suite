import re
from pathlib import Path

def test_dashboard_potencias_historico_get_renders(client):
    r = client.get("/dashboard/potencias-historico")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Historico Potencias" in html
    assert 'id="ont-cto-summary-wrap"' in html
    assert 'id="ont-cto-summary-table"' in html
    assert 'id="ont-cto-summary-tbody"' in html
    assert "Último histórico (dBm)" in html
    assert "Potencias por CTO" in html
    assert "historico-cto-summary__th-spacer" in html
    assert 'id="ratc-input"' in html
    assert 'id="power-chart"' in html
    assert "dashboard-potencias-historico.js" in html
    assert "dashboard-historico-potencias.css" in html
    assert "btn-toggle-legend" in html
    assert "btn-show-all" in html
    assert "btn-hide-all" in html
    assert 'id="btn-consultar-ahora"' in html
    assert 'id="kpi-snapshot-hint"' in html
    js = Path("static/js/dashboard-potencias-historico.js").read_text(encoding="utf-8")
    assert "/api/potencias-historico/" in js
    assert "Snapshot RX sin lecturas válidas" in js
    assert "RX manual ONT " in js
    assert "Umbral -27 dBm" in js
    assert "Umbral -25 dBm" in js
    assert "clasificar_rx_dbm" in js
    assert "HISTORICO_RX_DOWN_PLACEHOLDER_DBM" in js
    assert "_isHistoricoRxDownPlaceholder" in js
    assert "_copyHistoricoAccessId" in js
    assert "data-access-id" in js
def test_api_potencias_historico_consultar_ahora_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_altiplano_ahora_rama",
        lambda _ratc: {
            "ok": True,
            "timestamp": "2026-04-27 18:00:31",
            "pon": "BA_OLTA_MR01_01-1-1",
            "samples": [{"ont_key": "3", "rx_dbm": -20.5}],
        },
    )
    r = client.post("/api/potencias-historico/MR01-RATC-0-000200/consultar-ahora")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["timestamp"] == "2026-04-27 18:00:31"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", payload["timestamp"])
    assert payload["pon"] == "BA_OLTA_MR01_01-1-1"
    assert payload["samples"][0]["ont_key"] == "3"
    assert payload["samples"][0]["rx_dbm"] == -20.5


def test_api_potencias_historico_consultar_ahora_without_valid_samples(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_altiplano_ahora_rama",
        lambda _ratc: {
            "ok": True,
            "timestamp": "2026-04-27 18:00:31",
            "pon": "BA_OLTA_MR01_01-1-1",
            "samples": [{"ont_key": "3", "rx_dbm": None}, {"ont_key": "4", "rx_dbm": None}],
        },
    )
    r = client.post("/api/potencias-historico/MR01-RATC-0-000200/consultar-ahora")
    assert r.status_code == 200
    payload = r.get_json()
    assert len(payload["samples"]) == 2
    assert all(s["rx_dbm"] is None for s in payload["samples"])


def test_api_potencias_historico_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": True,
            "labels": ["2026-04-24 20:00"],
            "datasets": [{"label": "ONT 1", "data": [-18.5]}],
            "pon": "BA_OLTA_MR01_01-1-1",
            "median": -18.5,
            "total_onts": 1,
            "status": "Activo",
            "days": days,
            "rows": [],
            "ont_summary": [
                {
                    "ont_key": "1",
                    "cto": "",
                    "access_id": "1051999888",
                    "last_hist_rx": -18.5,
                    "last_hist_ts": "2026-04-24 20:00",
                }
            ],
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200?days=15")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["pon"] == "BA_OLTA_MR01_01-1-1"
    assert payload["total_onts"] == 1
    assert payload["days"] == 15
    assert payload.get("ont_summary") and payload["ont_summary"][0]["ont_key"] == "1"
    assert payload["ont_summary"][0].get("access_id") == "1051999888"


def test_api_potencias_historico_not_found(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": False,
            "status_code": 404,
            "error": "Rama RATC no encontrada en inventario",
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-999999")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_dashboard_entry_redirect_historico(client):
    r = client.get("/dashboard?tab=potencias-historico", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/potencias-historico")


def test_api_potencias_historico_invalid_days_400(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_potencias_historico_rama",
        lambda _ratc, days=30: {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 7, 15, 30",
        },
    )
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200?days=8")
    assert r.status_code == 400
    assert "days" in r.get_json()["error"]


def test_export_potencias_historico_csv_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_potencias_historico_rama",
        lambda ratc, days=30: {
            "ok": True,
            "csv": "timestamp,objectname,ont,rx_dbm,pon\r\n2026-04-25 00:00,BA_OLTA_X-1-1-1,1,-18.3,BA_OLTA_X-1-1\r\n",
            "ratc": ratc,
            "days": days,
        },
    )
    r = client.get("/dashboard/potencias-historico/export.csv?ratc=MR01-RATC-0-000200&days=7")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    cd = r.headers["Content-Disposition"]
    assert cd.startswith("attachment;")
    assert "potencias_historico_MR01-RATC-0-000200_7d_" in cd
    assert re.search(r"\d{8}_\d{4}\.csv", cd)
    assert "timestamp,objectname,ont,rx_dbm,pon" in r.get_data(as_text=True)


def test_export_potencias_historico_csv_invalid_days_400(client):
    r = client.get("/dashboard/potencias-historico/export.csv?ratc=MR01-RATC-0-000200&days=9")
    assert r.status_code == 400
    assert "days" in r.get_json()["error"]


def test_ont_sort_key_orders_by_cto_then_ont_id():
    from services.historico_potencias import _ont_sort_key

    m = {"1": "SF-Z-200", "2": "SF-Z-100", "3": "SF-Z-100", "10": "SF-Z-100"}
    onts = ["1", "2", "3", "10"]
    assert sorted(onts, key=lambda o: _ont_sort_key(o, m)) == ["2", "3", "10", "1"]


def test_api_potencias_historico_internal_error_includes_request_id(client, monkeypatch):
    import web.routes as routes

    def _boom(_ratc, days=30):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes, "consultar_potencias_historico_rama", _boom)
    r = client.get("/api/potencias-historico/MR01-RATC-0-000200")
    assert r.status_code == 500
    payload = r.get_json()
    assert "error" in payload
    assert "request_id" in payload


def test_historico_last_summary_skips_down_placeholder_rx(monkeypatch):
    from datetime import datetime

    import services.historico_potencias as historico

    monkeypatch.setattr(historico, "_resolver_pon_desde_rama", lambda _ratc: "BA_OLTA_X-1-1")
    monkeypatch.setattr(historico, "_ont_inventory_maps", lambda _rama: ({}, {}))

    rows = [
        (datetime(2026, 5, 29, 8, 31), "BA_OLTA_X:1-1-1-1-1", -22.0),
        (datetime(2026, 5, 29, 11, 31), "BA_OLTA_X:1-1-1-1-1", -100.0),
    ]

    class _Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return rows

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(historico, "db_cursor", lambda: _Ctx())
    payload = historico._consultar_potencias_historico_rama_uncached("MR01-RATC-0-000200", 1)
    assert payload["ok"] is True
    summary = {s["ont_key"]: s for s in payload["ont_summary"]}
    assert summary["1"]["last_hist_rx"] == -22.0
    assert summary["1"]["last_hist_ts"] == "2026-05-29 08:31"


def test_is_historico_rx_down_placeholder():
    import services.historico_potencias as historico

    assert historico._is_historico_rx_down_placeholder(-100.0) is True
    assert historico._is_historico_rx_down_placeholder(-22.0) is False
    assert historico._is_historico_rx_down_placeholder(None) is False


def test_ont_key_from_object_name_strips_altiplano_prefix():
    import services.historico_potencias as historico

    assert historico._ont_key_from_object_name("BA_OLTA_ES01_01:1-1-2-1-4") == "4"
    assert historico._ont_key_from_object_name("BA_OLTA_ES01_01-2-1-6") == "6"
    assert historico._ont_key_from_object_name("") == ""


def test_ont_inventory_maps_uses_object_name_ui(monkeypatch):
    import services.historico_potencias as historico

    rows = [
        (
            "1051999888",
            "IN SERVICE",
            "ES01-FATC-8-105124",
            "ES01-RATC-0-000002",
            None,
            "BA_OLTA_ES01_01-2-1-2",
            None,
            1,
        ),
    ]

    class _Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return rows

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(historico, "db_cursor", lambda: _Ctx())
    cto_map, access_map = historico._ont_inventory_maps("ES01-RATC-0-000002")
    assert cto_map.get("2") == "ES01-FATC-8-105124"
    assert access_map.get("2") == "1051999888"


def test_service_consultar_ahora_excludes_empty_ont_key(monkeypatch):
    import services.historico_potencias as historico

    monkeypatch.setattr(historico, "_resolver_pon_desde_rama", lambda _ratc: "BA_OLTA_X-1-1")
    monkeypatch.setattr(
        historico,
        "consultar_rama_potencias_altiplano_por_ont",
        lambda _ratc: [
            {"ont_key": "", "rx_dbm": None},
            {"ont_key": "   ", "rx_dbm": -19.0},
            {"ont_key": "1", "rx_dbm": -20.0},
        ],
    )
    payload = historico.consultar_potencias_altiplano_ahora_rama("MR01-RATC-0-000200")
    assert payload["ok"] is True
    assert len(payload["samples"]) == 1
    assert payload["samples"][0]["ont_key"] == "1"
    assert payload["samples"][0]["rx_dbm"] == -20.0


def test_service_consultar_ahora_uses_seconds_timestamp(monkeypatch):
    import services.historico_potencias as historico

    monkeypatch.setattr(historico, "_resolver_pon_desde_rama", lambda _ratc: "BA_OLTA_MR01_01-1-1")
    monkeypatch.setattr(
        historico,
        "consultar_rama_potencias_altiplano_por_ont",
        lambda _ratc: [{"ont_key": "3", "rx_dbm": -20.5}],
    )
    payload = historico.consultar_potencias_altiplano_ahora_rama("MR01-RATC-0-000200")
    assert payload["ok"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", payload["timestamp"])
