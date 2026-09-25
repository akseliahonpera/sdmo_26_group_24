"""Edge node: simulates a sensor device with a local SQLite buffer."""
import random
import signal
import sys
import time

from common import get_logger, init_db, now_ms, dumps, EDGE_SCHEMA

log = get_logger("edge-node")
DB_PATH = "edge_node.db"
MAX_BUFFER = 500
SAMPLE_INTERVAL = 1.0  # seconds
DEVICE_ID = "sensor-001"

_running = True


def _shutdown(*_):
    global _running
    _running = False
    log.info("Shutting down edge node...")


def read_sensor():
    """Mock sensor read — replace with real hardware call."""
    return {
        "device_id": DEVICE_ID,
        "ts": now_ms(),
        "temperature": round(20 + random.uniform(-5, 5), 2),
        "humidity": round(50 + random.uniform(-15, 15), 2),
    }


def main():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    conn = init_db(DB_PATH, EDGE_SCHEMA)
    log.info("Edge node %s started (db=%s)", DEVICE_ID, DB_PATH)

    while _running:
        reading = read_sensor()

        # Enforce buffer cap: drop oldest unsynced if full
        count = conn.execute(
            "SELECT COUNT(*) FROM readings WHERE synced=0"
        ).fetchone()[0]
        if count >= MAX_BUFFER:
            conn.execute(
                "DELETE FROM readings WHERE id IN "
                "(SELECT id FROM readings WHERE synced=0 ORDER BY id LIMIT 10)"
            )
            log.warning("Buffer full — dropped 10 oldest unsynced readings")

        conn.execute(
            "INSERT INTO readings (device_id, ts, temperature, humidity) "
            "VALUES (?, ?, ?, ?)",
            (reading["device_id"], reading["ts"],
             reading["temperature"], reading["humidity"]),
        )
        conn.commit()
        log.info("Reading: %s", dumps(reading))

        time.sleep(SAMPLE_INTERVAL)

    conn.close()
    log.info("Edge node stopped")


if __name__ == "__main__":
    sys.exit(main())