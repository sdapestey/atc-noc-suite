"""Radar Degradacion — ranking preventivo de ramas."""
from datetime import date, datetime
from pathlib import Path


def test_compute_rama_metrics_detecta_degradacion_sostenida():
    from services.radar_degradacion import _compute_rama_metrics

    daily = [
        {
            "dia": "2026-05-25",
            "ultima_peor_rx": -22.0,
            "ultima_mediana_rx": -20.0,
            "peor_rx_pico": -22.0,
            "onts_amarillo_rojo": 0,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-05-28",
            "ultima_peor_rx": -24.0,
            "ultima_mediana_rx": -21.5,
            "peor_rx_pico": -24.0,
            "onts_amarillo_rojo": 1,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-01",
            "ultima_peor_rx": -26.5,
            "ultima_mediana_rx": -23.0,
            "peor_rx_pico": -26.5,
            "onts_amarillo_rojo": 3,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-04",
            "ultima_peor_rx": -28.0,
            "ultima_mediana_rx": -24.5,
            "peor_rx_pico": -28.0,
            "onts_amarillo_rojo": 5,
            "onts_down": 1,
            "onts_validas": 9,
            "evento_transitorio_dia": False,
        },
    ]
    out = _compute_rama_metrics(daily, ont_count=10, cto_count=2)
    assert out is not None
    assert out["NIVEL"] in ("CRITICO", "ATENCION")
    assert out["SCORE"] >= 30.0
    assert out["PENDIENTE_PEOR_RX"] < 0
    assert "degradacion_sostenida" in out["SENALES"]


def test_build_timeline_dias_verde_amarillo_rojo():
    from services.radar_degradacion import _build_timeline_dias

    daily = [
        {
            "dia": "2026-05-25",
            "ultima_peor_rx": -22.0,
            "peor_rx_pico": -22.0,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-05-28",
            "ultima_peor_rx": -25.5,
            "peor_rx_pico": -25.5,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-04",
            "ultima_peor_rx": -28.0,
            "peor_rx_pico": -28.0,
            "evento_transitorio_dia": False,
        },
    ]
    tl = _build_timeline_dias(daily)
    assert [d["e"] for d in tl] == ["G", "A", "R"]
    assert tl[0]["r"] == -22.0
    assert tl[2]["r"] == -28.0


def test_build_timeline_dias_rellena_ventana_sin_muestra():
    from services.radar_degradacion import _build_timeline_dias

    daily = [
        {
            "dia": "2026-06-05",
            "ultima_peor_rx": -28.0,
            "peor_rx_pico": -28.0,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-07",
            "ultima_peor_rx": -29.0,
            "peor_rx_pico": -29.0,
            "evento_transitorio_dia": False,
        },
    ]
    tl = _build_timeline_dias(
        daily,
        window_days=7,
        hasta=date(2026, 6, 7),
    )
    assert len(tl) == 7
    assert [d["d"] for d in tl] == [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
        "2026-06-06",
        "2026-06-07",
    ]
    assert [d["e"] for d in tl] == ["N", "N", "N", "N", "R", "N", "R"]


def test_build_timeline_dias_marca_transitorio_recuperado():
    from services.radar_degradacion import _build_timeline_dias

    daily = [
        {
            "dia": "2026-06-07",
            "ultima_peor_rx": -24.9,
            "peor_rx_pico": -31.5,
            "evento_transitorio_dia": True,
        },
    ]
    tl = _build_timeline_dias(daily)
    assert len(tl) == 1
    assert tl[0]["e"] == "G"
    assert tl[0]["t"] == 1
    assert tl[0]["p"] == -31.5


def test_compute_rama_metrics_incluye_timeline():
    from services.radar_degradacion import _compute_rama_metrics

    daily = [
        {
            "dia": "2026-06-01",
            "ultima_peor_rx": -22.0,
            "ultima_mediana_rx": -20.0,
            "peor_rx_pico": -22.0,
            "onts_amarillo_rojo": 0,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-03",
            "ultima_peor_rx": -25.0,
            "ultima_mediana_rx": -21.5,
            "peor_rx_pico": -25.0,
            "onts_amarillo_rojo": 1,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-05",
            "ultima_peor_rx": -26.0,
            "ultima_mediana_rx": -23.0,
            "peor_rx_pico": -26.0,
            "onts_amarillo_rojo": 2,
            "onts_down": 0,
            "onts_validas": 10,
            "evento_transitorio_dia": False,
        },
    ]
    out = _compute_rama_metrics(daily, ont_count=10, cto_count=2)
    assert out is not None
    assert out["TIMELINE"]
    assert [d["e"] for d in out["TIMELINE"]] == ["G", "A", "A"]


