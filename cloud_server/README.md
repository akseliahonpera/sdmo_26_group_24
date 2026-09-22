# Cloud Server (Flask + SQLAlchemy + MySQL)

Receives sensor readings from edge gateways, stores them in MySQL and serves aggregates over a small JSON API.
MySQL runs in Docker; the Flask app runs directly on your machine.

All files specific to this service live in this folder. Shared code (`common.py`) lives in the repo root.

## Prerequisites

- [Docker Desktop](https://docs.docker.com/get-started/get-docker/) (on Windows it needs WSL 2, which the installer sets up) and make sure it's **running**
- Python 3.9+
- Git

Check your tools:

```bash
docker --version
docker compose version
python --version      # use python3 on macOS/Linux
```

## Quick start

Run these from the **repository root** unless stated otherwise.

```bash
# 1. Clone
git clone <REPO_URL>
cd <REPO_FOLDER>

# 2. Create your local config (edit the passwords if you like)
cp cloud_server/.env.example cloud_server/.env      # Windows cmd: copy cloud_server\.env.example cloud_server\.env

# 3. Start MySQL and wait until it's healthy (first start takes ~30s)
cd cloud_server
docker compose up -d --wait
cd ..

# 4. Create a virtual environment (in the repo root) and install dependencies
python -m venv .venv
source .venv/bin/activate                            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r cloud_server/requirements.txt

# 5. Run the server from the repo root (creates the table automatically)
python -m cloud_server.app
```

The server listens on http://localhost:5000. Check it with `curl localhost:5000/health`.

## Configuration

Settings are read from `cloud_server/.env` (copied from `.env.example`). The same file configures the MySQL container and the app.

| Variable | Default | Used by | Description |
|---|---|---|---|
| `MYSQL_ROOT_PASSWORD` | – (required) | Docker | Root password of the MySQL container |
| `MYSQL_DATABASE` | `cloud_db` | Docker + app | Database name |
| `MYSQL_USER` | `cloud_user` | Docker + app | Application user |
| `MYSQL_PASSWORD` | – (required) | Docker + app | Application user's password |
| `MYSQL_HOST` | `127.0.0.1` | app | MySQL host |
| `MYSQL_PORT` | `3306` | Docker + app | Host port Docker publishes, and the port the app connects to |

## API reference

Base URL: `http://localhost:5000`. All endpoints accept and return JSON.
There is **no authentication**, so only run this on a trusted network.

| Method | Path | Purpose |
|---|---|---|
| `POST` | [`/api/ingest`](#post-apiingest) | Store a batch of readings (used by the edge gateway) |
| `GET` | [`/api/stats`](#get-apistats) | Per-device aggregates |
| `GET` | [`/api/readings/<device_id>`](#get-apireadingsdevice_id) | Latest readings of one device |
| `GET` | [`/health`](#get-health) | Liveness and database check |

Timestamps (`ts`, `first_ts`, `last_ts`) are Unix epoch time in **milliseconds**.

### POST /api/ingest

Stores a batch of readings. This is what the edge gateway calls.

**Request body**

```json
{
  "readings": [
    {"id": 1, "device_id": "dev-a", "ts": 1758400000000, "temperature": 21.5, "humidity": 40.2},
    {"id": 2, "device_id": "dev-a", "ts": 1758400003000, "temperature": 21.7, "humidity": 40.0}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `id` | integer | Row id in the edge node's local database (informational) |
| `device_id` | string, 1–64 chars | Sensor/device identifier. Case-sensitive |
| `ts` | integer | Measurement time, epoch milliseconds. Together with `device_id` it uniquely identifies a reading |
| `temperature` | number | |
| `humidity` | number | |

**Behaviour**

- **Idempotent:** a reading whose `(device_id, ts)` already exists is silently ignored, so a gateway can safely re-send a batch (for example after a crash before it marked the batch as synced).
- **Malformed readings are skipped**, not rejected: a reading with a missing field or a non-numeric `id`/`ts`/`temperature`/`humidity` is logged and dropped, and the rest of the batch is still stored.
- **One transaction per batch:** either all valid readings of a batch are stored or none are.
- An object without a `readings` key, or with an empty list, is accepted as an empty batch.

**Responses**

| Status | Body | When |
|---|---|---|
| `200` | `{"accepted": 2}` | Batch processed. `accepted` is the number of *valid* readings (new or duplicate). If it is lower than the number sent, some were malformed |
| `400` | `{"error": "bad payload"}` | Body is not a JSON object, or `readings` is not a list |
| `503` | `{"error": "database unavailable"}` | The database could not be reached or the write failed. Nothing was stored; the client should retry |

### GET /api/stats

Returns aggregates for every device, sorted by `device_id`. Returns `[]` when there is no data yet.

**Response `200`**

```json
[
  {
    "device_id": "dev-a",
    "count": 2,
    "avg_temperature": 21.6,
    "avg_humidity": 40.1,
    "first_ts": 1758400000000,
    "last_ts": 1758400003000
  }
]
```

| Field | Description |
|---|---|
| `device_id` | Device identifier |
| `count` | Number of stored readings |
| `avg_temperature`, `avg_humidity` | Averages, rounded to 2 decimals |
| `first_ts`, `last_ts` | Oldest and newest reading timestamp (epoch ms) |

Errors: `503` `{"error": "database unavailable"}`.

### GET /api/readings/&lt;device_id&gt;

Returns the most recent readings of one device, **newest first**.

| Query parameter | Default | Description |
|---|---|---|
| `limit` | `100` | Max number of readings to return. Clamped to the range 1–1000; a non-numeric value falls back to the default |

**Response `200`**

```json
[
  {"ts": 1758400003000, "temperature": 21.7, "humidity": 40.0},
  {"ts": 1758400000000, "temperature": 21.5, "humidity": 40.2}
]
```

- An unknown device returns `[]` (not `404`).
- `device_id` is case-sensitive; URL-encode special characters.
- Errors: `503` `{"error": "database unavailable"}`.

### GET /health

Checks that the server is up **and** can reach the database. Useful for monitoring and container health checks.

| Status | Body | When |
|---|---|---|
| `200` | `{"status": "ok"}` | Server and database are reachable |
| `503` | `{"status": "db_error"}` | The database check failed |

### Examples

macOS / Linux / Git Bash:

```bash
# Store a batch
curl -X POST localhost:5000/api/ingest -H "Content-Type: application/json" \
  -d '{"readings":[{"id":1,"device_id":"dev-a","ts":1758400000000,"temperature":21.5,"humidity":40.2}]}'

# Aggregates for all devices
curl localhost:5000/api/stats

# Last 10 readings of dev-a
curl "localhost:5000/api/readings/dev-a?limit=10"

# Health
curl localhost:5000/health
```

Windows PowerShell (`curl` there is an alias for a different command, so use `Invoke-RestMethod`):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/ingest `
  -ContentType "application/json" `
  -Body '{"readings":[{"id":1,"device_id":"dev-a","ts":1758400000000,"temperature":21.5,"humidity":40.2}]}'

Invoke-RestMethod http://localhost:5000/api/stats
Invoke-RestMethod "http://localhost:5000/api/readings/dev-a?limit=10"
Invoke-RestMethod http://localhost:5000/health
```

## Database layer (ORM)

The service uses the **SQLAlchemy 2.0 ORM** with the `mysql-connector-python` driver.

| File | Responsibility |
|---|---|
| `models.py` | The `Reading` model (table definition) |
| `db.py` | Connection URL from the environment, engine + connection pool, session factory, table creation, duplicate-safe bulk insert |
| `app.py` | Flask routes; they query through ORM sessions and never write SQL strings |

**Table `readings`**

| Column | Type | Notes |
|---|---|---|
| `device_id` | `VARCHAR(64)`, binary collation | Primary key (part 1). Case-sensitive |
| `ts` | `BIGINT` | Primary key (part 2). Epoch ms from the edge node |
| `edge_id` | `BIGINT`, nullable | Row id on the edge node |
| `temperature` | `DOUBLE` | |
| `humidity` | `DOUBLE` | |
| `received_at` | `BIGINT` | Epoch ms, set by the server on arrival (not exposed by the API) |

Things worth knowing:

- **Tables are created automatically** on startup with `create_all()`. It only creates *missing* tables and never alters existing ones. When you change the model later, either use a migration tool such as [Alembic](https://alembic.sqlalchemy.org/), or during development reset the database with `docker compose down -v`.
- **Connection pool:** 10 persistent connections plus up to 10 extra under burst load. Dead connections are detected (`pool_pre_ping`) and replaced, so restarting MySQL doesn't require restarting the app.
- **Duplicate handling:** the ORM has no portable "insert or ignore", so `db.insert_readings_ignore_duplicates()` uses MySQL's `INSERT ... ON DUPLICATE KEY UPDATE` with a no-op update, which skips *only* duplicate keys.
- **Validation happens in Python** (`parse_reading()` in `app.py`) before the database is touched, so the database only sees clean data.

## Look inside the database

From the `cloud_server/` folder:

```bash
docker compose exec mysql mysql -u cloud_user -p cloud_db
# enter the MYSQL_PASSWORD from your .env, then:
#   SELECT * FROM readings;
```

## Everyday commands

Run the Docker commands from the `cloud_server/` folder.

| Task | Command |
|---|---|
| Start MySQL | `docker compose up -d --wait` |
| Stop MySQL (keeps data) | `docker compose stop` |
| Stop and remove container (keeps data) | `docker compose down` |
| View MySQL logs | `docker compose logs -f mysql` |
| **Wipe all data and start fresh** | `docker compose down -v` |
| Run the server (from the repo root) | `python -m cloud_server.app` |

## Troubleshooting

- **"port is already allocated" / MySQL won't start:** something else uses port 3306 (a local MySQL, or another service in this repo). Set `MYSQL_PORT=3307` in `cloud_server/.env`, then `docker compose up -d --wait`.
- **`Access denied for user`:** the MySQL credentials in `.env` are only applied the *first* time the data volume is created. If you changed them afterwards, run `docker compose down -v` in `cloud_server/` and start again (this deletes the data).
- **`Can't connect to MySQL server` / `/health` returns 503:** check that Docker Desktop is running and `docker compose ps` (in `cloud_server/`) shows the container as `healthy`.
- **`.env` changes have no effect on the app:** restart the server (`python -m cloud_server.app`).
- **`ModuleNotFoundError: No module named 'common'`:** run the server from the repository root with `python -m cloud_server.app`. Running `python cloud_server/app.py` doesn't work because `common.py` lives in the root. In an IDE, set the working directory to the repo root.
- **`ModuleNotFoundError` for anything else:** activate the virtual environment and re-run `pip install -r cloud_server/requirements.txt`.

## Files in this folder

```
cloud_server/
├── __init__.py
├── app.py               # Flask routes and request validation
├── models.py            # SQLAlchemy ORM model (Reading)
├── db.py                # engine, sessions, table creation, upsert helper
├── docker-compose.yml   # MySQL container
├── requirements.txt     # Python dependencies of this service
├── .env.example         # config template (copy to .env)
└── README.md
```