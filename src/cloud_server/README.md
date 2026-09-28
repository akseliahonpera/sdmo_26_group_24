# Cloud Server (Flask + SQLAlchemy + MySQL)

Receives sensor readings from edge gateways, stores them in MySQL and serves aggregates over a small JSON API.
MySQL runs in Docker; the Flask app runs directly on your machine.

## Required commands to start the cloud server

### Docker

Note that you should have your certs (server.crt and server.key) in cloud_server/certs/

```bash
cd src/cloud_server
docker compose up -d --build

docker compose logs -f app
```

### Manual
B) Run these from the repository root:

```bash
# 1) Create the local environment file
cp src/cloud_server/.env.example src/cloud_server/.env

# 2) Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3) Install dependencies
pip install -r src/cloud_server/requirements.txt

# 4) Start MySQL (from the project root using the service folder)
cd src/cloud_server
docker compose up -d --wait
cd ../..

# 5) Start the Flask server
cd src
python -m cloud_server.app
```

Then check the health endpoint:

```bash
curl http://localhost:5000/health
```

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


The server listens on http://localhost:5000. Check it with `curl localhost:5000/health`.


## Configuration

Settings are read from `src/cloud_server/.env` (copied from `.env.example`). The same file configures the MySQL container and the app.

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


## Look inside the database

From the `src/cloud_server/` folder:

```bash
docker compose exec mysql mysql -u cloud_user -p cloud_db
# enter the MYSQL_PASSWORD from your .env, then:
#   SELECT * FROM readings;
```
