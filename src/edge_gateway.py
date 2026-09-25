"""Edge gateway: syncs local edge node buffer to the cloud."""
import signal
import sqlite3
import sys
import time

import requests

from common import get_logger, init_db, dumps, EDGE_SCHEMA

log = get_logger("edge-gateway")
DB_PATH = "edge_node.db"
CLOUD_URL = "http://127.0.0.1:5000/api/ingest"
BATCH_SIZE = 50
SYNC_INTERVAL = 3.0
MAX_BACKOFF = 30.0

_running = True


def _shutdown(*_):
    global _running
    _running = False
    log.info("Shutting down gateway...")


def fetch_batch(conn):
    try:
        rows = conn.execute(
            "SELECT id, device_id, ts, temperature, humidity "
            "FROM readings WHERE synced=0 ORDER BY id LIMIT ?",
            (BATCH_SIZE,),
        ).fetchall()
    except sqlite3.OperationalError as e:
        # Table not created yet — edge node hasn't started.
        log.debug("Table not ready yet: %s", e)
        return []
    return [
        {"id": r[0], "device_id": r[1], "ts": r[2],
         "temperature": r[3], "humidity": r[4]}
        for r in rows
    ]


def mark_synced(conn, ids):
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    conn.execute(
        f"UPDATE readings SET synced=1 WHERE id IN ({placeholders})", ids
    )
    conn.commit()


def push_batch(batch):
    resp = requests.post(CLOUD_URL, json={"readings": batch}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def main():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    conn = init_db(DB_PATH, EDGE_SCHEMA)
    backoff = 1.0
    log.info("Gateway started, syncing to %s", CLOUD_URL)

    while _running:
        try:
            batch = fetch_batch(conn)
            if not batch:
                time.sleep(SYNC_INTERVAL)
                backoff = 1.0
                continue

            log.info("Pushing %d readings to cloud...", len(batch))
            result = push_batch(batch)
            mark_synced(conn, [r["id"] for r in batch])
            log.info("Cloud acknowledged: %s", dumps(result))
            backoff = 1.0

        except requests.RequestException as e:
            log.warning("Cloud unreachable (%s) — backing off %.1fs", e, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

        time.sleep(SYNC_INTERVAL)

    conn.close()
    log.info("Gateway stopped")


if __name__ == "__main__":
    sys.exit(main())