def test_compute_rama_metrics_ignora_pico_transitorio_recuperado():
    from services.radar_degradacion import _compute_rama_metrics

    daily = [
        {
            "dia": "2026-06-01",
            "ultima_peor_rx": -24.9,
            "ultima_mediana_rx": -20.5,
            "peor_rx_pico": -24.9,
            "onts_amarillo_rojo": 0,
            "onts_down": 0,
            "onts_validas": 9,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-02",
            "ultima_peor_rx": -24.7,
            "ultima_mediana_rx": -20.6,
            "peor_rx_pico": -24.7,
            "onts_amarillo_rojo": 0,
            "onts_down": 0,
            "onts_validas": 9,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-03",
            "ultima_peor_rx": -25.0,
            "ultima_mediana_rx": -20.5,
            "peor_rx_pico": -25.0,
            "onts_amarillo_rojo": 1,
            "onts_down": 0,
            "onts_validas": 9,
            "evento_transitorio_dia": False,
        },
        {
            "dia": "2026-06-07",
            "ultima_peor_rx": -24.9,
            "ultima_mediana_rx": -20.2,
            "peor_rx_pico": -31.5,
            "onts_amarillo_rojo": 1,
            "onts_down": 0,
            "onts_validas": 9,
            "evento_transitorio_dia": True,
        },
    ]
    out = _compute_rama_metrics(daily, ont_count=11, cto_count=4)
    assert out is not None
    assert out["NIVEL"] == "ESTABLE"
    assert out["ULTIMA_PEOR_RX"] == -24.9
    assert out["PEOR_RX_PICO"] == -31.5
    assert "evento_transitorio" in out["SENALES"]
    assert "recuperacion" in out["SENALES"]
    assert out["SCORE"] < 30.0
    assert out["TIMELINE"][-1]["t"] == 1
    assert out["TIMELINE"][-1]["e"] == "G"


def test_procesar_filas_radar_usa_ultima_muestra_del_dia():
    import services.radar_degradacion as radar

    rows = [
        (datetime(2026, 6, 7, 8, 31), datetime(2026, 6, 7, 8, 31), "v1__t_BA_OLTA_TG02_05-7-8-15", -31.5),
        (datetime(2026, 6, 7, 8, 31), datetime(2026, 6, 7, 17, 31), "v1__t_BA_OLTA_TG02_05-7-8-15", -24.9),
        (datetime(2026, 6, 7, 8, 31), datetime(2026, 6, 7, 8, 31), "v1__t_BA_OLTA_TG02_05-7-8-8", -27.0),
        (datetime(2026, 6, 7, 8, 31), datetime(2026, 6, 7, 17, 31), "v1__t_BA_OLTA_TG02_05-7-8-8", -20.5),
    ]
    ramas_by_pon = {"BA_OLTA_TG02_05-7-8": {"TG02-RATC-0-001047"}}
    ont_keys = {"TG02-RATC-0-001047": {"15", "8"}}
    out = radar._procesar_filas_radar_por_olt(rows, ramas_by_pon, ont_keys)
    row = out["TG02-RATC-0-001047"][0]
    assert row["ultima_peor_rx"] == -24.9
    assert row["peor_rx_pico"] == -31.5
    assert row["evento_transitorio_dia"] is True


