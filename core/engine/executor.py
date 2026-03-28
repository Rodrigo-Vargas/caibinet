"""File executor — performs and reverses file moves, verifying hashes."""
from __future__ import annotations

import hashlib
import os
import shutil
import logging
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session as DBSession

from ..db.models import Operation, OperationStatus, Session as SessionModel, SessionStatus

log = logging.getLogger(__name__)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply(operation: Operation, db: DBSession) -> None:
    """Move the file from source → dest and mark *operation* as applied.

    Raises ``RuntimeError`` on any failure; the source remains intact.
    """
    src = operation.source_path
    dst = operation.dest_path

    if not os.path.exists(src):
        _fail(operation, db, f"Source file not found: {src}")
        raise RuntimeError(f"Source file not found: {src}")

    # Hash verification — guard against source being replaced since scan
    current_hash = _sha256(src)
    if current_hash != operation.file_hash:
        _fail(operation, db, f"Hash mismatch (expected {operation.file_hash}, got {current_hash})")
        raise RuntimeError("Hash mismatch — source file changed since scan")

    os.makedirs(os.path.dirname(dst), exist_ok=True)

    try:
        shutil.move(src, dst)
    except OSError as exc:
        _fail(operation, db, str(exc))
        raise RuntimeError(str(exc)) from exc

    operation.status = OperationStatus.applied
    operation.error = None
    db.commit()
    log.info("Applied: %s → %s", src, dst)


# ---------------------------------------------------------------------------
# Undo single operation
# ---------------------------------------------------------------------------

def undo(operation: Operation, db: DBSession) -> None:
    """Reverse a previously applied move (dest → source)."""
    src = operation.dest_path   # where the file currently lives
    dst = operation.source_path  # where it should go back

    if not os.path.exists(src):
        _fail(operation, db, f"Destination file not found for undo: {src}")
        raise RuntimeError(f"File to undo not found: {src}")

    os.makedirs(os.path.dirname(dst), exist_ok=True)

    try:
        shutil.move(src, dst)
    except OSError as exc:
        _fail(operation, db, str(exc))
        raise RuntimeError(str(exc)) from exc

    operation.status = OperationStatus.undone
    operation.error = None
    db.commit()
    log.info("Undone: %s → %s", src, dst)


# ---------------------------------------------------------------------------
# Undo batch (session)
# ---------------------------------------------------------------------------

class UndoResult:
    def __init__(self, operation_id: str, success: bool, error: str | None = None) -> None:
        self.operation_id = operation_id
        self.success = success
        self.error = error


def undo_batch(session_id: str, db: DBSession) -> List[UndoResult]:
    """Undo all applied operations for *session_id* in reverse order."""
    ops = (
        db.query(Operation)
        .filter(
            Operation.session_id == session_id,
            Operation.status == OperationStatus.applied,
        )
        .order_by(Operation.created_at.desc())
        .all()
    )
    return _undo_ops(ops, db)


def undo_all(db: DBSession) -> List[UndoResult]:
    """Undo every applied operation across all sessions, in reverse order."""
    ops = (
        db.query(Operation)
        .filter(Operation.status == OperationStatus.applied)
        .order_by(Operation.created_at.desc())
        .all()
    )
    return _undo_ops(ops, db)


def _undo_ops(ops: list, db: DBSession) -> List[UndoResult]:
    results: List[UndoResult] = []
    for op in ops:
        try:
            undo(op, db)
            results.append(UndoResult(op.id, success=True))
        except RuntimeError as exc:
            results.append(UndoResult(op.id, success=False, error=str(exc)))
    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fail(operation: Operation, db: DBSession, message: str) -> None:
    operation.status = OperationStatus.error
    operation.error = message
    db.commit()
    log.error("Executor error for op %s: %s", operation.id, message)
