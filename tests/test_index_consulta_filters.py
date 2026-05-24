"""Filtros de consulta índice: orden de operadores (sin chip de estado en toolbar)."""

from web.routes import (
    _consulta_operadores_union,
    operador_metric_pill_slug,
    sort_consulta_operadores_chips,
)


def test_operador_metric_pill_slug():
    assert operador_metric_pill_slug("TASA") == "tasa"
    assert operador_metric_pill_slug("DIRECTV") == "directv"
    assert operador_metric_pill_slug("  ATC  ") == "atc"


def test_sort_consulta_operadores_chips_solo_validos():
    assert sort_consulta_operadores_chips(["-", "ATC", "TASA", "0", "None"]) == [
        "TASA",
        "ATC",
    ]
    assert sort_consulta_operadores_chips(["DIRECTV", "TASA"]) == ["TASA", "DIRECTV"]


def test_consulta_operadores_union_omite_invalidos():
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
    assert _consulta_operadores_union(consultas) == ["TASA", "ATC"]


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
    assert 'data-chip-operador="-"' not in html
    assert 'data-chip-operador="0"' not in html
    assert 'data-chip-operador="ATC"' in html
    assert 'data-chip-operador="TASA"' in html
