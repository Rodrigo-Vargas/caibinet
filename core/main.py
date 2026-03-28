"""FastAPI application factory and entry point."""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .api.routes import scan, operations, undo, settings as settings_route

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# --- LLM file logging ---------------------------------------------------------
# Always write prompt/response DEBUG records from core.ai to logs/llm.log,
# regardless of whether CAIBINET_DEBUG_LLM is set for the console.
_logs_dir = Path(__file__).resolve().parent.parent / "logs"
_logs_dir.mkdir(exist_ok=True)
_llm_file_handler = logging.handlers.RotatingFileHandler(
    _logs_dir / "llm.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB per file
    backupCount=5,
    encoding="utf-8",
)
_llm_file_handler.setLevel(logging.DEBUG)
_llm_file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
)
_llm_logger = logging.getLogger("core.ai")
_llm_logger.setLevel(logging.DEBUG)
_llm_logger.addHandler(_llm_file_handler)
# ------------------------------------------------------------------------------

# Set CAIBINET_DEBUG_LLM=1 to see full prompt/response payloads in the logs
if os.getenv("CAIBINET_DEBUG_LLM") == "1":
    logging.getLogger("core.ai").setLevel(logging.DEBUG)
    log.info("LLM I/O debug logging enabled (core.ai → DEBUG)")


def _run_migrations() -> None:
    """Run any pending Alembic migrations against the live database."""
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_command
        from sqlalchemy import create_engine, inspect

        ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
        alembic_cfg = AlembicConfig(str(ini_path))
        # Override the URL so we always migrate the actual runtime DB,
        # not the hard-coded path in alembic.ini.
        alembic_cfg.set_main_option("sqlalchemy.url", settings.db_url)

        # If the DB already has our tables but no alembic_version table
        # (i.e. it was bootstrapped via create_all), stamp it at 0001_initial
        # so that only the delta migrations (0002+) are applied.
        engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
        with engine.connect() as conn:
            inspector = inspect(conn)
            has_sessions = "sessions" in inspector.get_table_names()
            has_alembic = "alembic_version" in inspector.get_table_names()
            if has_sessions and not has_alembic:
                log.info("Existing DB has no alembic_version; stamping at 0001_initial")
                alembic_command.stamp(alembic_cfg, "0001_initial")

        alembic_command.upgrade(alembic_cfg, "head")
        log.info("Database migrations applied (alembic upgrade head)")
    except Exception as exc:
        log.error("Migration failed: %s", exc, exc_info=True)
        raise


def create_app() -> FastAPI:
    settings.ensure_data_dir()
    _run_migrations()

    app = FastAPI(
        title="Caibinet API",
        version="0.1.0",
        description="Local AI File Organizer — Python backend",
    )

    # Allow the Electron renderer (any localhost origin) to call the API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    app.include_router(scan.router, tags=["scan"])
    app.include_router(operations.router, tags=["operations"])
    app.include_router(undo.router, tags=["undo"])
    app.include_router(settings_route.router, tags=["settings"])

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": "0.1.0"}

    # Log all registered routes at startup for easier debugging
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", str(route))
        if methods:
            log.info("Route registered: %s %s", ",".join(sorted(methods)), path)

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Caibinet Python sidecar")
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    log.info("Starting Caibinet backend on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
