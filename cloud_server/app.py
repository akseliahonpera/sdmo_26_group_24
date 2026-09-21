"""Cloud server: receives readings from gateways, stores & aggregates them (MySQL).

Run from the repository root (so that `common.py` in the root is importable):

    python -m cloud_server.app
"""
import os
import time
from contextlib import contextmanager
from pathlib import Path

import mysql.connector
from mysql.connector import pooling
from mysql.connector.errors import DataError, IntegrityError
from dotenv import load_dotenv
from flask import Flask, jsonify, request

from common import get_logger, dumps

# Reads cloud_server/.env (the same file docker compose uses).
load_dotenv(Path(__file__).resolve().parent / ".env")

log = get_logger("cloud")

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.environ.get("MYSQL_PORT", "3306")),
    "user": os.environ.get("MYSQL_USER", "cloud_user"),
    "password": os.environ.get("MYSQL_PASSWORD", ""),
    "database": os.environ.get("MYSQL_DATABASE", "cloud_db"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    edge_id     BIGINT,
    device_id   VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    ts          BIGINT NOT NULL,
    temperature DOUBLE NOT NULL,
    humidity    DOUBLE NOT NULL,
    received_at BIGINT NOT NULL,
    PRIMARY KEY (device_id, ts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

app = Flask(__name__)
pool = None


def init_pool(pool_size=10):
    """Create the connection pool and make sure the table exists."""
    global pool
    pool = pooling.MySQLConnectionPool(
        pool_name="cloud_pool",
        pool_size=pool_size,
        pool_reset_session=True,
        **DB_CONFIG,
    )
    with db_cursor(commit=True) as cur:
        cur.execute(SCHEMA)


@contextmanager
def db_cursor(commit=False):
    """Borrow a pooled connection; closing it returns it to the pool."""
    conn = pool.get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@app.route("/api/ingest", methods=["POST"])
def ingest():
    payload = request.get_json(silent=True) or {}
    readings = payload.get("readings", [])
    if not isinstance(readings, list):
        return jsonify({"error": "bad payload"}), 400

    inserted = 0
    received_at = int(time.time() * 1000)
    with db_cursor(commit=True) as cur:
        for r in readings:
            try:
                # ON DUPLICATE KEY UPDATE with a no-op assignment ignores only
                # duplicate keys (INSERT IGNORE would also hide other errors).
                cur.execute(
                    "INSERT INTO readings "
                    "(edge_id, device_id, ts, temperature, humidity, received_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE device_id = device_id",
                    (r["id"], r["device_id"], r["ts"],
                     r["temperature"], r["humidity"], received_at),
                )
                inserted += 1
            except (KeyError, TypeError, DataError, IntegrityError) as e:
                log.warning("Skipping malformed reading: %s", e)

    log.info("Ingested %d/%d readings", inserted, len(readings))
    return jsonify({"accepted": inserted})


@app.route("/api/stats")
def stats():
    with db_cursor() as cur:
        cur.execute(
            "SELECT device_id, COUNT(*), AVG(temperature), AVG(humidity), "
            "MIN(ts), MAX(ts) FROM readings GROUP BY device_id"
        )
        rows = cur.fetchall()
    return jsonify([
        {
            "device_id": r[0],
            "count": r[1],
            "avg_temperature": round(float(r[2]), 2) if r[2] is not None else None,
            "avg_humidity": round(float(r[3]), 2) if r[3] is not None else None,
            "first_ts": r[4],
            "last_ts": r[5],
        }
        for r in rows
    ])


@app.route("/api/readings/<device_id>")
def readings(device_id):
    limit = min(int(request.args.get("limit", 100)), 1000)
    with db_cursor() as cur:
        cur.execute(
            "SELECT ts, temperature, humidity FROM readings "
            "WHERE device_id = %s ORDER BY ts DESC LIMIT %s",
            (device_id, limit),
        )
        rows = cur.fetchall()
    return jsonify([
        {"ts": r[0], "temperature": r[1], "humidity": r[2]} for r in rows
    ])


@app.route("/health")
def health():
    try:
        with db_cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return jsonify({"status": "ok"})
    except mysql.connector.Error as e:
        log.error("Health check failed: %s", e)
        return jsonify({"status": "db_error"}), 503


def main():
    init_pool()
    log.info("Cloud server starting on :5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()