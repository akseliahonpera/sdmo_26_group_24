import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)

log = logging.getLogger("backend")

app = FastAPI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()

    log.info(
        "REQUEST %s %s client=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )

    response = await call_next(request)

    duration_ms = (time.monotonic() - start) * 1000

    log.info(
        "RESPONSE %s %s status=%d duration=%.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )

    return response

class DeviceData(BaseModel):
    device_id: str
    ts: int
    temperature: int
    humidity: int

@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "OK\n"

@app.post("/api/data", response_class=PlainTextResponse)
async def data(data: DeviceData):
    print("Received:", data)
    return "DATA OK\n"

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "ESP32 backend is running\n"
