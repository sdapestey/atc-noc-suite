import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sn_altiplano",
    Path(__file__).resolve().parents[1] / "services" / "sn_altiplano.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
normalize_change_sn = _mod.normalize_change_sn
validate_ont_sn_for_altiplano = _mod.validate_ont_sn_for_altiplano


def test_normalize_sdmc_hex16_to_twelve_char():
    assert normalize_change_sn("53444D435C73B3AF", "DIRECTV") == "SDMC5C73B3AF"


def test_normalize_sdmc_twelve_unchanged():
    assert normalize_change_sn("SDMC5C73B3AF", "DIRECTV") == "SDMC5C73B3AF"


def test_validate_accepts_normalized_sdmc():
    assert validate_ont_sn_for_altiplano("SDMC5C73B3AF") is None


def test_validate_rejects_sixteen_hex_without_known_prefix():
    assert validate_ont_sn_for_altiplano("DEADBEEF00000001") is not None


def test_tasa_still_uses_tasa_rules():
    assert normalize_change_sn("41534B5900435645", "TASA") == "ASKY00435645"
