"""ML-KEM-768 + AES-256-GCM envelope.

Wire format (JSON):
    {"v": 1, "kid": "<key id>", "t": <ms>, "ct": b64, "nonce": b64, "data": b64}

* ct    = ML-KEM ciphertext (encapsulation of a fresh shared secret per message)
* data  = AES-256-GCM(HKDF(shared secret), plaintext JSON), AAD binds v|kid|t
"""
import base64
import hashlib
import json
import os
import time
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from kyber_py.ml_kem import ML_KEM_768

KEM = ML_KEM_768
MAX_SKEW_MS = 60_000
HKDF_INFO = b"esp32-mlkem-v1"


class EnvelopeError(Exception):
    """Envelope could not be opened (bad format, stale, wrong key, tampered)."""


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode()


def b64d(s: str) -> bytes:
    return base64.b64decode(s, validate=True)


def key_id(ek: bytes) -> str:
    return hashlib.sha256(ek).hexdigest()[:16]


def load_or_create_keypair(seed_file: str):
    """Server long-term keypair, stored as a 64-byte seed (ML-KEM d||z)."""
    path = Path(seed_file)
    if path.exists():
        seed = path.read_bytes()
    else:
        seed = os.urandom(64)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(seed)
    ek, dk = KEM.key_derive(seed)
    return ek, dk


def _derive_key(shared: bytes, kid: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=HKDF_INFO + b"|" + kid.encode(),
    ).derive(shared)


def _aad(kid: str, t: int) -> bytes:
    return f"v1|{kid}|{t}".encode()


def seal(ek: bytes, payload: dict, now_ms: int | None = None) -> dict:
    """Client/proxy side: encapsulate to the server key and encrypt payload."""
    kid = key_id(ek)
    shared, ct = KEM.encaps(ek)
    key = _derive_key(shared, kid)
    nonce = os.urandom(12)
    t = now_ms if now_ms is not None else int(time.time() * 1000)
    data = AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), _aad(kid, t))
    return {"v": 1, "kid": kid, "t": t,
            "ct": b64e(ct), "nonce": b64e(nonce), "data": b64e(data)}


def open_envelope(dk: bytes, kid: str, env: dict, now_ms: int | None = None) -> dict:
    """Server side: decapsulate and decrypt. Raises EnvelopeError on any failure."""
    try:
        if env.get("v") != 1 or env.get("kid") != kid:
            raise EnvelopeError("unsupported version or unknown key id")
        t = int(env["t"])
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if abs(now - t) > MAX_SKEW_MS:
            raise EnvelopeError("stale message")
        # ML-KEM uses implicit rejection: a bad ct yields a random key, so
        # tampering shows up as an AES-GCM tag failure below.
        shared = KEM.decaps(dk, b64d(env["ct"]))
        key = _derive_key(shared, kid)
        plain = AESGCM(key).decrypt(b64d(env["nonce"]), b64d(env["data"]), _aad(kid, t))
        return json.loads(plain)
    except EnvelopeError:
        raise
    except (InvalidTag, KeyError, TypeError, ValueError) as e:
        raise EnvelopeError(type(e).__name__) from e
