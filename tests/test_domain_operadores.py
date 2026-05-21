from services.domain import nombre_operador


def test_nombre_operador_mapea_codigos_atc():
    assert nombre_operador(2800) == "ATC"
    assert nombre_operador(2805) == "ATC"
    assert nombre_operador(2806) == "ATC"


def test_nombre_operador_fallback_a_string_para_desconocido():
    assert nombre_operador(9999) == "9999"
