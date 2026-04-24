from services.sn_tasa import normalize_tasa_change_sn


def test_normalize_hex_asky_prefix_to_asky_plus_last8():
    assert normalize_tasa_change_sn("41534B5900435645") == "ASKY00435645"


def test_normalize_hex_mstc_prefix_to_mstc_plus_last8():
    assert normalize_tasa_change_sn("4D53544345678954") == "MSTC45678954"


def test_normalize_hex_case_insensitive():
    assert normalize_tasa_change_sn("41534b5900435645") == "ASKY00435645"
    assert normalize_tasa_change_sn("4d53544345678954") == "MSTC45678954"


def test_normalize_trims_whitespace():
    assert normalize_tasa_change_sn("  41534B5900435645  ") == "ASKY00435645"


def test_normalize_already_asky_mstc_twelve_char_unchanged():
    assert normalize_tasa_change_sn("ASKY00435645") == "ASKY00435645"
    assert normalize_tasa_change_sn("mstc45678954") == "MSTC45678954"


def test_normalize_other_hex16_unchanged():
    assert normalize_tasa_change_sn("DEADBEEF00000001") == "DEADBEEF00000001"


def test_normalize_short_string_upper_only():
    assert normalize_tasa_change_sn("alclf00") == "ALCLF00"


def test_normalize_alcl_style_serial_upper():
    assert normalize_tasa_change_sn("alclf00000066") == "ALCLF00000066"
