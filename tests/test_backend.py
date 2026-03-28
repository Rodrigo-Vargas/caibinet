"""Unit tests for the Caibinet Python backend."""
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def test_extractor_text(tmp_path):
    from core.engine.scanner import FileRecord
    from core.engine.extractor import extract

    f = tmp_path / "hello.txt"
    f.write_text("Hello world! " * 100)

    record = FileRecord(
        path=f,
        relative_path="hello.txt",
        name="hello.txt",
        extension=".txt",
        size=f.stat().st_size,
        mime_type="text/plain",
        sha256="",
    )

    text, content_type = extract(record)
    assert content_type == "text"
    assert "Hello world!" in text


def test_extractor_unknown_mime(tmp_path):
    from core.engine.scanner import FileRecord
    from core.engine.extractor import extract

    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02" * 20)

    record = FileRecord(
        path=f,
        relative_path="data.bin",
        name="data.bin",
        extension=".bin",
        size=60,
        mime_type="application/octet-stream",
        sha256="",
    )

    text, content_type = extract(record)
    assert content_type == "metadata_only"
    assert text == ""


# ---------------------------------------------------------------------------
# AI response parsing
# ---------------------------------------------------------------------------

def test_parse_response_valid():
    from core.ai.prompts import parse_response

    raw = '{"filename": "invoice_2024.pdf", "category": "Finance", "path": "finance/invoices/", "confidence": 0.92, "reasoning": "Contains invoice header"}'
    decision = parse_response(raw)

    assert decision.filename == "invoice_2024.pdf"
    assert decision.category == "Finance"
    assert abs(decision.confidence - 0.92) < 0.001
    assert decision.parse_error == ""


def test_parse_response_embedded_in_text():
    from core.ai.prompts import parse_response

    raw = 'Sure! Here is the result: {"filename": "report.docx", "category": "Work", "path": "work/reports/", "confidence": 0.75, "reasoning": "Work report"}'
    decision = parse_response(raw)

    assert decision.filename == "report.docx"
    assert decision.confidence == 0.75


def test_parse_response_invalid():
    from core.ai.prompts import parse_response

    decision = parse_response("not json at all")
    assert decision.confidence == 0.0
    assert decision.parse_error != ""


def test_parse_response_invalid_category():
    from core.ai.prompts import parse_response

    raw = '{"filename": "x.txt", "category": "Junk", "path": "misc/", "confidence": 0.8, "reasoning": "x"}'
    decision = parse_response(raw)
    assert decision.category == "Other"


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------

def test_decision_low_confidence_still_proposed(tmp_path):
    from core.engine.scanner import FileRecord
    from core.engine.decision import evaluate
    from core.ai.prompts import AIDecision
    from core.db.models import OperationStatus

    f = tmp_path / "junk.txt"
    f.write_text("x")

    record = FileRecord(
        path=f,
        relative_path="junk.txt",
        name="junk.txt",
        extension=".txt",
        size=1,
        mime_type="text/plain",
        sha256="abc123",
    )

    ai_decision = AIDecision(
        filename="junk.txt",
        category="Other",
        path="misc/",
        confidence=0.2,
        reasoning="low confidence",
    )

    proposal = evaluate(
        file_record=record,
        ai_decision=ai_decision,
        scan_root=str(tmp_path),
        session_id=str(uuid.uuid4()),
    )

    # Low confidence is now shown to the user as pending — not auto-skipped
    assert proposal.status == OperationStatus.pending


def test_decision_good_confidence(tmp_path):
    from core.engine.scanner import FileRecord
    from core.engine.decision import evaluate
    from core.ai.prompts import AIDecision
    from core.db.models import OperationStatus

    f = tmp_path / "invoice.pdf"
    f.write_text("x")

    record = FileRecord(
        path=f,
        relative_path="invoice.pdf",
        name="invoice.pdf",
        extension=".pdf",
        size=1,
        mime_type="application/pdf",
        sha256="abc123",
    )

    ai_decision = AIDecision(
        filename="invoice_2024",
        category="Finance",
        path="finance/invoices/",
        confidence=0.88,
        reasoning="Invoice document",
    )

    proposal = evaluate(
        file_record=record,
        ai_decision=ai_decision,
        scan_root=str(tmp_path),
        session_id=str(uuid.uuid4()),
    )

    assert proposal.status == OperationStatus.pending
    assert proposal.proposed_name == "invoice_2024.pdf"


# ---------------------------------------------------------------------------
# Executor apply + undo
# ---------------------------------------------------------------------------

def test_executor_apply_and_undo(tmp_path):
    from core.engine import executor
    from core.db.models import Base, Operation, OperationStatus
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from datetime import datetime, timezone

    # In-memory SQLite DB for this test
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Create source file
    src = tmp_path / "source.txt"
    src.write_text("hello")
    sha = hashlib.sha256(b"hello").hexdigest()

    dest = tmp_path / "dest" / "moved.txt"

    op = Operation(
        id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        source_path=str(src),
        dest_path=str(dest),
        original_name="source.txt",
        proposed_name="moved.txt",
        category="Other",
        ai_reasoning="test",
        confidence=0.9,
        file_hash=sha,
        status=OperationStatus.approved,
    )
    db.add(op)
    db.commit()

    # Apply
    executor.apply(op, db)
    assert not src.exists()
    assert dest.exists()
    assert op.status == OperationStatus.applied

    # Undo
    executor.undo(op, db)
    assert src.exists()
    assert not dest.exists()
    assert op.status == OperationStatus.undone
