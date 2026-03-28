"""Undo routes — single operation, session batch, and global all."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db.models import Operation, OperationStatus
from ...db.session import get_db
from ...engine import executor

router = APIRouter()


class UndoResult(BaseModel):
    operation_id: str
    success: bool
    error: str | None = None


@router.post("/undo/{operation_id}", response_model=UndoResult)
def undo_operation(operation_id: str, db: DBSession = Depends(get_db)) -> UndoResult:
    op = db.query(Operation).filter(Operation.id == operation_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    if op.status != OperationStatus.applied:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot undo operation with status '{op.status}'",
        )
    try:
        executor.undo(op, db)
        return UndoResult(operation_id=operation_id, success=True)
    except RuntimeError as exc:
        return UndoResult(operation_id=operation_id, success=False, error=str(exc))


@router.post("/undo/session/{session_id}", response_model=List[UndoResult])
def undo_session(session_id: str, db: DBSession = Depends(get_db)) -> List[UndoResult]:
    results = executor.undo_batch(session_id, db)
    return [UndoResult(operation_id=r.operation_id, success=r.success, error=r.error) for r in results]


@router.post("/undo/all", response_model=List[UndoResult])
def undo_all(db: DBSession = Depends(get_db)) -> List[UndoResult]:
    results = executor.undo_all(db)
    return [UndoResult(operation_id=r.operation_id, success=r.success, error=r.error) for r in results]
