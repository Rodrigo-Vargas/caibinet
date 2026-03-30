"""Operations and sessions routes."""
from __future__ import annotations

import mimetypes
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db.models import Operation, OperationStatus, Session as SessionModel, SessionStatus, SummaryCache
from ...db.session import get_db
from ...engine import executor

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------

class OperationOut(BaseModel):
    id: str
    session_id: str
    created_at: str
    source_path: str
    dest_path: str
    original_name: str
    proposed_name: str
    category: str
    ai_reasoning: str
    confidence: float
    file_hash: str
    status: str
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    content_summary: Optional[str] = None

    @classmethod
    def from_orm(cls, op: Operation, summary: Optional[str] = None) -> "OperationOut":
        return cls(
            id=op.id,
            session_id=op.session_id,
            created_at=op.created_at.isoformat(),
            source_path=op.source_path,
            dest_path=op.dest_path,
            original_name=op.original_name,
            proposed_name=op.proposed_name,
            category=op.category,
            ai_reasoning=op.ai_reasoning or "",
            confidence=op.confidence or 0.0,
            file_hash=op.file_hash or "",
            status=op.status.value if hasattr(op.status, "value") else str(op.status),
            error=op.error,
            elapsed_seconds=op.elapsed_seconds,
            content_summary=summary,
        )


class SessionOut(BaseModel):
    id: str
    created_at: str
    label: str
    directory: str
    status: str
    total_files: int
    processed_files: int
    elapsed_seconds: Optional[float] = None
    phase: Optional[str] = None

    @classmethod
    def from_orm(cls, s: SessionModel) -> "SessionOut":
        return cls(
            id=s.id,
            created_at=s.created_at.isoformat(),
            label=s.label,
            directory=s.directory,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            total_files=int(s.total_files or 0),
            processed_files=int(s.processed_files or 0),
            elapsed_seconds=s.elapsed_seconds,
            phase=s.phase,
        )


class ApplyResult(BaseModel):
    session_id: str
    applied: int
    failed: int
    results: List[dict]


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(db: DBSession = Depends(get_db)) -> List[SessionOut]:
    sessions = db.query(SessionModel).order_by(SessionModel.created_at.desc()).all()
    return [SessionOut.from_orm(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: DBSession = Depends(get_db)) -> SessionOut:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionOut.from_orm(session)


@router.post("/sessions/{session_id}/apply", response_model=ApplyResult)
def apply_session(session_id: str, db: DBSession = Depends(get_db)) -> ApplyResult:
    ops = (
        db.query(Operation)
        .filter(
            Operation.session_id == session_id,
            Operation.status == OperationStatus.approved,
        )
        .all()
    )
    if not ops:
        raise HTTPException(status_code=400, detail="No approved operations to apply")

    applied = 0
    failed = 0
    results = []

    for op in ops:
        try:
            executor.apply(op, db)
            applied += 1
            results.append({"operation_id": op.id, "success": True})
        except RuntimeError as exc:
            failed += 1
            results.append({"operation_id": op.id, "success": False, "error": str(exc)})

    # Update session status
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session and failed == 0:
        session.status = SessionStatus.applied
        db.commit()

    return ApplyResult(session_id=session_id, applied=applied, failed=failed, results=results)


# ---------------------------------------------------------------------------
# Operation endpoints
# ---------------------------------------------------------------------------

@router.get("/operations", response_model=List[OperationOut])
def list_operations(
    session_id: Optional[str] = None,
    status: Optional[str] = None,
    db: DBSession = Depends(get_db),
) -> List[OperationOut]:
    q = db.query(Operation)
    if session_id:
        q = q.filter(Operation.session_id == session_id)
    if status:
        q = q.filter(Operation.status == status)
    ops = q.order_by(Operation.created_at.asc()).all()
    summaries = _get_summaries([op.file_hash for op in ops if op.file_hash], db)
    return [OperationOut.from_orm(op, summaries.get(op.file_hash)) for op in ops]


@router.post("/operations/{op_id}/approve", response_model=OperationOut)
def approve_operation(op_id: str, db: DBSession = Depends(get_db)) -> OperationOut:
    op = _get_op(op_id, db)
    op.status = OperationStatus.approved
    db.commit()
    summary = _get_single_summary(op.file_hash, db)
    return OperationOut.from_orm(op, summary)


@router.post("/operations/{op_id}/skip", response_model=OperationOut)
def skip_operation(op_id: str, db: DBSession = Depends(get_db)) -> OperationOut:
    op = _get_op(op_id, db)
    op.status = OperationStatus.skipped
    db.commit()
    summary = _get_single_summary(op.file_hash, db)
    return OperationOut.from_orm(op, summary)


def _get_summaries(file_hashes: List[str], db: DBSession) -> dict:
    """Return a {file_hash: summary} dict for the given hashes."""
    if not file_hashes:
        return {}
    rows = db.query(SummaryCache).filter(SummaryCache.file_hash.in_(file_hashes)).all()
    return {row.file_hash: row.summary for row in rows}


def _get_single_summary(file_hash: Optional[str], db: DBSession) -> Optional[str]:
    if not file_hash:
        return None
    row = db.query(SummaryCache).filter(SummaryCache.file_hash == file_hash).first()
    return row.summary if row else None


def _get_op(op_id: str, db: DBSession) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op


# ---------------------------------------------------------------------------
# File preview endpoint
# ---------------------------------------------------------------------------

class FilePreviewResponse(BaseModel):
    content: str
    is_binary: bool
    size: int
    truncated: bool
    mime_type: str


_PREVIEW_MAX_CHARS = 4_000


@router.get("/preview", response_model=FilePreviewResponse)
def preview_file(path: str) -> FilePreviewResponse:
    """Return a short text preview of the file at *path*.

    Binary or unreadable files are indicated via ``is_binary=True`` with an
    empty ``content`` string so the frontend can display a suitable message.
    """
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail="Not a regular file")

    size = os.path.getsize(path)
    mime_type, _ = mimetypes.guess_type(path)
    mime_type = mime_type or "application/octet-stream"

    try:
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            raw = fh.read(_PREVIEW_MAX_CHARS + 1)
        truncated = len(raw) > _PREVIEW_MAX_CHARS
        return FilePreviewResponse(
            content=raw[:_PREVIEW_MAX_CHARS],
            is_binary=False,
            size=size,
            truncated=truncated,
            mime_type=mime_type,
        )
    except (UnicodeDecodeError, PermissionError):
        return FilePreviewResponse(
            content="",
            is_binary=True,
            size=size,
            truncated=False,
            mime_type=mime_type,
        )
