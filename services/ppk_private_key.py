"""Carga claves PuTTY PPK v3 (sin passphrase) u OpenSSH para SFTP."""
from __future__ import annotations

import base64
import struct
from io import BytesIO, StringIO
from pathlib import Path

import paramiko
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _read_ssh_string(bio: BytesIO) -> bytes:
    length = struct.unpack(">I", bio.read(4))[0]
    return bio.read(length)


def ppk_v3_to_openssh_pem(ppk_path: str | Path) -> str:
    """Convierte PuTTY-User-Key-File-3 RSA sin cifrado a PEM OpenSSH."""
    lines = [ln.strip() for ln in Path(ppk_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    pub_chunks: list[str] = []
    priv_chunks: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("Public-Lines:"):
            count = int(line.split(":", 1)[1])
            pub_chunks = lines[idx + 1 : idx + 1 + count]
            idx += 1 + count
            continue
        if line.startswith("Private-Lines:"):
            count = int(line.split(":", 1)[1])
            priv_chunks = lines[idx + 1 : idx + 1 + count]
            idx += 1 + count
            continue
        idx += 1

    pubbin = base64.b64decode("".join(pub_chunks))
    privbin = base64.b64decode("".join(priv_chunks))
    pubio = BytesIO(pubbin)
    _read_ssh_string(pubio)  # key type
    pubexp = int.from_bytes(_read_ssh_string(pubio), "big")
    modulus = int.from_bytes(_read_ssh_string(pubio), "big")
    privio = BytesIO(privbin)
    privexp = int.from_bytes(_read_ssh_string(privio), "big")
    p = int.from_bytes(_read_ssh_string(privio), "big")
    q = int.from_bytes(_read_ssh_string(privio), "big")
    iqmp = int.from_bytes(_read_ssh_string(privio), "big")
    private_key = rsa.RSAPrivateNumbers(
        p=p,
        q=q,
        d=privexp,
        dmp1=rsa.rsa_crt_dmp1(privexp, p),
        dmq1=rsa.rsa_crt_dmq1(privexp, q),
        iqmp=iqmp,
        public_numbers=rsa.RSAPublicNumbers(e=pubexp, n=modulus),
    ).private_key(default_backend())
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("utf-8")


def load_paramiko_pkey(key_path: str | Path) -> paramiko.PKey:
    """Carga RSA desde .ppk (v3 sin passphrase) o clave OpenSSH/PEM."""
    path = Path(key_path)
    if not path.is_file():
        raise FileNotFoundError(f"Clave SFTP no encontrada: {path}")
    text_head = path.read_text(encoding="utf-8", errors="replace")[:64]
    if text_head.startswith("PuTTY-User-Key-File"):
        pem = ppk_v3_to_openssh_pem(path)
        return paramiko.RSAKey.from_private_key(StringIO(pem))
    return paramiko.RSAKey.from_private_key_file(str(path))
