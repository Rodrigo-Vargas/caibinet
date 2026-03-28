"""Decision engine — converts AI output into an OperationProposal."""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Optional

from ..ai.prompts import AIDecision
from ..db.models import OperationStatus
from .scanner import FileRecord


class OperationProposal:
    """A proposed file operation, ready to be persisted."""

    def __init__(
        self,
        *,
        session_id: str,
        source_path: str,
        dest_path: str,
        original_name: str,
        proposed_name: str,
        category: str,
        confidence: float,
        ai_reasoning: str,
        file_hash: str,
        status: OperationStatus = OperationStatus.pending,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.session_id = session_id
        self.source_path = source_path
        self.dest_path = dest_path
        self.original_name = original_name
        self.proposed_name = proposed_name
        self.category = category
        self.confidence = confidence
        self.ai_reasoning = ai_reasoning
        self.file_hash = file_hash
        self.status = status


def _safe_filename(name: str) -> str:
    """Replace characters unsafe for filenames with underscores."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return name.strip(". ") or "unnamed"


def _resolve_collision(dest: str) -> str:
    """Append _2, _3, … until *dest* does not exist."""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    counter = 2
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _clamp_to_one_new_dir(scan_root: str, sub_path: str) -> str:
    """Ensure at most one new directory level is created under *scan_root*.

    Walks the components of *sub_path* from the root outward.  The first
    component that does not yet exist on disk marks the boundary — everything
    beyond it is discarded, so callers can only create a single new folder.

    Examples (scan_root=/home/user/Docs, existing: Finance/):
      ``Finance/reports/`` → ``Finance/reports/``  (reports is the one new dir)
      ``Finance/reports/2025/`` → ``Finance/reports/``  (can't create 2 new dirs)
      ``Invoices/paid/`` → ``Invoices/``  (Invoices doesn't exist yet)
    """
    parts = Path(sub_path).parts
    allowed: list[str] = []
    for part in parts:
        candidate = os.path.join(scan_root, *allowed, part)
        if os.path.isdir(candidate):
            allowed.append(part)
        else:
            # First missing directory — allow exactly this one new level, then stop
            allowed.append(part)
            break
    return str(Path(*allowed)) if allowed else ""


def evaluate(
    file_record: FileRecord,
    ai_decision: AIDecision,
    scan_root: str,
    session_id: str,
) -> OperationProposal:
    """Evaluate an AI decision for *file_record* and return an :class:`OperationProposal`."""

    source = str(file_record.path)

    # --- Parse error gate (no valid action to propose) ---
    if ai_decision.parse_error:
        return OperationProposal(
            session_id=session_id,
            source_path=source,
            dest_path=source,
            original_name=file_record.name,
            proposed_name=file_record.name,
            category=ai_decision.category,
            confidence=ai_decision.confidence,
            ai_reasoning=ai_decision.parse_error,
            file_hash=file_record.sha256,
            status=OperationStatus.skipped,
        )

    # --- Build destination path ---
    proposed_name = _safe_filename(ai_decision.filename) if ai_decision.filename else file_record.name
    # Preserve original extension if AI dropped it
    if not Path(proposed_name).suffix and file_record.extension:
        proposed_name += file_record.extension

    sub_path = ai_decision.path.lstrip("/\\").rstrip("/\\")
    sub_path = _clamp_to_one_new_dir(scan_root, sub_path)
    dest_dir = os.path.join(scan_root, sub_path)
    dest = os.path.join(dest_dir, proposed_name)
    dest = _resolve_collision(dest)

    # --- No-op gate ---
    if os.path.normpath(source) == os.path.normpath(dest):
        return OperationProposal(
            session_id=session_id,
            source_path=source,
            dest_path=dest,
            original_name=file_record.name,
            proposed_name=proposed_name,
            category=ai_decision.category,
            confidence=ai_decision.confidence,
            ai_reasoning=ai_decision.reasoning,
            file_hash=file_record.sha256,
            status=OperationStatus.skipped,
        )

    return OperationProposal(
        session_id=session_id,
        source_path=source,
        dest_path=dest,
        original_name=file_record.name,
        proposed_name=proposed_name,
        category=ai_decision.category,
        confidence=ai_decision.confidence,
        ai_reasoning=ai_decision.reasoning,
        file_hash=file_record.sha256,
        status=OperationStatus.pending,
    )
