"""ML-KEM proxy: ESP32 --(plain POST, local link)--> proxy --(ML-KEM envelope)--> gateway :7879

Run from the repository root:
    python -m kem_proxy.proxy

The server's encapsulation key is PINNED: provision it out of band (file
containing base64 of the raw ek). Do not fetch it over an unauthenticated
channel, or a MITM could substitute its own key.
"""
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

from cloud_server.kem import b64d, seal

GATEWAY_URL = os.environ.get("KEM_GATEWAY_URL", "http://127.0.0.1:7879/api/kem/ingest")
EK_FILE = os.environ.get("SERVER_EK_FILE", str(Path(__file__).parent / "server_ek.b64"))
UPSTREAM_TIMEOUT = float(os.environ.get("KEM_UPSTREAM_TIMEOUT", "3"))

EK = b64d(Path(EK_FILE).read_text().strip())

app = Flask(__name__)


@app.route("/ingest", methods=["POST"])
def ingest():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "bad payload"}), 400

    envelope = seal(EK, payload)
    try:
        r = requests.post(GATEWAY_URL, json=envelope, timeout=UPSTREAM_TIMEOUT)
    except requests.RequestException:
        # 502 tells the ESP32 "no answer" -> it falls back to HTTPS/TLS.
        return jsonify({"error": "upstream unreachable"}), 502

    if r.status_code != 200:
        return jsonify({"error": "upstream rejected", "status": r.status_code}), 502
    return jsonify(r.json()), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=False)
