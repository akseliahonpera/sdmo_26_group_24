"""Shared utilities for edge-cloud system."""
import json
import logging
import sqlite3
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def init_db(path: str, schema: str, check_same_thread: bool = True) -> sqlite3.Connection:
    """Initialize SQLite with WAL mode (good for edge devices).

    Set check_same_thread=False when the connection will be shared
    across threads (e.g. Flask's threaded dev server).
    """
    conn = sqlite3.connect(path, timeout=10, check_same_thread=check_same_thread)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(schema)
    conn.commit()
    return conn


def now_ms() -> int:
    return int(time.time() * 1000)


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))

EDGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    ts INTEGER NOT NULL,
    temperature REAL NOT NULL,
    humidity REAL NOT NULL,
    synced INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_synced ON readings(synced);
"""