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
    assert "<th>Estado</th><td id=\"s0-estado-id\"" in html
    assert "<th>Estado</th><td id=\"s1-estado-id\"" in html


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


def test_index_get_modo_masivo_empty_shows_masivo_tab(client):
    """GET /?modo=masivo: pestaña masivo y sin resultados (Limpiar redirige aquí en masivo)."""
    r = client.get("/", query_string={"modo": "masivo"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="consulta_modo" value="masivo"' in html
    assert 'class="consulta-section' not in html
    assert 'id="consulta-s0"' not in html
    assert 'id="qm"' in html
