"""Database models and additive V2 migrations.

The original ``rooms`` and ``logs`` tables are intentionally retained.  V2 room
state is stored in additional columns and audit receipts live in ``room_events``.
This lets a production database be upgraded in place without rewriting history.
"""

from __future__ import annotations

from datetime import datetime
import os
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./random_draw.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine_options = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.utcnow()


class Room(Base):
    __tablename__ = "rooms"

    # Original columns. Never rename or remove these: production data uses them.
    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    is_coin_flip = Column(Boolean, default=False)
    is_list_draw = Column(Boolean, default=False)
    min_value = Column(Integer, default=1)
    max_value = Column(Integer, default=100)
    with_replacement = Column(Boolean, default=True)

    # V2 additive state.
    short_code = Column(String(8), nullable=True)
    mode = Column(String(16), nullable=True, default="numbers")
    config_json = Column(Text, nullable=True)
    drawn_json = Column(Text, nullable=True)
    latest_result_json = Column(Text, nullable=True)
    host_token_hash = Column(String(64), nullable=True)
    host_name = Column(String(80), nullable=True)
    draw_policy = Column(String(16), nullable=True, default="host_only")
    status = Column(String(16), nullable=True, default="active")
    draw_index = Column(Integer, nullable=True, default=0)
    event_index = Column(Integer, nullable=True, default=0)
    round_index = Column(Integer, nullable=True, default=1)
    updated_at = Column(DateTime, nullable=True, default=utcnow)
    ended_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    logs = relationship("Log", back_populates="room")
    events = relationship(
        "RoomEvent", back_populates="room", order_by="RoomEvent.event_index"
    )

    __table_args__ = (Index("ux_rooms_short_code", "short_code", unique=True),)


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, ForeignKey("rooms.id"))
    timestamp = Column(DateTime, default=utcnow)
    user_name = Column(String)
    action = Column(String)
    result = Column(String)

    room = relationship("Room", back_populates="logs")


class RoomEvent(Base):
    """Append-only user-readable history and concise draw receipts."""

    __tablename__ = "room_events"

    id = Column(Integer, primary_key=True)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=False, index=True)
    event_index = Column(Integer, nullable=False)
    draw_index = Column(Integer, nullable=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False)
    kind = Column(String(24), nullable=False)
    mode = Column(String(16), nullable=False)
    actor = Column(String(80), nullable=False)
    result_json = Column(Text, nullable=True)
    pool_fingerprint = Column(String(64), nullable=True)
    pool_count = Column(Integer, nullable=True)
    details_json = Column(Text, nullable=True)
    invalidated = Column(Boolean, default=False, nullable=False)

    room = relationship("Room", back_populates="events")

    __table_args__ = (
        UniqueConstraint("room_id", "event_index", name="uq_room_event_index"),
    )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dialect-neutral column definitions for the small additive migration. SQLAlchemy
# metadata creates fresh databases; these definitions upgrade an existing V1 DB.
_ROOM_V2_COLUMNS = {
    "is_list_draw": "BOOLEAN DEFAULT FALSE",
    "short_code": "VARCHAR(8)",
    "mode": "VARCHAR(16)",
    "config_json": "TEXT",
    "drawn_json": "TEXT",
    "latest_result_json": "TEXT",
    "host_token_hash": "VARCHAR(64)",
    "host_name": "VARCHAR(80)",
    "draw_policy": "VARCHAR(16)",
    "status": "VARCHAR(16)",
    "draw_index": "INTEGER DEFAULT 0",
    "event_index": "INTEGER DEFAULT 0",
    "round_index": "INTEGER DEFAULT 1",
    "updated_at": "TIMESTAMP",
    "ended_at": "TIMESTAMP",
    "expires_at": "TIMESTAMP",
}


def _migrate_rooms() -> None:
    inspector = inspect(engine)
    if "rooms" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("rooms")}
    with engine.begin() as connection:
        for name, definition in _ROOM_V2_COLUMNS.items():
            if name not in existing:
                connection.execute(
                    text(f'ALTER TABLE rooms ADD COLUMN "{name}" {definition}')
                )
        # Existing rooms predate host credentials. They remain draw-compatible,
        # but management actions still require a V2-created host token.
        connection.execute(
            text(
                "UPDATE rooms SET mode = CASE "
                "WHEN is_coin_flip = TRUE THEN 'coin' "
                "WHEN is_list_draw = TRUE THEN 'list' ELSE 'numbers' END "
                "WHERE mode IS NULL OR mode = ''"
            )
        )
        connection.execute(
            text("UPDATE rooms SET draw_policy='anyone' WHERE draw_policy IS NULL")
        )
        connection.execute(text("UPDATE rooms SET status='active' WHERE status IS NULL"))
        connection.execute(text("UPDATE rooms SET draw_index=0 WHERE draw_index IS NULL"))
        connection.execute(text("UPDATE rooms SET event_index=0 WHERE event_index IS NULL"))
        connection.execute(text("UPDATE rooms SET round_index=1 WHERE round_index IS NULL"))
    # The index is intentionally separate so SQLite can add it after the column.
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ux_rooms_short_code ON rooms (short_code)")
        )


def create_tables() -> None:
    # Upgrade old rooms before create_all tries to create the V2-only tables and
    # indexes that reference the new column.
    _migrate_rooms()
    Base.metadata.create_all(bind=engine)
