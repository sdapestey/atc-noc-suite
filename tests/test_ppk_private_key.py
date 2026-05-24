"""Conversión PPK v3 RSA sin passphrase."""
from pathlib import Path

import pytest

from services.ppk_private_key import ppk_v3_to_openssh_pem


@pytest.mark.skipif(
    not Path(r"C:\Users\Sebastian\Downloads\ATFAR.Noc 3 (1).ppk").is_file(),
    reason="PPK de prueba no disponible en este entorno",
)
def test_ppk_v3_to_pem_local_key():
    pem = ppk_v3_to_openssh_pem(r"C:\Users\Sebastian\Downloads\ATFAR.Noc 3 (1).ppk")
    assert "BEGIN" in pem
    assert "PRIVATE KEY" in pem
