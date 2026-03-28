"""POST /scan — start a scan session in the background."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...db.models import (
    Operation,
    OperationStatus,
    Session as SessionModel,
    SessionStatus,
    SummaryCache,
)
from ...db.session import get_db
from ...engine.scanner import scan_directory, build_folder_tree
from ...engine.extractor import extract
from ...engine.decision import evaluate
from ...ai.ollama import OllamaProvider
from ...ai.base import ProviderConfig
from ...ai.prompts import (
    render_summary_prompt,
    render_decision_prompt,
    render_rename_prompt,
    render_folder_role_prompt,
    render_related_files_prompt,
    parse_response,
    parse_rename_response,
    parse_folder_role_response,
    parse_related_files_response,
)
from .settings import _load_settings

log = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Cancellation tokens — in-memory, keyed by session_id
# ---------------------------------------------------------------------------
_cancel_tokens: set[str] = set()
_cancel_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Summary cache helpers
# ---------------------------------------------------------------------------

def _get_cached_summary(file_hash: str, ttl_minutes: int, db: DBSession) -> str | None:
    """Return a cached summary for *file_hash* if it exists and has not expired.

    Returns ``None`` when caching is disabled (``ttl_minutes == 0``), the entry
    does not exist, or the entry is older than *ttl_minutes* minutes.
    """
    if ttl_minutes <= 0:
        return None
    row = db.query(SummaryCache).filter(SummaryCache.file_hash == file_hash).first()
    if row is None:
        return None
    age = datetime.now(timezone.utc) - row.cached_at.replace(tzinfo=timezone.utc)
    if age > timedelta(minutes=ttl_minutes):
        return None
    return row.summary


def _set_cached_summary(file_hash: str, summary: str, ttl_minutes: int, db: DBSession) -> None:
    """Upsert a summary into the cache. No-op when caching is disabled."""
    if ttl_minutes <= 0:
        return
    row = db.query(SummaryCache).filter(SummaryCache.file_hash == file_hash).first()
    now = datetime.now(timezone.utc)
    if row:
        row.summary = summary
        row.cached_at = now
    else:
        db.add(SummaryCache(file_hash=file_hash, summary=summary, cached_at=now))


def _request_cancel(session_id: str) -> None:
    with _cancel_lock:
        _cancel_tokens.add(session_id)


def _is_cancelled(session_id: str) -> bool:
    with _cancel_lock:
        return session_id in _cancel_tokens


def _clear_cancel(session_id: str) -> None:
    with _cancel_lock:
        _cancel_tokens.discard(session_id)


class ScanRequest(BaseModel):
    directory: str
    dry_run: bool = True


class ScanResponse(BaseModel):
    session_id: str
    message: str


@router.post("/scan", response_model=ScanResponse)
async def start_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
) -> ScanResponse:
    session_id = str(uuid.uuid4())
    session = SessionModel(
        id=session_id,
        created_at=datetime.now(timezone.utc),
        label=body.directory,
        directory=body.directory,
        status=SessionStatus.running,
        total_files="0",
        processed_files="0",
    )
    db.add(session)
    db.commit()

    background_tasks.add_task(
        _run_scan,
        session_id=session_id,
        directory=body.directory,
        dry_run=body.dry_run,
    )

    return ScanResponse(session_id=session_id, message="Scan started")


@router.get("/list-files")
def list_files(
    directory: str,
    db: DBSession = Depends(get_db),
) -> dict:
    """Return the files that *would* be scanned in *directory* without starting a session.

    Used by the frontend to show the full file list instantly so the UI can
    render per-row progress feedback as soon as the scan begins.
    """
    try:
        effective = _load_settings(db)
        files = scan_directory(directory, effective.ignore_patterns)
        if effective.max_files > 0:
            files = files[: effective.max_files]
        return {"files": [str(f.path) for f in files]}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/operations/{op_id}/retry", response_model=None)
def retry_operation(
    op_id: str,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
) -> dict:
    """Re-run the LLM analysis for a single operation. Resets it to *pending*
    and spawns a background thread to re-process the file."""
    op = db.query(Operation).filter(Operation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    session = db.query(SessionModel).filter(SessionModel.id == op.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Parent session not found")

    # Reset the operation so the UI shows it as "in progress" again
    op.status = OperationStatus.pending
    op.error = None
    op.elapsed_seconds = None
    db.commit()

    background_tasks.add_task(
        _retry_single_file,
        op_id=op_id,
        source_path=op.source_path,
        session_id=op.session_id,
        directory=session.directory,
    )

    return {"op_id": op_id, "message": "Retry started"}


def _retry_single_file(op_id: str, source_path: str, session_id: str, directory: str) -> None:
    """Background worker that re-processes one file and updates its operation in-place."""
    from ...db.session import SessionLocal
    from ...engine.scanner import FileRecord, _compute_sha256
    from pathlib import Path
    import mimetypes

    db = SessionLocal()
    op = None
    try:
        op = db.query(Operation).filter(Operation.id == op_id).first()
        if not op:
            return

        effective = _load_settings(db)
        ai = OllamaProvider(ProviderConfig(
            model=effective.ollama_model,
            base_url=effective.ollama_url,
            timeout=effective.ollama_timeout,
        ))

        folder_tree = build_folder_tree(directory, effective.ignore_patterns)

        p = Path(source_path)
        mime_type = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        try:
            sha256 = _compute_sha256(p)
            size = p.stat().st_size
        except OSError as e:
            raise RuntimeError(f"Cannot read file: {e}") from e

        try:
            rel = str(p.relative_to(directory))
        except ValueError:
            rel = p.name

        file_record = FileRecord(
            path=p,
            relative_path=rel,
            name=p.name,
            extension=p.suffix,
            size=size,
            mime_type=mime_type,
            sha256=sha256,
        )

        file_start = time.monotonic()
        content, content_type = extract(file_record)
        file_record.content_type = content_type

        # --- Pass 1: summarise file content (served from cache when available) ---
        summary = _get_cached_summary(file_record.sha256, effective.summary_cache_ttl_minutes, db)
        if summary is not None:
            log.debug("RETRY SUMMARY CACHE HIT  file=%s", file_record.name)
        else:
            summary_prompt = render_summary_prompt(
                name=file_record.name,
                ext=file_record.extension,
                size=file_record.size,
                content=content,
                content_type=content_type,
            )
            log.debug("RETRY LLM SUMMARY REQUEST  file=%s prompt=\n%s", file_record.name, summary_prompt)
            summary = ai.generate(summary_prompt).strip()
            log.debug("RETRY LLM SUMMARY RESPONSE  file=%s response=\n%s", file_record.name, summary)
            _set_cached_summary(file_record.sha256, summary, effective.summary_cache_ttl_minutes, db)

        # --- Pass 2a: rename check ---
        rename_prompt = render_rename_prompt(
            name=file_record.name,
            ext=file_record.extension,
            size=file_record.size,
            summary=summary,
        )
        log.debug("RETRY LLM RENAME REQUEST  file=%s", file_record.name)
        raw_rename = ai.generate(rename_prompt)
        rename_decision = parse_rename_response(raw_rename, file_record.name)
        if rename_decision.parse_error:
            log.warning("RETRY LLM RENAME PARSE ERROR  file=%s error=%s", file_record.name, rename_decision.parse_error)

        # --- Pass 2b: organization decision ---
        decision_prompt = render_decision_prompt(
            name=rename_decision.filename,
            ext=file_record.extension,
            size=file_record.size,
            summary=summary,
            folder_tree=folder_tree,
        )
        log.debug("RETRY LLM DECISION REQUEST  file=%s prompt=\n%s", file_record.name, decision_prompt)
        raw_response = ai.generate(decision_prompt)
        log.debug("RETRY LLM DECISION RESPONSE  file=%s response=\n%s", file_record.name, raw_response)
        ai_decision = parse_response(raw_response)

        if ai_decision.parse_error:
            log.warning("RETRY LLM PARSE ERROR  file=%s error=%s", file_record.name, ai_decision.parse_error)

        proposal = evaluate(
            file_record=file_record,
            ai_decision=ai_decision,
            scan_root=directory,
            session_id=session_id,
        )

        op.dest_path = proposal.dest_path
        op.proposed_name = proposal.proposed_name
        op.category = proposal.category
        op.confidence = proposal.confidence
        op.ai_reasoning = proposal.ai_reasoning
        op.file_hash = proposal.file_hash
        op.status = proposal.status
        op.error = None
        op.elapsed_seconds = round(time.monotonic() - file_start, 3)
        log.info(
            "RETRY COMPLETE  file=%s → category=%s confidence=%.2f proposed=%s",
            file_record.name, op.category, op.confidence, op.proposed_name,
        )
    except Exception as exc:
        log.error("Retry worker failure for op=%s: %s", op_id, exc, exc_info=True)
        if op:
            op.status = OperationStatus.error
            op.error = str(exc)
    finally:
        db.commit()
        db.close()


@router.post("/sessions/{session_id}/cancel")
def cancel_scan(
    session_id: str,
    db: DBSession = Depends(get_db),
) -> dict:
    """Request cancellation of a running scan. Idempotent."""
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in (SessionStatus.running, SessionStatus.pending):
        raise HTTPException(
            status_code=409,
            detail=f"Session is not running (status={session.status})",
        )
    _request_cancel(session_id)
    log.info("Cancellation requested for session=%s", session_id)
    return {"session_id": session_id, "message": "Cancellation requested"}

def _run_scan(session_id: str, directory: str, dry_run: bool) -> None:
    from ...db.session import SessionLocal

    db = SessionLocal()
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            return

        # 1. Load effective settings from DB, then scan directory
        effective = _load_settings(db)
        files = scan_directory(directory, effective.ignore_patterns)
        if effective.max_files > 0:
            files = files[:effective.max_files]
        session.total_files = str(len(files))
        db.commit()

        if not files:
            session.phase = None
            session.status = SessionStatus.applied
            db.commit()
            return

        # 2. Build AI provider and folder tree snapshot
        provider_config = ProviderConfig(
            model=effective.ollama_model,
            base_url=effective.ollama_url,
            timeout=effective.ollama_timeout,
        )
        ai = OllamaProvider(provider_config)
        folder_tree = build_folder_tree(directory, effective.ignore_patterns)
        log.debug("Folder tree for scan:\n%s", folder_tree)

        scan_start = time.monotonic()

        # -----------------------------------------------------------------------
        # Phase 1 — "summarizing": collect content summaries for every file.
        # The frontend shows a bulk progress bar during this phase.
        # -----------------------------------------------------------------------
        session.phase = "summarizing"
        session.processed_files = "0"
        db.commit()

        # path → summary
        summaries: dict[str, str] = {}

        for idx, file_record in enumerate(files):
            if _is_cancelled(session_id):
                log.info("Scan cancelled (summarizing): session=%s at file %d/%d", session_id, idx, len(files))
                session.phase = None
                session.status = SessionStatus.cancelled
                db.commit()
                _clear_cancel(session_id)
                return

            try:
                content, content_type = extract(file_record)
                file_record.content_type = content_type

                summary = _get_cached_summary(file_record.sha256, effective.summary_cache_ttl_minutes, db)
                if summary is not None:
                    log.debug("SUMMARY CACHE HIT  file=%s", file_record.name)
                else:
                    summary_prompt = render_summary_prompt(
                        name=file_record.name,
                        ext=file_record.extension,
                        size=file_record.size,
                        content=content,
                        content_type=content_type,
                    )
                    log.debug("LLM SUMMARY REQUEST  file=%s", file_record.name)
                    summary = ai.generate(summary_prompt).strip()
                    log.debug("LLM SUMMARY RESPONSE  file=%s summary=%s", file_record.name, summary)
                    _set_cached_summary(file_record.sha256, summary, effective.summary_cache_ttl_minutes, db)

                summaries[str(file_record.path)] = summary
            except Exception as exc:
                log.error("Phase-1 summary error for %s: %s", file_record.path, exc)
                summaries[str(file_record.path)] = ""

            session.processed_files = str(idx + 1)
            db.commit()

        # Build the full-folder context list (name + summary) for every file collected
        # in phase 1. This lets the organize prompt detect naming conventions and
        # find similar files across the folder.
        folder_summaries = [
            {"name": fr.name, "summary": summaries.get(str(fr.path), "")}
            for fr in files
        ]

        # -----------------------------------------------------------------------
        # Phase 1.5 — "analyzing": run two batch LLM calls to understand the
        # folder as a whole — its primary role and groups of related files.
        # -----------------------------------------------------------------------
        session.phase = "analyzing"
        db.commit()

        folder_role: str = ""
        outlier_set: set[str] = set()
        # Maps filename → suggested subfolder name for related-file groups
        file_to_group: dict[str, str] = {}

        try:
            role_prompt = render_folder_role_prompt(folder_summaries)
            log.debug("LLM FOLDER ROLE REQUEST")
            raw_role = ai.generate(role_prompt)
            log.debug("LLM FOLDER ROLE RESPONSE\n%s", raw_role)
            role_result = parse_folder_role_response(raw_role)
            if role_result.parse_error:
                log.warning("LLM FOLDER ROLE PARSE ERROR  error=%s", role_result.parse_error)
            else:
                folder_role = role_result.role
                outlier_set = set(role_result.outlier_files)
                log.info("LLM FOLDER ROLE  role=%r  outliers=%s", folder_role, outlier_set)
        except Exception as exc:
            log.warning("Folder role analysis failed: %s", exc)

        try:
            related_prompt = render_related_files_prompt(folder_summaries)
            log.debug("LLM RELATED FILES REQUEST")
            raw_related = ai.generate(related_prompt)
            log.debug("LLM RELATED FILES RESPONSE\n%s", raw_related)
            related_groups = parse_related_files_response(raw_related)
            for group in related_groups:
                for fname in group.files:
                    file_to_group[fname] = group.subfolder
            log.info("LLM RELATED FILES  groups=%d  mapped_files=%d", len(related_groups), len(file_to_group))

            # Maps filename → list of other filenames in the same related group
            file_to_related_group_files: dict[str, list[str]] = {}
            for group in related_groups:
                for fname in group.files:
                    file_to_related_group_files[fname] = [f for f in group.files if f != fname]
        except Exception as exc:
            log.warning("Related files analysis failed: %s", exc)
            file_to_related_group_files = {}

        # -----------------------------------------------------------------------
        # Phase 2 — "deciding": for each file run rename-check then organize.
        # The frontend shows per-file results appearing as they complete.
        # -----------------------------------------------------------------------
        session.phase = "deciding"
        session.processed_files = "0"
        db.commit()

        # Keep a snapshot of content_type per file — was set in phase 1 loop above.
        # We need to re-extract only if the file hasn't been processed yet.
        _content_type_cache: dict[str, str] = {
            str(fr.path): fr.content_type for fr in files
        }

        for idx, file_record in enumerate(files):
            if _is_cancelled(session_id):
                log.info("Scan cancelled (deciding): session=%s at file %d/%d", session_id, idx, len(files))
                session.phase = None
                session.status = SessionStatus.cancelled
                db.commit()
                _clear_cancel(session_id)
                return

            try:
                file_start = time.monotonic()
                summary = summaries.get(str(file_record.path), "")

                # --- Sub-step 2a: rename check ---
                # Ask the LLM whether the current filename clearly represents the content.
                rename_prompt = render_rename_prompt(
                    name=file_record.name,
                    ext=file_record.extension,
                    size=file_record.size,
                    summary=summary,
                )
                log.debug("LLM RENAME REQUEST  file=%s", file_record.name)
                raw_rename = ai.generate(rename_prompt)
                log.debug("LLM RENAME RESPONSE  file=%s response=%s", file_record.name, raw_rename)
                rename_decision = parse_rename_response(raw_rename, file_record.name)
                if rename_decision.parse_error:
                    log.warning("LLM RENAME PARSE ERROR  file=%s error=%s", file_record.name, rename_decision.parse_error)
                log.info(
                    "LLM RENAME  file=%s → should_rename=%s proposed=%s confidence=%.2f",
                    file_record.name, rename_decision.should_rename,
                    rename_decision.filename, rename_decision.confidence,
                )

                # --- Sub-step 2b: folder organization ---
                # Use the (potentially renamed) filename as the basis for the organize prompt
                # so the LLM knows the intended name when deciding the category/path.
                _related_key = rename_decision.filename if rename_decision.filename in file_to_related_group_files else file_record.name
                decision_prompt = render_decision_prompt(
                    name=rename_decision.filename,
                    ext=file_record.extension,
                    size=file_record.size,
                    summary=summary,
                    folder_tree=folder_tree,
                    folder_role=folder_role or None,
                    is_outlier=rename_decision.filename in outlier_set or file_record.name in outlier_set,
                    related_group=file_to_group.get(rename_decision.filename) or file_to_group.get(file_record.name),
                    related_files=file_to_related_group_files.get(_related_key) or [],
                )
                log.debug("LLM DECISION REQUEST  file=%s", file_record.name)
                raw_response = ai.generate(decision_prompt)
                log.debug("LLM DECISION RESPONSE  file=%s response=%s", file_record.name, raw_response)
                ai_decision = parse_response(raw_response)

                if ai_decision.parse_error:
                    log.warning(
                        "LLM PARSE ERROR  file=%s error=%s raw=\n%s",
                        file_record.name, ai_decision.parse_error, raw_response,
                    )
                else:
                    log.info(
                        "LLM DECISION  file=%s → category=%s confidence=%.2f proposed=%s reasoning=%s",
                        file_record.name, ai_decision.category, ai_decision.confidence,
                        ai_decision.filename, ai_decision.reasoning,
                    )

                proposal = evaluate(
                    file_record=file_record,
                    ai_decision=ai_decision,
                    scan_root=directory,
                    session_id=session_id,
                )

                op = Operation(
                    id=proposal.id,
                    session_id=session_id,
                    source_path=proposal.source_path,
                    dest_path=proposal.dest_path,
                    original_name=proposal.original_name,
                    proposed_name=proposal.proposed_name,
                    category=proposal.category,
                    confidence=proposal.confidence,
                    ai_reasoning=proposal.ai_reasoning,
                    file_hash=proposal.file_hash,
                    status=proposal.status,
                    elapsed_seconds=round(time.monotonic() - file_start, 3),
                )
                db.add(op)
            except Exception as exc:
                log.error("Error processing %s: %s", file_record.path, exc)
                op = Operation(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    source_path=str(file_record.path),
                    dest_path=str(file_record.path),
                    original_name=file_record.name,
                    proposed_name=file_record.name,
                    category="Other",
                    confidence=0.0,
                    ai_reasoning="",
                    file_hash=file_record.sha256,
                    status=OperationStatus.error,
                    error=str(exc),
                )
                db.add(op)

            session.processed_files = str(idx + 1)
            db.commit()

        session.phase = None
        session.status = SessionStatus.applied if dry_run else SessionStatus.pending
        session.elapsed_seconds = round(time.monotonic() - scan_start, 3)
        db.commit()
        log.info("Scan complete: session=%s files=%d elapsed=%.2fs", session_id, len(files), session.elapsed_seconds)

    except Exception as exc:
        log.error("Scan worker failure: %s", exc, exc_info=True)
        if session:
            session.phase = None
            session.status = SessionStatus.error
            db.commit()
    finally:
        _clear_cancel(session_id)
        db.close()