def test_procesar_filas_radar_por_olt_agrupa_por_rama():
    import services.radar_degradacion as radar

    rows = [
        (datetime(2026, 6, 1), datetime(2026, 6, 1, 12), "v1__t_BA_OLTA_MR01_01-1-1-19", -22.0),
        (datetime(2026, 6, 3), datetime(2026, 6, 3, 12), "v1__t_BA_OLTA_MR01_01-1-1-19", -24.0),
        (datetime(2026, 6, 5), datetime(2026, 6, 5, 12), "v1__t_BA_OLTA_MR01_01-1-1-19", -28.0),
        (datetime(2026, 6, 5), datetime(2026, 6, 5, 12), "v1__t_BA_OLTA_MR01_01-1-2-6", -29.0),
    ]
    ramas_by_pon = {
        "BA_OLTA_MR01_01-1-1": {"MR01-RATC-0-000100"},
        "BA_OLTA_MR01_01-1-2": {"MR01-RATC-0-000200"},
    }
    ont_keys = {
        "MR01-RATC-0-000100": {"19"},
        "MR01-RATC-0-000200": {"6"},
    }
    out = radar._procesar_filas_radar_por_olt(rows, ramas_by_pon, ont_keys)
    assert len(out["MR01-RATC-0-000100"]) == 3
    assert out["MR01-RATC-0-000200"][-1]["ultima_peor_rx"] == -29.0


def test_radar_degradacion_uncached_ordena_por_score(monkeypatch):
    import services.radar_degradacion as radar

    inv_rows = [
        ("MR01-RATC-0-000100", 8, 2),
        ("MR01-RATC-0-000200", 6, 1),
    ]

    class _Cur:
        def execute(self, *_a, **_k):
            pass

        def fetchall(self):
            return inv_rows

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_a):
            return False

    def _fake_cargar(days, ramas):
        del days, ramas
        return {
            "MR01-RATC-0-000100": [
                {
                    "dia": "2026-06-01",
                    "ultima_peor_rx": -22.0,
                    "ultima_mediana_rx": -22.0,
                    "peor_rx_pico": -22.0,
                    "onts_amarillo_rojo": 0,
                    "onts_down": 0,
                    "onts_validas": 8,
                    "evento_transitorio_dia": False,
                },
                {
                    "dia": "2026-06-03",
                    "ultima_peor_rx": -23.0,
                    "ultima_mediana_rx": -23.0,
                    "peor_rx_pico": -23.0,
                    "onts_amarillo_rojo": 0,
                    "onts_down": 0,
                    "onts_validas": 8,
                    "evento_transitorio_dia": False,
                },
                {
                    "dia": "2026-06-05",
                    "ultima_peor_rx": -24.0,
                    "ultima_mediana_rx": -24.0,
                    "peor_rx_pico": -24.0,
                    "onts_amarillo_rojo": 1,
                    "onts_down": 0,
                    "onts_validas": 8,
                    "evento_transitorio_dia": False,
                },
            ],
            "MR01-RATC-0-000200": [
                {
                    "dia": "2026-06-01",
                    "ultima_peor_rx": -21.0,
                    "ultima_mediana_rx": -21.0,
                    "peor_rx_pico": -21.0,
                    "onts_amarillo_rojo": 0,
                    "onts_down": 0,
                    "onts_validas": 6,
                    "evento_transitorio_dia": False,
                },
                {
                    "dia": "2026-06-03",
                    "ultima_peor_rx": -27.5,
                    "ultima_mediana_rx": -27.5,
                    "peor_rx_pico": -27.5,
                    "onts_amarillo_rojo": 2,
                    "onts_down": 0,
                    "onts_validas": 6,
                    "evento_transitorio_dia": False,
                },
                {
                    "dia": "2026-06-05",
                    "ultima_peor_rx": -29.0,
                    "ultima_mediana_rx": -29.0,
                    "peor_rx_pico": -29.0,
                    "onts_amarillo_rojo": 4,
                    "onts_down": 1,
                    "onts_validas": 5,
                    "evento_transitorio_dia": False,
                },
            ],
        }

    monkeypatch.setattr(radar, "db_cursor", lambda: _Ctx())
    monkeypatch.setattr(radar, "_cargar_muestras_diarias_por_rama", _fake_cargar)
    payload = radar._radar_degradacion_uncached(14, limit=50)
    assert payload["ok"] is True
    assert len(payload["items"]) == 2
    assert payload["items"][0]["RAMA"] == "MR01-RATC-0-000200"
    assert payload["items"][0]["SCORE"] >= payload["items"][1]["SCORE"]
    tl = payload["items"][0]["TIMELINE"]
    assert len(tl) == 14
    ultimo_con_muestra = next(d for d in reversed(tl) if d.get("e") != "N")
    assert ultimo_con_muestra["d"] == "2026-06-05"
    assert ultimo_con_muestra["e"] == "R"


