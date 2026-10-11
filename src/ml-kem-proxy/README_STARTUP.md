# Starting the application (after the initial setup)

This guide is for every run **after** the first-time setup (certificates, `.env`,
firmware build, images built). It assumes Windows with Docker Desktop.

```
ESP32 (QEMU) -> socat :8080 -> ml-kem-proxy :7777 -> edge-gateway (nginx) -> cloud-app :5000 -> MySQL
                                   |  ML-KEM envelope -> :7879 /api/kem/ingest
                                   |  fallback (TLS-backed route) -> :7777 /api/ingest
```

Services (from `docker-compose.yml`): `esp32`, `edge-gateway`, `ml-kem-proxy`,
`cloud-app`, `cloud-mysql`.

---

## 1. Start Docker Desktop

Open Docker Desktop and wait until it shows the engine is running (green status).
Check in a terminal:

```
docker version
```

## 2. Open a terminal in the project folder

The folder that contains `docker-compose.yml` (the `src` folder).
In File Explorer click the address bar, type `powershell`, press Enter.

## 3. Start the stack

```
docker compose up -d
docker compose ps
```

Wait until `cloud-mysql` shows `(healthy)` (up to ~30 s). `cloud-app` starts after that.
All five services should be `Up`.

> No `--build` needed. Only rebuild when code or config changed (see section 9).

## 4. Quick health checks (optional but recommended)

In PowerShell use `curl.exe` (plain `curl` is a different PowerShell command):

```
curl.exe -k https://localhost:5000/health
curl.exe http://localhost:7777/api/kem/public-key
```

- First should return `{"status":"ok"}`.
- Second should return JSON with an `ek` value.

If the second one fails, see Troubleshooting.

## 5. Start the traffic forwarder (socat) in the ESP32 container

`socat` stops whenever the container restarts, so do this every time.

```
docker compose exec esp32 bash
```

Inside the container:

```bash
source /opt/esp/idf/export.sh
cd firmware
pkill socat
nohup socat TCP-LISTEN:8080,bind=0.0.0.0,reuseaddr,fork TCP:ml-kem-proxy:7777 > /tmp/socat.log 2>&1 &
```

The last command should show a listener on port 8080. Only ONE `socat` is needed.

## 6. Start the ESP32 simulator

Still inside the esp32 container, in `/workspace/firmware`:

```bash
qemu-system-xtensa \
    -nographic \
    -icount 3 \
    -machine esp32 \
    -drive file=build/flash.bin,if=mtd,format=raw \
    -nic user,model=open_eth,id=lo0
```

Expected output after a few seconds:

```
Got IP: 10.0.2.15
POST http://10.0.2.2:8080/api/ingest
HTTP status=200 ...
```

Stop the simulator with `Ctrl + A`, then `X`. This does not stop `socat`.

## 7. Watch the system working

Open a second PowerShell window in the project folder:

```
docker compose logs -f ml-kem-proxy cloud-app
```

Normal operation (ML-KEM path):
- `cloud-app` logs `Ingested 1/1 readings`
- `ml-kem-proxy` shows no warnings

Check stored data:

```
curl.exe -k https://localhost:5000/api/stats
```

## 8. Testing the fallback (ML-KEM -> TLS -> back)

1. In `docker-compose.yml`, under `ml-kem-proxy` set `EDGE_KEM_URL: http://edge-gateway:9999` (a dead port).
2. `docker compose up -d ml-kem-proxy`
3. Let the ESP32 send data. The proxy log shows 3 failed ML-KEM attempts, then
   `falling back to TLS`. Readings are still stored via the TLS-backed route.
4. After 60 s the next request is a probe. While the port is still dead you see
   `probe failed, staying on TLS for 60.0s` and the timer restarts.
5. Restore `EDGE_KEM_URL: http://edge-gateway:7879`, run `docker compose up -d ml-kem-proxy`.
   After the next probe the log shows `ML-KEM is working again`.

## 9. When you DO need to rebuild

| What changed | Command |
|---|---|
| `proxy.py` | `docker compose build ml-kem-proxy` then `docker compose up -d ml-kem-proxy` |
| `app.py`, `kem.py`, requirements | `docker compose build cloud-app` then `docker compose up -d cloud-app` |
| nginx config | `docker compose build edge-gateway` then `docker compose up -d edge-gateway` (or `docker compose exec edge-gateway nginx -t` and `nginx -s reload` if the config is mounted) |
| ESP32 firmware | inside esp32 container: `idf.py build` then `idf.py merge-bin -o flash.bin --fill-flash-size 4MB` |
| `.env` values | `docker compose up -d --force-recreate` |

## 10. Stopping

| Goal | Command |
|---|---|
| Pause everything, keep data | `docker compose stop` |
| Stop and remove containers, keep database | `docker compose down` |
| Remove everything INCLUDING database and ML-KEM server key | `docker compose down -v` (destroys data!) |

After `stop` or `down`, repeat from step 3, and do step 5 (socat) again.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `WRONG_VERSION_NUMBER` in proxy log | Proxy uses `https://` towards a plain-HTTP port. `EDGE_TLS_URL` must be `http://edge-gateway:7777` |
| ESP32: `Host is unreachable` once at boot | Normal, happens before the device gets its IP |
| ESP32: timeouts / `EAGAIN` | `socat` not running (step 5), proxy down, or proxy slower than the device timeout |
| `curl.exe http://localhost:7777/api/kem/public-key` returns 404 | nginx config without the KEM routes is loaded; rebuild/reload edge-gateway |
| Same call returns 502/504 | nginx cannot reach `cloud-app` over TLS: check certificate name `group24` and the mounted `ca.crt` |
| `cloud-app` restarts | Check `docker compose logs cloud-app` (missing certs, DB variables, or `kyber-py`/`cryptography` not installed) |
| Compose complains about missing password | `.env` is missing or misnamed (must be exactly `.env`, not `.env.txt`) |
| Proxy says key does not match pin | `KEM_EK_SHA256` is outdated, usually after the server key was regenerated (`down -v`) |
| Payload accepted but nothing stored | Body must be `{"readings":[{"id":..,"device_id":..,"ts":..,"temperature":..,"humidity":..}]}` |
