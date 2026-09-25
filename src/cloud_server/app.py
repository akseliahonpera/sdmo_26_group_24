"""Cloud server: receives readings from gateways, stores & aggregates them.

Run from the repository root (so that `common.py` in the root is importable):

    python -m cloud_server.app
"""
import time

from flask import Flask, jsonify, request
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from cloud_server import db
from cloud_server.utils import get_logger
from cloud_server.models import Reading

log = get_logger("cloud")

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000

app = Flask(__name__)


@app.errorhandler(SQLAlchemyError)
def handle_db_error(e):
    """Any database failure -> 503, so the gateway backs off and retries."""
    log.error("Database error: %s", e)
    return jsonify({"error": "database unavailable"}), 503


def parse_reading(r, received_at):
    """Convert one reading from the payload to a row dict.

    Raises KeyError / TypeError / ValueError if a field is missing or not
    a plain number, same as the checks the original SQLite version did.
    """
    return {
        "edge_id": int(r["id"]),
        "device_id": str(r["device_id"]),
        "ts": int(r["ts"]),
        "temperature": float(r["temperature"]),
        "humidity": float(r["humidity"]),
        "received_at": received_at,
    }


@app.route("/api/ingest", methods=["POST"])
def ingest():
    payload = request.get_json(silent=True)
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

    # One transaction per batch: committed on success, rolled back on error.
    with db.SessionLocal.begin() as session:
        db.insert_readings_ignore_duplicates(session, rows)

    log.info("Ingested %d/%d readings", len(rows), len(readings))
    return jsonify({"accepted": len(rows)})


@app.route("/api/stats")
def stats():
    stmt = (
        select(
            Reading.device_id,
            func.count().label("count"),
            func.avg(Reading.temperature),
            func.avg(Reading.humidity),
            func.min(Reading.ts),
            func.max(Reading.ts),
        )
        .group_by(Reading.device_id)
        .order_by(Reading.device_id)
    )
    with db.SessionLocal() as session:
        rows = session.execute(stmt).all()
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
def device_readings(device_id):
    # Non-numeric ?limit= falls back to the default instead of raising.
    limit = request.args.get("limit", DEFAULT_LIMIT, type=int)
    limit = max(1, min(limit, MAX_LIMIT))
    stmt = (
        select(Reading.ts, Reading.temperature, Reading.humidity)
        .where(Reading.device_id == device_id)
        .order_by(Reading.ts.desc())
        .limit(limit)
    )
    with db.SessionLocal() as session:
        rows = session.execute(stmt).all()
    return jsonify([
        {"ts": r.ts, "temperature": r.temperature, "humidity": r.humidity}
        for r in rows
    ])


@app.route("/health")
def health():
    try:
        with db.SessionLocal() as session:
            session.execute(text("SELECT 1"))
        return jsonify({"status": "ok"})
    except SQLAlchemyError as e:
        log.error("Health check failed: %s", e)
        return jsonify({"status": "db_error"}), 503


def main():
    db.init_db()
    log.info("Cloud server starting on :5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)


if __name__ == "__main__":
    main()
