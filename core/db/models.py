import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Text, DateTime, ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum





def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class SessionStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    applied = "applied"
    undone = "undone"
    error = "error"
    cancelled = "cancelled"


class OperationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    applied = "applied"
    undone = "undone"
    skipped = "skipped"
    error = "error"


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    created_at = Column(DateTime, default=_now, nullable=False)
    label = Column(String, nullable=False, default="")
    directory = Column(String, nullable=False)
    status = Column(SAEnum(SessionStatus), default=SessionStatus.pending, nullable=False)
    total_files = Column(String, default="0")       # stored as str for SQLite compat
    processed_files = Column(String, default="0")
    elapsed_seconds = Column(Float, nullable=True)  # total scan duration
    # Two-phase scan: 'summarizing' (collecting summaries) | 'deciding' (rename + organize per file)
    phase = Column(String, nullable=True)           # None once the scan is complete

    operations = relationship(
        "Operation", back_populates="session", cascade="all, delete-orphan"
    )


class Operation(Base):
    __tablename__ = "operations"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)
    source_path = Column(String, nullable=False)
    dest_path = Column(String, nullable=False)
    original_name = Column(String, nullable=False)
    proposed_name = Column(String, nullable=False)
    category = Column(String, nullable=False, default="Other")
    ai_reasoning = Column(Text, default="")
    confidence = Column(Float, default=0.0)
    file_hash = Column(String, default="")
    status = Column(SAEnum(OperationStatus), default=OperationStatus.pending, nullable=False)
    error = Column(Text, nullable=True)
    elapsed_seconds = Column(Float, nullable=True)  # per-file LLM processing time

    session = relationship("Session", back_populates="operations")


class SettingEntry(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class SummaryCache(Base):
    """Cached LLM file-content summary, keyed by the file's SHA-256 hash."""
    __tablename__ = "summary_cache"

    file_hash = Column(String, primary_key=True)
    summary = Column(Text, nullable=False)
    cached_at = Column(DateTime, default=_now, nullable=False)
