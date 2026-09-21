# Cloud Server (Flask + MySQL)

Receives sensor readings from gateways, stores them in MySQL and serves aggregates.
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

The server listens on http://localhost:5000.

## Try it

macOS / Linux / Git Bash:

```bash
curl -X POST localhost:5000/api/ingest -H "Content-Type: application/json" \
  -d '{"readings":[{"id":1,"device_id":"dev-a","ts":1758400000000,"temperature":21.5,"humidity":40.2}]}'

curl localhost:5000/api/stats
curl "localhost:5000/api/readings/dev-a?limit=10"
curl localhost:5000/health
```

Windows PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/ingest `
  -ContentType "application/json" `
  -Body '{"readings":[{"id":1,"device_id":"dev-a","ts":1758400000000,"temperature":21.5,"humidity":40.2}]}'

Invoke-RestMethod http://localhost:5000/api/stats
```

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
- **`Can't connect to MySQL server`:** check that Docker Desktop is running and `docker compose ps` (in `cloud_server/`) shows the container as `healthy`.
- **`.env` changes have no effect on the app:** restart the server (`python -m cloud_server.app`).
- **`ModuleNotFoundError: No module named 'common'`:** run the server from the repository root with `python -m cloud_server.app`. Running `python cloud_server/app.py` doesn't work because `common.py` lives in the root. In an IDE, set the working directory to the repo root.
- **`ModuleNotFoundError` for anything else:** activate the virtual environment and re-run `pip install -r cloud_server/requirements.txt`.

## Files in this folder

```
cloud_server/
├── __init__.py
├── app.py               # Flask app
├── docker-compose.yml   # MySQL container
├── requirements.txt     # Python dependencies of this service
├── .env.example         # config template (copy to .env)
└── README.md
```