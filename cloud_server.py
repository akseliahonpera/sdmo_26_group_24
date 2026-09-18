"""Cloud server: receives readings from gateways, stores & aggregates them."""
from flask import Flask, jsonify, request

from common import get_logger, init_db, dumps

log = get_logger("cloud")
DB_PATH = "cloud.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    edge_id INTEGER,
    device_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    temperature REAL NOT NULL,
    humidity REAL NOT NULL,
    received_at INTEGER NOT NULL DEFAULT (strftime('%s','now')*1000),
    PRIMARY KEY (device_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_device_ts ON readings(device_id, ts);
"""

app = Flask(__name__)
conn = None


@app.route("/api/ingest", methods=["POST"])
def ingest():
    payload = request.get_json(silent=True) or {}
    readings = payload.get("readings", [])
    if not isinstance(readings, list):
        return jsonify({"error": "bad payload"}), 400

    inserted = 0
    for r in readings:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO readings "
                "(edge_id, device_id, ts, temperature, humidity) "
                "VALUES (?, ?, ?, ?, ?)",
                (r["id"], r["device_id"], r["ts"],
                 r["temperature"], r["humidity"]),
            )
            inserted += 1
        except (KeyError, TypeError) as e:
            log.warning("Skipping malformed reading: %s", e)

    conn.commit()
    log.info("Ingested %d/%d readings", inserted, len(readings))
    return jsonify({"accepted": inserted})


@app.route("/api/stats")
def stats():
    rows = conn.execute(
        "SELECT device_id, COUNT(*), AVG(temperature), AVG(humidity), "
        "MIN(ts), MAX(ts) FROM readings GROUP BY device_id"
    ).fetchall()
    return jsonify([
        {
            "device_id": r[0],
            "count": r[1],
            "avg_temperature": round(r[2], 2) if r[2] is not None else None,
            "avg_humidity": round(r[3], 2) if r[3] is not None else None,
            "first_ts": r[4],
            "last_ts": r[5],
        }
        for r in rows
    ])


@app.route("/api/readings/<device_id>")
def readings(device_id):
    limit = min(int(request.args.get("limit", 100)), 1000)
    rows = conn.execute(
        "SELECT ts, temperature, humidity FROM readings "
        "WHERE device_id=? ORDER BY ts DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    return jsonify([
        {"ts": r[0], "temperature": r[1], "humidity": r[2]} for r in rows
    ])


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def main():
    global conn
    conn = init_db(DB_PATH, SCHEMA, check_same_thread=False)
    log.info("Cloud server starting on :5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()