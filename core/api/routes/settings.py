"""Settings routes — GET/PUT /settings, GET /settings/models, GET /health/llm."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from ...config import settings as app_settings
from ...db.models import SettingEntry, SummaryCache
from ...db.session import get_db
from ...ai.ollama import OllamaProvider
from ...ai.base import ProviderConfig

log = logging.getLogger(__name__)

router = APIRouter()


class SettingsOut(BaseModel):
    ollama_url: str
    ollama_model: str
    ollama_timeout: int
    ignore_patterns: List[str]
    max_files: int
    context_aware: bool
    summary_cache_ttl_minutes: int
    ocr_enabled: bool


class SettingsIn(BaseModel):
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_timeout: Optional[int] = None
    ignore_patterns: Optional[List[str]] = None
    max_files: Optional[int] = None
    context_aware: Optional[bool] = None
    summary_cache_ttl_minutes: Optional[int] = None
    ocr_enabled: Optional[bool] = None


def _load_settings(db: DBSession) -> SettingsOut:
    """Merge DB overrides on top of env/default app_settings."""
    rows = {r.key: r.value for r in db.query(SettingEntry).all()}

    def _get(key: str, default: Any) -> Any:
        if key in rows:
            try:
                return json.loads(rows[key])
            except json.JSONDecodeError:
                return rows[key]
        return default

    return SettingsOut(
        ollama_url=_get("ollama_url", app_settings.ollama_url),
        ollama_model=_get("ollama_model", app_settings.ollama_model),
        ollama_timeout=_get("ollama_timeout", app_settings.ollama_timeout),
        ignore_patterns=_get("ignore_patterns", app_settings.ignore_patterns),
        max_files=_get("max_files", app_settings.max_files),
        context_aware=_get("context_aware", app_settings.context_aware),
        summary_cache_ttl_minutes=_get("summary_cache_ttl_minutes", app_settings.summary_cache_ttl_minutes),
        ocr_enabled=_get("ocr_enabled", app_settings.ocr_enabled),
    )


def _upsert(key: str, value: Any, db: DBSession) -> None:
    row = db.query(SettingEntry).filter(SettingEntry.key == key).first()
    serialized = json.dumps(value)
    if row:
        row.value = serialized
    else:
        db.add(SettingEntry(key=key, value=serialized))


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: DBSession = Depends(get_db)) -> SettingsOut:
    return _load_settings(db)


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, db: DBSession = Depends(get_db)) -> SettingsOut:
    updates: Dict[str, Any] = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        _upsert(key, value, db)
        # Also update the in-process config for the running sidecar session
        if hasattr(app_settings, key):
            object.__setattr__(app_settings, key, value)
    db.commit()
    return _load_settings(db)


class CacheClearResult(BaseModel):
    deleted: int


@router.delete("/cache/summary", response_model=CacheClearResult)
def clear_summary_cache(db: DBSession = Depends(get_db)) -> CacheClearResult:
    """Delete all cached LLM file summaries."""
    deleted = db.query(SummaryCache).delete()
    db.commit()
    log.info("Summary cache cleared: %d entries deleted", deleted)
    return CacheClearResult(deleted=deleted)


@router.get("/settings/models", response_model=List[str])
def list_models(db: DBSession = Depends(get_db)) -> List[str]:
    current = _load_settings(db)
    provider = OllamaProvider(
        ProviderConfig(model=current.ollama_model, base_url=current.ollama_url)
    )
    try:
        return provider.list_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {exc}") from exc


class LLMHealthResponse(BaseModel):
    ok: bool
    detail: str
    model: str
    ollama_url: str


class LLMCheckRequest(BaseModel):
    ollama_url: str
    ollama_model: str


def _check_llm(ollama_url: str, ollama_model: str) -> LLMHealthResponse:
    """Shared logic: check reachability and model availability for a given URL+model."""
    log.info("LLM health check: url=%s model=%s", ollama_url, ollama_model)
    provider = OllamaProvider(ProviderConfig(model=ollama_model, base_url=ollama_url))

    if not provider.ping():
        log.warning("LLM health check FAILED: Ollama unreachable at %s", ollama_url)
        return LLMHealthResponse(
            ok=False,
            detail=f"Cannot reach Ollama at {ollama_url}",
            model=ollama_model,
            ollama_url=ollama_url,
        )

    try:
        available_models = provider.list_models()
    except Exception as exc:
        log.warning("LLM health check FAILED: could not list models from %s: %s", ollama_url, exc)
        return LLMHealthResponse(
            ok=False,
            detail=f"Ollama is reachable but failed to list models: {exc}",
            model=ollama_model,
            ollama_url=ollama_url,
        )

    if ollama_model not in available_models:
        log.warning(
            "LLM health check FAILED: model '%s' not in available models %s",
            ollama_model, available_models,
        )
        return LLMHealthResponse(
            ok=False,
            detail=f"Model '{ollama_model}' is not available. Pull it with: ollama pull {ollama_model}",
            model=ollama_model,
            ollama_url=ollama_url,
        )

    log.info("LLM health check OK: model=%s available_models=%s", ollama_model, available_models)
    return LLMHealthResponse(ok=True, detail="LLM is ready", model=ollama_model, ollama_url=ollama_url)


@router.get("/health/llm", response_model=LLMHealthResponse, tags=["health"])
def llm_health(db: DBSession = Depends(get_db)) -> LLMHealthResponse:
    """Check the configured Ollama instance using persisted settings."""
    current = _load_settings(db)
    return _check_llm(current.ollama_url, current.ollama_model)


@router.post("/health/llm/check", response_model=LLMHealthResponse, tags=["health"])
def llm_health_check(body: LLMCheckRequest) -> LLMHealthResponse:
    """Ad-hoc health check against a specific URL+model (used by Settings Test button)."""
    return _check_llm(body.ollama_url, body.ollama_model)
