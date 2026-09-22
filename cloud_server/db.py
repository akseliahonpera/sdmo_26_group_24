"""Database setup: engine, session factory and helpers (SQLAlchemy 2.0 + MySQL)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from cloud_server.models import Base, Reading

# Reads cloud_server/.env (the same file docker compose uses).
load_dotenv(Path(__file__).resolve().parent / ".env")

# Set by init_db().
engine = None
SessionLocal = None


def build_url() -> URL:
    """Build the connection URL from environment variables.

    URL.create() takes care of escaping special characters in the password.
    """
    return URL.create(
        drivername="mysql+mysqlconnector",
        username=os.environ.get("MYSQL_USER", "cloud_user"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        database=os.environ.get("MYSQL_DATABASE", "cloud_db"),
        query={"charset": "utf8mb4"},
    )


def init_db() -> None:
    """Create the engine (with a connection pool) and any missing tables."""
    global engine, SessionLocal
    engine = create_engine(
        build_url(),
        pool_size=10,        # persistent connections
        max_overflow=10,     # extra connections under burst load
        pool_pre_ping=True,  # transparently replace dead connections
        pool_recycle=1800,   # recycle connections older than 30 min
    )
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    # Creates missing tables only; it never alters existing ones.
    Base.metadata.create_all(engine)


def insert_readings_ignore_duplicates(session, rows: list[dict]) -> None:
    """Bulk-insert readings, silently skipping ones that already exist.

    Duplicates are identified by the primary key (device_id, ts). The no-op
    ON DUPLICATE KEY UPDATE ignores *only* duplicate keys, unlike INSERT IGNORE,
    which would also hide other errors such as truncated data.
    """
    if not rows:
        return
    # The ORM has no portable "upsert", so this uses MySQL's insert() construct
    # on the model's table (a plain executemany), still inside the ORM session.
    stmt = mysql_insert(Reading.__table__)
    stmt = stmt.on_duplicate_key_update(device_id=stmt.inserted.device_id)
    session.execute(stmt, rows)
