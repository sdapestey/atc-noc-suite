"""Clasificación de criterio único — consulta INP Orquestador."""
from web.routes import classify_inp_consulta_query


def test_classify_empty():
    assert classify_inp_consulta_query("") == ("", "", None)


def test_classify_target_hash():
    tgt = "BA_OLTA_ES01_01-12-14-15#3001#gpon"
    assert classify_inp_consulta_query(tgt) == (tgt, "", None)


def test_classify_ba_olta_prefijo():
    dn = "BA_OLTA_ES01_01-9-9-9"
    assert classify_inp_consulta_query(dn) == (dn, "", None)


def test_classify_access_id_numerico():
    assert classify_inp_consulta_query("1051234567") == ("", "1051234567", None)


def test_classify_access_id_alfanumerico():
    assert classify_inp_consulta_query("ALCL00010199") == ("", "ALCL00010199", None)


def test_classify_rechaza_uuid():
    uid = "550e8400-e29b-41d4-a716-446655440000"
    dn, bid, err = classify_inp_consulta_query(uid)
    assert dn == "" and bid == ""
    assert err and "uuid" in err.lower()


def test_classify_invalido():
    _, _, err = classify_inp_consulta_query("no-es-valido@")
    assert err
