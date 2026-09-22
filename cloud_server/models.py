"""ORM models for the cloud server (SQLAlchemy 2.0)."""
from typing import Optional

from sqlalchemy import BigInteger, Double, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Reading(Base):
    """One sensor reading pushed by an edge gateway.

    A reading is uniquely identified by (device_id, ts), which makes re-sent
    batches idempotent: duplicates are simply ignored on insert.
    """

    __tablename__ = "readings"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    # Binary collation keeps device IDs case-sensitive (as they were in SQLite);
    # MySQL's default collation would treat "Dev-A" and "dev-a" as the same key.
    device_id: Mapped[str] = mapped_column(
        String(64, collation="utf8mb4_bin"), primary_key=True
    )
    # Epoch milliseconds, set by the edge node. BIGINT: it overflows a 32-bit INT.
    ts: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    # Row id in the edge node's local database (informational).
    edge_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    temperature: Mapped[float] = mapped_column(Double)
    humidity: Mapped[float] = mapped_column(Double)
    # Epoch milliseconds, set by the cloud server when the batch arrives.
    received_at: Mapped[int] = mapped_column(BigInteger)
