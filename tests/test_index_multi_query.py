"""Consulta índice con varios tokens separados por coma."""

import re

def test_index_multiple_access_ids_two_sections(client, monkeypatch):
    import web.routes as routes

    def fake_detalle(aid):
        base = {
            "OPERADOR": "TASA",
            "Status": "IN SERVICE",
            "CTO": "TG01-FATC-8-100987",
            "RAMA": "TG01-RATC-0-000308",
            "ONT": "BA_OLTA_TG01_02-2-15-8",
            "SN": "04EDFBADD5F81",
            "TX": None,
            "RX": None,
            "fuente_detalle": "bajada_inventario",
        }
        if aid == "105":
            return {**base, "AID": "105"}
        if aid == "106":
            return {**base, "AID": "106"}
        return None

    monkeypatch.setattr(routes, "consultar_access_id_detalle_desde_bajada_inventario", fake_detalle)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post(
        "/",
        data={"consulta_modo": "masivo", "value_masivo": "105, 106"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-query-token="105"' in html
    assert 'data-query-token="106"' in html
    assert "<th>TX (dBm)</th><td id=\"s0-tx\"" in html
    assert "<th>TX (dBm)</th><td id=\"s1-tx\"" in html
    assert "estado-id" not in html


def test_index_masivo_panel_semaforo_sin_badge_filas(client, monkeypatch):
    """Panel masivo: sin badge de filas; semáforo RX se difiere (Altiplano vía /potencias en cliente)."""
    import web.routes as routes

    called = []

    def boom_rama(_rama):
        called.append("dashboard_rama")
        return {
            "__dashboard_resumen__": {"ROJAS": 1, "AMARILLAS": 2, "VERDES": 3},
        }

    monkeypatch.setattr(
        routes,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-100987": [
                {
                    "AID": "105",
                    "OPERADOR": "TASA",
                    "PRINCIPAL": "Tigre",
                    "ONT": "ONT-1",
                    "SN": "SN1",
                    "STATUS": "IN SERVICE",
                    "TX": None,
                    "RX": None,
                }
            ]
        },
    )
    monkeypatch.setattr(routes, "consultar_dashboard_rama", boom_rama)

    r = client.post(
        "/",
        data={"consulta_modo": "masivo", "value_masivo": "TG01-RATC-0-000308, TG01-RATC-0-000309"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    assert not called, "no debe consultar Altiplano para semáforo en el POST masivo"
    assert not re.search(r'class="badge">\s*\d+\s+fila', html, re.I)
    assert "consulta-semaforo-pending" in html
    assert 'data-semaforo="rojo"' in html
    assert 'data-semaforo="amarillo"' in html
    assert 'data-semaforo="verde"' in html


def test_index_comma_only_shows_hint(client):
    r = client.post("/", data={"consulta_modo": "masivo", "value_masivo": ", ,"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "No se interpretó ningún término" in html


def test_index_individual_rama_defer_altiplano_semaforo(client, monkeypatch):
    """Consulta individual RAMA: inventario en el POST; potencias/semáforo vía /potencias en cliente."""
    import web.routes as routes

    called = []

    def boom_rama(_rama):
        called.append("dashboard_rama")
        return {
            "__dashboard_resumen__": {"ROJAS": 9, "AMARILLAS": 0, "VERDES": 0},
        }

    monkeypatch.setattr(
        routes,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-100987": [
                {
                    "AID": "105",
                    "OPERADOR": "TASA",
                    "PRINCIPAL": "Tigre",
                    "RAMA": "TG01-RATC-0-000308",
                    "ONT": "ONT-1",
                    "STATUS": "IN SERVICE",
                    "TX": None,
                    "RX": None,
                }
            ]
        },
    )
    monkeypatch.setattr(routes, "consultar_dashboard_rama", boom_rama)

    r = client.post(
        "/",
        data={"consulta_modo": "individual", "value": "TG01-RATC-0-000308"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    assert not called, "no debe consultar Altiplano para semáforo en el POST individual"
    assert "consulta-semaforo-pending" in html
    assert 'data-query-token="TG01-RATC-0-000308"' in html


def test_index_individual_rejects_multiple_tokens(client):
    r = client.post("/", data={"consulta_modo": "individual", "value": "105, 106"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "consulta individual" in html.lower()
    assert 'data-query-token="105"' not in html


def test_index_get_empty_shows_welcome_no_result_sections(client):
    """GET / sin POST: sin bloques de resultado (Limpiar redirige aquí en modo individual)."""
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<strong>Individual:</strong>" in html
    assert 'class="consulta-section' not in html
    assert 'id="consulta-s0"' not in html


def test_index_masivo_multi_rama_shows_cto_ont_totals(client, monkeypatch):
    """Consulta masiva con varias RAMAs: pills CTO/ONT con suma total junto a los botones."""
    import web.routes as routes

    def rama_struct(rama):
        if rama == "TG01-RATC-0-000308":
            return {
                "TG01-FATC-8-100987": [
                    {"AID": "105", "OPERADOR": "TASA", "ONT": "ONT-1", "STATUS": "IN SERVICE"},
                    {"AID": "108", "OPERADOR": "TASA", "ONT": "ONT-F", "STATUS": "FREE"},
                ],
                "TG01-FATC-8-100988": [
                    {"AID": "106", "OPERADOR": "ATC", "ONT": "ONT-2", "STATUS": "IN SERVICE"},
                ],
            }
        if rama == "TG01-RATC-0-000309":
            return {
                "TG01-FATC-8-100989": [{"AID": "107", "OPERADOR": "TASA", "ONT": "ONT-3", "STATUS": "IN SERVICE"}],
            }
        return {}

    monkeypatch.setattr(routes, "consultar_rama_estructura", rama_struct)

    r = client.post(
        "/",
        data={
            "consulta_modo": "masivo",
            "value_masivo": "TG01-RATC-0-000308\nTG01-RATC-0-000309",
        },
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="consulta-masivo-rama-summary"' in html
    assert "Ramas consultadas:" in html
    assert 'id="consulta-masivo-ramas-total">2</span>' in html
    assert 'id="consulta-masivo-ramas-up">0</span>' in html
    assert 'id="consulta-masivo-ramas-down">0</span>' in html
    assert 'class="consulta-masivo-totals dashboard-tree-selection"' in html
    assert 'olt-metric-pill--cto' in html
    assert 'olt-metric-pill--ont' in html
    assert ">3</span> <span class=\"dashboard-metric-pill__l olt-metric-pill__l\">CTO</span>" in html
    assert ">3</span> <span class=\"dashboard-metric-pill__l olt-metric-pill__l\">ONT</span>" in html
    assert 'olt-metric-pill--op-tasa' in html
    assert 'olt-metric-pill--op-atc' in html
    assert 'olt-metric-pill__l">TASA</span>' in html
    assert 'olt-metric-pill__n">2</span>' in html
    assert 'olt-metric-pill__l">ATC</span>' in html
    assert 'olt-metric-pill__n">1</span>' in html
    assert 'olt-selection-operadores-label">Operador:</span>' not in html
    assert 'consulta-masivo-totals__op-n' not in html
    assert 'id="consulta-masivo-pager"' in html
    assert (
        'id="consulta-masivo-pager" aria-label="Paginación de resultados" hidden'
        in html
    )
    assert 'value="10" selected' in html
    assert "consulta-masivo-pager__size-row" in html
    assert '<details class="consulta-panel">' in html
    assert '<details class="consulta-panel" open>' not in html
    assert "consulta-cto-panel" in html


def test_index_rama_ont_badge_counts_only_in_service(client, monkeypatch):
    """Badges ONT en RAMA/CTO cuentan solo filas IN SERVICE (no FREE/RESERVED)."""
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_rama_estructura",
        lambda _rama: {
            "TG01-FATC-8-100987": [
                {"AID": "105", "OPERADOR": "TASA", "ONT": "ONT-1", "STATUS": "IN SERVICE"},
                {"AID": "106", "OPERADOR": "TASA", "ONT": "ONT-2", "STATUS": "FREE"},
                {"AID": "107", "OPERADOR": "TASA", "ONT": "ONT-3", "STATUS": "RESERVED"},
            ],
            "TG01-FATC-8-100988": [
                {"AID": "108", "OPERADOR": "TASA", "ONT": "ONT-4", "STATUS": "IN SERVICE"},
            ],
        },
    )

    r = client.post(
        "/",
        data={"consulta_modo": "individual", "value": "TG01-RATC-0-000308"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)

    assert html.count('title="ONT IN SERVICE">ONT 2</span>') == 1
    assert html.count('title="ONT IN SERVICE">ONT 1</span>') == 2


def test_index_cto_ont_badge_counts_only_in_service(client, monkeypatch):
    import web.routes as routes

    monkeypatch.setattr(
        routes,
        "consultar_cto_estructura",
        lambda _cto: [
            {"AID": "105", "OPERADOR": "TASA", "ONT": "ONT-1", "STATUS": "IN SERVICE"},
            {"AID": "106", "OPERADOR": "TASA", "ONT": "ONT-2", "STATUS": "FREE"},
        ],
    )

    r = client.post(
        "/",
        data={"consulta_modo": "individual", "value": "TG01-FATC-8-100987"},
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'title="ONT IN SERVICE">ONT 1</span>' in html
    assert 'ONT 2</span>' not in html or 'title="ONT IN SERVICE">ONT 2</span>' not in html


def test_index_get_modo_masivo_empty_shows_masivo_tab(client):
    """GET /?modo=masivo: pestaña masivo y sin resultados (Limpiar redirige aquí en masivo)."""
    r = client.get("/", query_string={"modo": "masivo"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="consulta_modo" value="masivo"' in html
    assert 'class="consulta-section' not in html
    assert 'id="consulta-s0"' not in html
    assert 'id="qm"' in html


def test_index_mode_tab_switch_clears_via_navigate(client):
    """Al cambiar Individual ↔ Masivo se recarga la consulta vacía (misma lógica que Limpiar)."""
    from pathlib import Path

    js = Path("static/js/consulta-index.js").read_text(encoding="utf-8")
    assert "function consultaNavigateClear(m)" in js
    assert "consultaNavigateClear(m)" in js
    assert "modoEl.value === m" in js