def test_cargar_muestras_reintenta_olt_con_timeout(monkeypatch):
    import services.radar_degradacion as radar
    from psycopg2.errors import QueryCanceled

    calls: list[str] = []

    def fake_fetch(olt, days):
        calls.append(olt)
        if olt == "BA_OLTA_X" and calls.count("BA_OLTA_X") == 1:
            raise QueryCanceled()
        return [(datetime(2026, 6, 7), datetime(2026, 6, 7, 12), "v1__t_BA_OLTA_X-1-1-1", -22.0)]

    monkeypatch.setattr(radar, "_batch_maps_por_ramas", lambda _ramas: (
        {"R1": "BA_OLTA_X-1-1"},
        {"R1": {"1"}},
    ))
    monkeypatch.setattr(radar, "_fetch_radar_rows_por_olt", fake_fetch)

    out = radar._cargar_muestras_diarias_por_rama(7, ["R1"])
    assert "R1" in out
    assert calls.count("BA_OLTA_X") == 2


def test_dashboard_radar_degradacion_get_renders(client):
    r = client.get("/dashboard/radar-degradacion")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Radar Degradacion" in html
    assert 'id="radar-table"' in html
    assert "Trayectoria" in html
    assert "radar-table--compact" in html
    assert 'class="radar-col-trend"' in html
    assert "pend / Δ" in html
    assert 'id="radar-pager"' in html
    assert 'id="radar-page-size"' in html
    assert "dashboard-radar-degradacion.js" in html
    assert "dashboard-radar-degradacion.css" in html
    js = Path("static/js/dashboard-radar-degradacion.js").read_text(encoding="utf-8")
    assert "/api/radar-degradacion" in js
    assert "PEOR_RX_PICO" in js
    assert "radar-page-prev" in js
    assert "pageSize" in js
    assert "_filterItemsClient" in js
    assert "_applyClientFilters" in js
    assert "_buildFetchParams" in js
    assert "_renderTimeline" in js
    assert "radar-timeline" in js
    assert "radar-timeline-wrap" in js
    assert "_rowMetricsTip" in js
    assert "radar-col-trend" in js
    assert "_renderTrendCell" in js
    assert "_trendClass" in js
    assert "radar-actions--compact" in js
    assert 'target="_blank"' in js
    assert "noopener noreferrer" in js
    assert "radarDegradacionStateV1" in js
    assert "createNocPageStateStore" in js
    assert "consultaUrl" in js and "/?q=" in js
    assert "/dashboard/camino-optico?q=" in js
    assert "radar-legend" in html
    assert "radar-th-timeline__hint" in html
    pager_idx = html.index('id="radar-pager"')
    table_idx = html.index('id="radar-table"')
    assert pager_idx < table_idx


def test_api_radar_degradacion_success(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_radar_degradacion",
        lambda **_kw: {
            "ok": True,
            "days": 14,
            "items": [{"RAMA": "MR01-RATC-0-000200", "SCORE": 42.0, "NIVEL": "ATENCION"}],
            "totales": {"RAMAS_CON_TENDENCIA": 1, "CRITICO": 0, "ATENCION": 1, "ESTABLE": 0},
        },
    )
    r = client.get("/api/radar-degradacion?days=14")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["ok"] is True
    assert payload["items"][0]["RAMA"] == "MR01-RATC-0-000200"


def test_api_radar_degradacion_invalid_days(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_radar_degradacion",
        lambda **_kw: {
            "ok": False,
            "status_code": 400,
            "error": "Parámetro days inválido. Valores permitidos: 7, 14, 30",
        },
    )
    r = client.get("/api/radar-degradacion?days=8")
    assert r.status_code == 400


def test_dashboard_entry_redirect_radar(client):
    r = client.get("/dashboard?tab=radar-degradacion", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/dashboard/radar-degradacion")


def test_export_radar_degradacion_csv(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "export_csv_radar_degradacion",
        lambda **_kw: {
            "ok": True,
            "days": 14,
            "csv": "rama,principal,region\nMR01-RATC-0-000200,Moreno,MR01\n",
        },
    )
    r = client.get("/dashboard/radar-degradacion/export.csv?days=14")
    assert r.status_code == 200
    assert "text/csv" in (r.headers.get("Content-Type") or "")
    assert "MR01-RATC-0-000200" in r.get_data(as_text=True)
