"""Validación de tokens Access ID / alias para consultas Orquestador Altiplano."""

import services.inventory as inv


def test_access_lookup_token_ok_numeric_and_aliases():
    assert inv._access_lookup_token_ok("1051234567") is True
    assert inv._access_lookup_token_ok("ALCL00010199") is True
    assert inv._access_lookup_token_ok("RES_IP_foo_bar") is True
    assert inv._access_lookup_token_ok("Srvc_loc_2157") is True


def test_is_nfc_tag_token_hex_lengths():
    assert inv._is_nfc_tag_token("04A5E2A22C5E80") is True
    assert inv._is_nfc_tag_token("042DEABADD5F81") is True
    assert inv._is_nfc_tag_token("ALCLF00ABCD12") is False
    assert inv._is_nfc_tag_token("1058516041") is False
    assert inv._is_nfc_tag_token("04A5E2") is False
    assert inv._is_nfc_tag_token("") is False


def test_access_lookup_token_rejects_invalid():
    assert inv._access_lookup_token_ok("") is False
    assert inv._access_lookup_token_ok("no spaces") is False
    assert inv._access_lookup_token_ok("bad@id") is False
    assert inv._access_lookup_token_ok("a" * 300) is False
