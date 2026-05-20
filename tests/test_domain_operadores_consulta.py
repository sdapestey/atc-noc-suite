from services.domain import (
    canonical_operador_consulta,
    operadores_consulta_coinciden,
    sort_operadores_consulta,
)


def test_canonical_operador_consulta_mapea_codigos():
    assert canonical_operador_consulta("DIRECTV") == "DIRECTV"
    assert canonical_operador_consulta("METROTEL") == "METROTEL"
    assert canonical_operador_consulta("IPLAN") == "IPLAN"
    assert canonical_operador_consulta("TASA") == "TASA"


def test_canonical_operador_consulta_omite_invalidos():
    assert canonical_operador_consulta("-") is None
    assert canonical_operador_consulta("0") is None
    assert canonical_operador_consulta("None") is None
    assert canonical_operador_consulta("9999") is None


def test_sort_operadores_consulta_solo_validos_y_orden():
    assert sort_operadores_consulta(["-", "ATC", "0", "TASA", "DIRECTV", "None"]) == [
        "TASA",
        "DIRECTV",
        "ATC",
    ]


def test_operadores_consulta_coinciden_alias_directv():
    assert operadores_consulta_coinciden("DIRECTV", "DIRECTV")
    assert not operadores_consulta_coinciden("DIRECTV", "TASA")
