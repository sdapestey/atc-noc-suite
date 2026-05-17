"""Filtros de consulta índice: orden de operadores (sin chip de estado en toolbar)."""

from web.routes import _consulta_operadores_union, sort_consulta_operadores_chips


def test_sort_consulta_operadores_chips_mueve_guion_al_final():
    assert sort_consulta_operadores_chips(["-", "ATC", "TASA"]) == ["ATC", "TASA", "-"]
    assert sort_consulta_operadores_chips(["—", "TASA", "-"]) == ["TASA", "—", "-"]
    assert sort_consulta_operadores_chips(["ATC", "-", "ATC"]) == ["ATC", "-"]


def test_consulta_operadores_union_aplica_orden_guion_al_final():
    consultas = [
        {
            "tabla_cto": [{"OPERADOR": "-"}, {"OPERADOR": "ATC"}],
            "resultado": None,
            "es_rama": False,
        },
        {
            "tabla_cto": [{"OPERADOR": "TASA"}],
            "resultado": None,
            "es_rama": False,
        },
    ]
    assert _consulta_operadores_union(consultas) == ["ATC", "TASA", "-"]


def test_index_masivo_cto_sin_chip_estado_operador_ordenado(client, monkeypatch):
    import web.routes as routes

    def fake_cto(cto):
        if "100001" in cto:
            return [
                {
                    "AID": "1",
                    "OPERADOR": "-",
                    "RAMA": "R1",
                    "PRINCIPAL": "S1",
                    "ONT": "O1",
                    "SN": "S",
                    "STATUS": "FREE",
                    "TX": None,
                    "RX": None,
                },
                {
                    "AID": "2",
                    "OPERADOR": "ATC",
                    "RAMA": "R1",
                    "PRINCIPAL": "S1",
                    "ONT": "O2",
                    "SN": "S",
                    "STATUS": "IN SERVICE",
                    "TX": None,
                    "RX": None,
                },
            ]
        if "100002" in cto:
            return [
                {
                    "AID": "3",
                    "OPERADOR": "TASA",
                    "RAMA": "R2",
                    "PRINCIPAL": "S2",
                    "ONT": "O3",
                    "SN": "S",
                    "STATUS": "RESERVED",
                    "TX": None,
                    "RX": None,
                },
            ]
        return []

    monkeypatch.setattr(routes, "consultar_cto_estructura", fake_cto)
    monkeypatch.setattr(routes, "consultar_cto_coordenadas", lambda _cto: None)

    r = client.post(
        "/",
        data={
            "consulta_modo": "masivo",
            "value_masivo": "TG01-FATC-8-100001\nTG01-FATC-8-100002",
        },
    )
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-chip-fat-status' not in html
    pos_dash = html.find('data-chip-operador="-"')
    pos_atc = html.find('data-chip-operador="ATC"')
    pos_tasa = html.find('data-chip-operador="TASA"')
    assert pos_dash != -1 and pos_atc != -1 and pos_tasa != -1
    assert pos_dash > pos_atc and pos_dash > pos_tasa
