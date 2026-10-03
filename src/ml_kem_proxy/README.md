I want to do ML-KEM proxy to esp32 to update the communications using this kyber-py implementation. https://github.com/GiacomoPope/kyber-py Using kyber-py
ML-KEM. In picture there is the plan for the impelmentation and fallback. 
There are four functions exposed on the `ML_KEM` class which are intended for use:

* `ML_KEM.keygen()`: generate a keypair `(ek, dk)`
* `ML_KEM.key_derive(seed)`: generate a keypair `(ek, dk)` from the provided seed
* `ML_KEM.encaps(ek)`: generate a key and ciphertext pair `(key, ct)`
* `ML_KEM.decaps(dk, ct)`: generate the shared key `key`

Additionally there are few methods for reading and writing both types of keys in the `ml_kem.pkcs` module:

* `ek_to_der`: for serialising the encapsulation key to a DER byte string
* `ek_to_pem`: for serialising the encapsulation key to a PEM string
* `ek_from_der`: for extracting the encapsulation key from a DER encoding
* `ek_from_pem`: for extracting the encapsulation key from a PEM encoding
* `dk_to_der`: for serialising the decapsulation key to a DER byte string
* `dk_to_pem`: for serialising the decapsulation key to a PEM string
* `dk_from_der`: for extracting the decapsulation key from a DER encoding
* `dk_from_pem`: for extracting the decapsulation key from a PEM encoding

Those, together with the `ML_KEM_512`, `ML_KEM_768`, and `ML_KEM_1024` objects comprise the kyber-py library stable API.


# Answer

## How the flow works

1. The ESP32 POSTs plain JSON to the local proxy (`client.py`, 3 s timeout).
2. The proxy calls `ML_KEM_768.encaps(server_ek)`, which gives a fresh `(key, ct)` per message. It derives an AES-256-GCM key from `key` with HKDF and encrypts the payload. It sends `{kid, t, ct, nonce, data}` to the ML-KEM Nginx gateway on `:7879`.
3. Nginx only forwards the message. The Flask server calls `decaps(dk, ct)`, decrypts, and runs the same ingest logic as `/api/ingest`.
4. If the proxy times out or returns non-200, `client.py` falls back to HTTPS on `:7878`. The proxy answers 502 on any upstream failure, so the ESP32 treats it as "no answer".

kyber-py only produces the shared secret. The AES-GCM step comes from the `cryptography` package, so run `pip install cryptography kyber-py`. The server keypair is stored as a 64-byte seed and rebuilt with `key_derive(seed)`. You can export the key to PEM or DER with the `pkcs` helpers if you want interop.

## Changes to your `app.py`

Move the body of `ingest()` into a helper, and add the ML-KEM route next to it:

```python
from cloud_server import kem

KEM_SEED_FILE = os.environ.get("KEM_SEED_FILE", str(CERTS_DIR / "kem.seed"))
EK, DK = kem.load_or_create_keypair(KEM_SEED_FILE)
KID = kem.key_id(EK)

def ingest_payload(payload):
    if not isinstance(payload, dict):
        return jsonify({"error": "bad payload"}), 400
    readings = payload.get("readings", [])
    if not isinstance(readings, list):
        return jsonify({"error": "bad payload"}), 400
    received_at = int(time.time() * 1000)
    rows = []
    for r in readings:
        try:
            rows.append(parse_reading(r, received_at))
        except (KeyError, TypeError, ValueError) as e:
            log.warning("Skipping malformed reading: %s", e)
    with db.SessionLocal.begin() as session:
        db.insert_readings_ignore_duplicates(session, rows)
    log.info("Ingested %d/%d readings", len(rows), len(readings))
    return jsonify({"accepted": len(rows)})

@app.route("/api/ingest", methods=["POST"])
def ingest():
    return ingest_payload(request.get_json(silent=True))

@app.route("/api/kem/ingest", methods=["POST"])
def kem_ingest():
    env = request.get_json(silent=True)
    if not isinstance(env, dict):
        return jsonify({"error": "bad payload"}), 400
    try:
        payload = kem.open_envelope(DK, KID, env)
    except kem.EnvelopeError as e:
        log.warning("Rejected KEM envelope: %s", e)
        return jsonify({"error": "bad envelope"}), 400
    return ingest_payload(payload)
```

Also remove the duplicate `import ssl` at the top. To provision the proxy, base64-encode `EK` once and save it to `kem_proxy/server_ek.b64`. You can print it with `python -c "from cloud_server.app import EK; from cloud_server.kem import b64e; print(b64e(EK))"`.

## Nginx gateway on 7879

```nginx
server {
    listen 7879;
    client_max_body_size 64k;
    location /api/kem/ {
        proxy_pass https://cloud-server:5000;
        proxy_ssl_trusted_certificate /etc/nginx/certs/server.crt;
    }
}
```

## Things to be aware of

- **ML-KEM doesn't authenticate the sender.** Encrypting to a pinned `ek` proves you're talking to the real server, but anyone who has `ek` can send valid envelopes. Your insert-ignore-duplicates makes replays harmless, but fake readings are still possible. Add a per-device HMAC or signature inside the plaintext, or keep mTLS on the gateway.
- **Pin the server key.** Don't fetch `ek` over an unverified channel, or a man-in-the-middle can swap in their own.
- **kyber-py is pure Python and not constant-time.** Its README says it isn't meant for production. That's fine for a prototype and a test harness, but for production you'd want liboqs or a similar library.
- **Running ML-KEM on the ESP32 itself is unrealistic.** That's why the proxy exists, and it should sit on a gateway-class device next to the board.
- **GET requests stay on TLS only.** The ML-KEM route wraps ingest. If you want encrypted GETs, you'd need a request-envelope plus a response key.

For the Tests box in your diagram, a good first test is a `seal()` then `open_envelope()` round-trip. Follow it with tests that tamper with `ct`, `data`, and `t`, and one that kills the proxy to confirm the TLS fallback fires. I can write those next if you'd like.