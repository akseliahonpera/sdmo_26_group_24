"""Gateway: receives readings from edge nodes over HTTPS (port 5001),
buffers them in local SQLite, forwards to the cloud over HTTPS (port 5000).
Everything pinned to TLS 1.2.
"""
import signal
import sqlite3
import ssl
import sys
import threading
import time

import requests
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter

from common import get_logger, init_db, EDGE_SCHEMA

log = get_logger("gateway")

DB_PATH = "gateway.db"
CLOUD_URL = "https://127.0.0.1:5000/api/ingest"
CERT_PATH = "test_certificate/cert.pem"
SERVER_CERT = ("test_certificate/cert.pem", "test_certificate/key.pem")

BATCH_SIZE = 50
SYNC_INTERVAL = 3.0
MAX_BACKOFF = 30.0

app = Flask(__name__)
conn = None
conn_lock = threading.Lock()
_running = True


class TLS12Adapter(HTTPAdapter):
    """Force outbound HTTPS to TLS 1.2 only."""
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_verify_locations(CERT_PATH)
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", TLS12Adapter())


def _shutdown(*_):
    global _running
    _running = False
    log.info("Shutting down gateway...")


@app.route("/api/reading", methods=["POST"])
def receive_reading():
    r = request.get_json(silent=True)
    if not r:
        return jsonify({"error": "bad payload"}), 400
    with conn_lock:
        conn.execute(
            "INSERT INTO readings (device_id, ts, temperature, humidity) "
            "VALUES (?, ?, ?, ?)",
            (r["device_id"], r["ts"], r["temperature"], r["humidity"]),
        )
        conn.commit()
    return jsonify({"ok": True})


def fetch_batch():
    with conn_lock:
        rows = conn.execute(
            "SELECT id, device_id, ts, temperature, humidity "
            "FROM readings WHERE synced=0 ORDER BY id LIMIT ?",
            (BATCH_SIZE,),
        ).fetchall()
    return [
        {"id": r[0], "device_id": r[1], "ts": r[2],
         "temperature": r[3], "humidity": r[4]}
        for r in rows
    ]


def mark_synced(ids):
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with conn_lock:
        conn.execute(
            f"UPDATE readings SET synced=1 WHERE id IN ({placeholders})", ids
        )
        conn.commit()


def sync_loop():
    backoff = 1.0
    while _running:
        try:
            batch = fetch_batch()
            if not batch:
                time.sleep(SYNC_INTERVAL)
                backoff = 1.0
                continue

            log.info("Pushing %d readings to cloud...", len(batch))
            resp = _session.post(CLOUD_URL, json={"readings": batch}, timeout=5)
            resp.raise_for_status()
            mark_synced([r["id"] for r in batch])
            log.info("Cloud acknowledged: %s", resp.json())
            backoff = 1.0

        except requests.RequestException as e:
            log.warning("Cloud unreachable — backing off %.1fs (%s)", backoff, e)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

        time.sleep(SYNC_INTERVAL)


def main():
    global conn
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    conn = init_db(DB_PATH, EDGE_SCHEMA, check_same_thread=False)

    t = threading.Thread(target=sync_loop, daemon=True)
    t.start()

    srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    srv_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    srv_ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    srv_ctx.load_cert_chain(certfile=SERVER_CERT[0], keyfile=SERVER_CERT[1])

    log.info("Gateway listening on https://0.0.0.0:5001 (TLS 1.2), syncing to %s",
             CLOUD_URL)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True,
            ssl_context=srv_ctx)


if __name__ == "__main__":
    main()