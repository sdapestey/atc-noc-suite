from services.domain import natural_sort_key_str, nombre_operador


def test_natural_sort_key_str_mezcla_aids_numericos_y_alias():
    aids = ["1051573192", "Srvc_loc_1162", "99223497"]
    assert sorted(aids, key=natural_sort_key_str) == [
        "99223497",
        "1051573192",
        "Srvc_loc_1162",
    ]


def test_nombre_operador_mapea_codigos_atc():
    assert nombre_operador(2800) == "ATC"
    assert nombre_operador(2805) == "ATC"
    assert nombre_operador(2806) == "ATC"


def test_nombre_operador_fallback_a_string_para_desconocido():
    assert nombre_operador(9999) == "9999"
