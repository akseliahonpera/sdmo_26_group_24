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

    device_id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )
    ts: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)

    edge_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    temperature: Mapped[float] = mapped_column(Double)
    humidity: Mapped[float] = mapped_column(Double)
    received_at: Mapped[int] = mapped_column(BigInteger)
