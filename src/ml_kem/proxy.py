"""ML-KEM proxy: sits between the emulated ESP32 and the Nginx edge gateway.

ESP32 --(plain POST, local hop)--> proxy --(ML-KEM envelope)--> edge :KEM_PORT --> /api/kem/ingest
                                        \--(fallback to the TLS-backed route)--> edge :7777 --> /api/ingest

Policy:
  * ML-KEM is the default.
  * 3 consecutive ML-KEM failures -> switch to TLS.
  * 60 s later, the next request is used as a probe: try ML-KEM once.
      success -> back to ML-KEM;  failure -> stay on TLS and restart the 60 s timer.
  * A request is never dropped: if ML-KEM fails it is sent over TLS right away.

Needs:  pip install kyber-py cryptography requests
"""

import hashlib
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from kyber_py.ml_kem import ML_KEM_768 as KEM

import base64

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s proxy: %(message)s")
log = logging.getLogger("proxy")

EDGE_HOST = os.environ.get("EDGE_HOST", "edge-gateway")
EDGE_KEM_URL = os.environ.get("EDGE_KEM_URL", f"http://{EDGE_HOST}:7879")   # envelope is already encrypted
EDGE_TLS_URL = os.environ.get("EDGE_TLS_URL", f"https://{EDGE_HOST}:7777")
TLS_VERIFY = os.environ.get("EDGE_CA_FILE", True)        # path to CA/cert, or True for system CAs
PINNED_EK_SHA256 = os.environ.get("KEM_EK_SHA256")       # optional hex pin of the server public key
LISTEN_PORT = int(os.environ.get("PROXY_PORT", "7777"))
TIMEOUT = float(os.environ.get("PROXY_TIMEOUT", "5"))

MAX_FAILS = 3
RETRY_AFTER = 60.0
INFO = b"esp32-kem-ingest-v1"


# --------------------------------------------------------------------------- failover state
class Failover:
    def __init__(self, max_fails=MAX_FAILS, retry_after=RETRY_AFTER, clock=time.monotonic):
        self.max_fails, self.retry_after, self.clock = max_fails, retry_after, clock
        self.lock = threading.Lock()
        self.mode = "kem"          # "kem" | "tls"
        self.fails = 0
        self.next_probe = 0.0
        self.probing = False

    def begin(self) -> str:
        """'kem' = normal, 'probe' = single ML-KEM test while on TLS, 'tls' = TLS only."""
        with self.lock:
            if self.mode == "kem":
                return "kem"
            if not self.probing and self.clock() >= self.next_probe:
                self.probing = True
                return "probe"
            return "tls"

    def success(self):
        with self.lock:
            if self.mode != "kem":
                log.info("ML-KEM is working again, leaving TLS fallback")
            self.mode, self.fails, self.probing = "kem", 0, False

    def failure(self, was_probe: bool) -> bool:
        """Record a failure. Returns True if no more ML-KEM attempts should be made now."""
        with self.lock:
            if was_probe:
                self.probing = False
                self.next_probe = self.clock() + self.retry_after
                log.warning("ML-KEM probe failed, staying on TLS for %ss", self.retry_after)
                return True
            self.fails += 1
            if self.fails >= self.max_fails:
                self.mode, self.next_probe = "tls", self.clock() + self.retry_after
                log.warning("ML-KEM failed %d times, falling back to TLS", self.fails)
                return True
            return False


state = Failover()


# --------------------------------------------------------------------------- ML-KEM transport
def b64e(b): return base64.b64encode(b).decode()
def b64d(s): return base64.b64decode(s, validate=True)


_ek = None
_ek_lock = threading.Lock()


def get_ek(refresh=False) -> bytes:
    """Server public key, fetched over the TLS route and cached."""
    global _ek
    with _ek_lock:
        if _ek is None or refresh:
            r = requests.get(f"{EDGE_TLS_URL}/api/kem/public-key", timeout=TIMEOUT, verify=TLS_VERIFY)
            r.raise_for_status()
            ek = b64d(r.json()["ek"])
            if PINNED_EK_SHA256 and hashlib.sha256(ek).hexdigest() != PINNED_EK_SHA256.lower():
                raise ValueError("server ML-KEM public key does not match pin")
            _ek = ek
        return _ek


def kem_post(plaintext: bytes) -> bytes:
    """Encrypt, POST to /api/kem/ingest, decrypt the reply. Raises on any problem."""
    ek = get_ek()
    shared, ct = KEM.encaps(ek)
    okm = HKDF(algorithm=hashes.SHA256(), length=64, salt=None, info=INFO).derive(shared)
    c2s, s2c = okm[:32], okm[32:]
    nonce = os.urandom(12)
    env = {
        "v": 1, "alg": "ML-KEM-768", "ct": b64e(ct), "nonce": b64e(nonce),
        "data": b64e(AESGCM(c2s).encrypt(nonce, plaintext, ct)),
    }
    try:
        r = requests.post(f"{EDGE_KEM_URL}/api/kem/ingest", json=env, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        return AESGCM(s2c).decrypt(b64d(j["nonce"]), b64d(j["data"]), ct)  # also authenticates the server
    except Exception:
        # Could be a rotated server key: refetch it next time (best effort).
        try:
            get_ek(refresh=True)
        except Exception:
            pass
        raise


def tls_request(method: str, path: str, body: bytes, headers: dict):
    r = requests.request(
        method, f"{EDGE_TLS_URL}{path}", data=body or None, timeout=TIMEOUT, verify=TLS_VERIFY,
        headers={"Content-Type": headers.get("Content-Type", "application/json")},
    )
    return r.status_code, r.content, r.headers.get("Content-Type", "application/json")


def ingest_with_failover(body: bytes, headers: dict):
    mode = state.begin()
    if mode in ("kem", "probe"):
        for attempt in range(1 if mode == "probe" else MAX_FAILS):
            try:
                reply = kem_post(body)
                state.success()
                return 200, reply, "application/json"
            except Exception as e:
                log.warning("ML-KEM attempt failed (%s): %s", mode, e)
                if state.failure(was_probe=(mode == "probe")):
                    break
                time.sleep(0.5)
    return tls_request("POST", "/api/ingest", body, headers)   # fallback, nothing is lost


# --------------------------------------------------------------------------- local HTTP face for the ESP32
class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        try:
            if method == "POST" and self.path.split("?")[0] == "/api/ingest":
                self._reply(*ingest_with_failover(body, self.headers))
            else:  # GETs and everything else: plain HTTPS passthrough
                self._reply(*tls_request(method, self.path, body, self.headers))
        except Exception as e:
            log.error("upstream unavailable: %s", e)
            self._reply(502, json.dumps({"error": "upstream unavailable"}).encode(), "application/json")

    def do_POST(self): self._handle("POST")
    def do_GET(self): self._handle("GET")
    def log_message(self, *a): pass


if __name__ == "__main__":
    log.info("ML-KEM proxy listening on :%d (kem=%s tls=%s)", LISTEN_PORT, EDGE_KEM_URL, EDGE_TLS_URL)
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
