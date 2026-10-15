"""ML-KEM-768 envelope handling for /api/kem/ingest.

Scheme (per request):
  proxy:  (shared, ct) = ML_KEM_768.encaps(server_ek)
          c2s || s2c   = HKDF-SHA256(shared)            # two 32-byte keys
          body         = AES-256-GCM(c2s, nonce, plaintext, aad=ct)
  server: shared = ML_KEM_768.decaps(dk, ct)  -> same keys -> decrypt
          reply is AES-256-GCM under s2c with the same ct as AAD.

Needs:  pip install kyber-py cryptography
"""

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from kyber_py.ml_kem import ML_KEM_768 as KEM

EK_LEN = 1184  # ML-KEM-768 encapsulation key size in bytes
INFO = b"esp32-kem-ingest-v1"
KEY_FILE = Path(os.environ.get("KEM_KEY_FILE", "/app/cloud_server/kem_keys/mlkem768.key"))


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def b64d(s: str) -> bytes:
    return base64.b64decode(s, validate=True)


def _load_or_create_keys():
    """Long-term server keypair, persisted so the public key survives restarts."""
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes()
        return raw[:EK_LEN], raw[EK_LEN:]
    ek, dk = KEM.keygen()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(ek + dk)
    return ek, dk


EK, DK = _load_or_create_keys()


def derive_keys(shared: bytes):
    okm = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=INFO).derive(shared)
    return okm[:32], okm[32:]  # client->server, server->client


def open_envelope(env: dict):
    """Returns (plaintext, s2c_key, ct). Raises on any malformed/forged input.

    ML-KEM decapsulation uses implicit rejection: a tampered ciphertext does
    not error, it yields a random key, so the AES-GCM tag check fails instead.
    """
    if env.get("v") != 1:
        raise ValueError("unsupported version")
    ct = b64d(env["ct"])
    nonce = b64d(env["nonce"])
    data = b64d(env["data"])
    c2s, s2c = derive_keys(KEM.decaps(DK, ct))
    return AESGCM(c2s).decrypt(nonce, data, ct), s2c, ct


def seal_response(s2c: bytes, ct: bytes, plaintext: bytes) -> dict:
    nonce = os.urandom(12)
    return {"nonce": b64e(nonce), "data": b64e(AESGCM(s2c).encrypt(nonce, plaintext, ct))}
