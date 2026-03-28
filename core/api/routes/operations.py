"""Operations and sessions routes."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db.models import Operation, OperationStatus, Session as SessionModel, SessionStatus
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

    @classmethod
    def from_orm(cls, op: Operation) -> "OperationOut":
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
    return [OperationOut.from_orm(op) for op in ops]


@router.post("/operations/{op_id}/approve", response_model=OperationOut)
def approve_operation(op_id: str, db: DBSession = Depends(get_db)) -> OperationOut:
    op = _get_op(op_id, db)
    op.status = OperationStatus.approved
    db.commit()
    return OperationOut.from_orm(op)


@router.post("/operations/{op_id}/skip", response_model=OperationOut)
def skip_operation(op_id: str, db: DBSession = Depends(get_db)) -> OperationOut:
    op = _get_op(op_id, db)
    op.status = OperationStatus.skipped
    db.commit()
    return OperationOut.from_orm(op)


def _get_op(op_id: str, db: DBSession) -> Operation:
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    return op
