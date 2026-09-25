"""Edge node: reads a sensor and POSTs readings to the gateway over HTTPS.

No local database. A small in-memory retry queue (max 100) absorbs
short gateway outages; anything beyond that is dropped.
"""
import random
import signal
import ssl
import sys
import time
from collections import deque

import requests
from requests.adapters import HTTPAdapter

from common import get_logger, now_ms, dumps

log = get_logger("edge-node")

GATEWAY_URL = "https://127.0.0.1:5001/api/reading"
CERT_PATH = "test_certificate/cert.pem"
SAMPLE_INTERVAL = 1.0
DEVICE_ID = "sensor-001"
PENDING_MAX = 100

_running = True
pending = deque(maxlen=PENDING_MAX)


class TLS12Adapter(HTTPAdapter):
    """Force outbound HTTPS to TLS 1.2 only (simulates an older client)."""
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
    log.info("Shutting down edge node...")


def read_sensor():
    return {
        "device_id": DEVICE_ID,
        "ts": now_ms(),
        "temperature": round(20 + random.uniform(-5, 5), 2),
        "humidity": round(50 + random.uniform(-15, 15), 2),
    }


def try_send(reading) -> bool:
    try:
        r = _session.post(GATEWAY_URL, json=reading, timeout=2)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("Gateway unreachable: %s", e)
        return False


def flush_pending():
    while pending:
        if try_send(pending[0]):
            pending.popleft()
        else:
            break


def main():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    log.info("Edge node %s started, posting to %s (TLS 1.2)", DEVICE_ID, GATEWAY_URL)

    while _running:
        reading = read_sensor()

        if try_send(reading):
            log.info("Sent: %s", dumps(reading))
            flush_pending()
        else:
            if len(pending) == PENDING_MAX:
                log.warning("Queue full — dropping oldest reading")
            pending.append(reading)
            log.info("Queued locally (%d pending)", len(pending))

        time.sleep(SAMPLE_INTERVAL)

    log.info("Edge node stopped, %d readings still queued (lost)", len(pending))


if __name__ == "__main__":
    sys.exit(main())