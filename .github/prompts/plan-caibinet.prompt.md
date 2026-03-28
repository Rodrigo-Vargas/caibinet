# Plan: Caibinet — Local AI File Organizer

**Stack:** Electron + React (TypeScript), Python (FastAPI) sidecar for all backend logic, SQLite for persistence, Ollama for local LLM, OS app-data dir for storage.

The architecture separates concerns cleanly: Electron manages the window and spawns a local Python FastAPI HTTP server; the React renderer calls that server directly over `localhost`; all file logic, AI calls, and the audit log live purely in Python.

---

## Folder Structure

```
caibinet/
├── electron/
│   ├── main.ts              # BrowserWindow, app lifecycle
│   ├── preload.ts           # contextBridge (minimal — most IPC is HTTP)
│   └── sidecar.ts           # spawn/kill Python process, port negotiation
├── src/                     # React renderer
│   ├── api/                 # typed fetch wrappers against Python HTTP API
│   ├── components/
│   │   ├── FileList/
│   │   ├── ProposedChanges/
│   │   ├── UndoHistory/
│   │   └── Settings/
│   ├── hooks/               # useOperations, useScan, useUndo, useSettings
│   ├── pages/               # Dashboard, History, Settings
│   ├── store/               # Zustand global state
│   └── main.tsx
├── core/                    # Python FastAPI backend
│   ├── main.py              # FastAPI app factory, startup/shutdown
│   ├── config.py            # Pydantic BaseSettings (reads env + app-data dir)
│   ├── api/routes/
│   │   ├── scan.py          # POST /scan
│   │   ├── operations.py    # GET/POST /operations
│   │   ├── undo.py          # POST /undo, POST /undo/batch, POST /undo/all
│   │   └── settings.py      # GET/PUT /settings
│   ├── engine/
│   │   ├── scanner.py       # recursive dir walk, ignore rules
│   │   ├── extractor.py     # plain text, PDF (PyMuPDF), metadata
│   │   ├── decision.py      # parse AI JSON, confidence gate, dedup check
│   │   └── executor.py      # atomic move, hash verify, write event log
│   ├── ai/
│   │   ├── base.py          # AIProvider ABC: generate(prompt, context) → str
│   │   ├── ollama.py        # OllamaProvider — POST /api/generate
│   │   └── prompts.py       # Jinja2 prompt templates, JSON schema enforcement
│   ├── db/
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── session.py       # engine, SessionLocal, get_db dependency
│   │   └── migrations/      # Alembic env + versions
│   └── requirements.txt
├── package.json
├── tsconfig.json
├── vite.config.ts           # Vite for renderer, watches src/
└── electron-builder.config.js
```

---

## Database Schema (SQLite via SQLAlchemy)

**`sessions`** — groups a scan run
`id · uuid`, `created_at`, `label · str`, `directory · str`, `status · enum(pending|applied|undone)`

**`operations`** — one row per proposed/applied file action
`id · uuid`, `session_id · fk`, `created_at`, `source_path`, `dest_path`, `original_name`, `proposed_name`, `category`, `ai_reasoning · text`, `confidence · float`, `file_hash · str`, `status · enum(pending|approved|applied|undone|skipped)`, `error · text nullable`

**`settings`** — key/value store
`key · str pk`, `value · json`

---

## Implementation Plan

### Phase 1 — Project Scaffold (Days 1–2)

1. Run `npm create electron-vite@latest caibinet -- --template react-ts` to get the Electron + React + Vite base.
2. Add renderer dependencies: `react-query`, `zustand`, `tailwindcss`, `clsx`, `lucide-react`.
3. Create `core/requirements.txt` with: `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `pydantic[settings]`, `pymupdf`, `httpx`, `jinja2`, `python-multipart`, `platformdirs`.
4. Set up Alembic in `core/db/migrations/` and write the initial migration creating the three tables above.
5. Write `core/config.py` using `pydantic-settings` — reads `CAIBINET_DATA_DIR` from env, defaulting to `~/.local/share/caibinet` (Linux) / `%APPDATA%\caibinet` (Windows) via `platformdirs`.

### Phase 2 — Electron ↔ Python IPC (Day 3)

6. Write `electron/sidecar.ts`: on app `ready`, find a free port, spawn `python core/main.py --port <PORT>` (or a packaged executable), expose the port via `ipcMain`. Kill the process on `will-quit`.
7. Write `electron/preload.ts`: expose `window.electronAPI.getBackendPort()` via `contextBridge`.
8. Write `src/api/client.ts`: a typed `fetch` wrapper that reads the port from `window.electronAPI` and provides `scan()`, `getOperations()`, `approveOperation()`, `undo()`, `getSettings()`, `putSettings()`.

### Phase 3 — Content Extraction (Days 4–5)

9. `core/engine/scanner.py`: `scan_directory(path, ignore_patterns) → List[FileRecord]`. Walks the tree, applies glob-based ignore rules (loaded from settings), computes SHA-256 per file, returns file size, mime type, relative path.
10. `core/engine/extractor.py`: `extract(file_record) → str`. Dispatches on mime:
    - `text/*` → read raw (truncated to 4 000 chars)
    - `application/pdf` → `pymupdf.open()` → extract first 3 pages as text
    - Others → use file metadata (name, size, extension) only, mark `content_type=metadata_only`

### Phase 4 — AI Provider Layer (Days 5–6)

11. `core/ai/base.py`: define `AIProvider` ABC with `generate(prompt: str) → str` and a `ProviderConfig` dataclass (model name, base URL, timeout).
12. `core/ai/ollama.py`: `OllamaProvider(AIProvider)` — `POST http://{host}:{port}/api/generate` with `stream=False`, returns `response["response"]`. Includes health-check `ping()` method for settings validation.
13. `core/ai/prompts.py`: Jinja2 template that renders the structured prompt (see below), plus a `parse_response(raw: str) → AIDecision` function that attempts `json.loads`, falls back to regex extraction on `{...}` block, validates required fields, defaults `confidence` to `0.0` on parse failure.

#### Structured Prompt Template

```
You are a file organization assistant. Analyze the content below and return **only** valid JSON — no explanation, no markdown.
Rules: use lowercase_underscores for filename, do not invent facts, be consistent across similar files.
Output exactly: {"filename": "...", "category": "Finance|Work|Personal|Media|Code|Other", "path": "relative/suggested/path/", "confidence": 0.0–1.0, "reasoning": "one sentence"}
File metadata: name={{ name }}, extension={{ ext }}, size={{ size }}
Content: {{ content }}
```

### Phase 5 — Decision Engine (Day 7)

14. `core/engine/decision.py`: `evaluate(file_record, ai_decision, settings) → OperationProposal`. Checks:
    - `confidence < settings.min_confidence` → mark `status=skipped`, reason logged
    - Proposed dest path collides with existing file → append `_2`, `_3`, etc.
    - Source == dest → mark `status=skipped`
    - Returns `OperationProposal` ready to persist

### Phase 6 — Execution & Undo Engine (Days 8–9)

15. `core/engine/executor.py`: `apply(operation: Operation) → None`:
    - Verify source still exists and SHA-256 matches stored hash (safety check)
    - `os.makedirs(dest_dir, exist_ok=True)`
    - `shutil.move(source, dest)` — this is the only mutation
    - Update `operation.status = "applied"` in DB
    - On any exception: revert (source still exists because move failed), set `status=error`
16. `undo(operation_id) → None`: reverse the move (`shutil.move(dest, source)`), verify dest exists, update status to `"undone"`.
17. `undo_batch(session_id) → List[Result]`: iterate operations for session in **reverse applied order**, undo each, collect results.
18. `undo_all() → List[Result]`: same across all sessions.

### Phase 7 — API Routes (Day 9)

19. `core/api/routes/scan.py`: `POST /scan` — body `{directory, dry_run: bool}`. Creates a `Session`, runs scanner → extractor → AI → decision in a background task (FastAPI `BackgroundTasks`), returns `session_id` immediately. Client polls `GET /sessions/{id}/status`.
20. `core/api/routes/operations.py`: `GET /operations?session_id=&status=` for listing; `POST /operations/{id}/approve` and `POST /operations/{id}/skip` to set approval; `POST /sessions/{id}/apply` to execute all approved operations.
21. `core/api/routes/undo.py`: `POST /undo/{operation_id}`, `POST /undo/session/{session_id}`, `POST /undo/all`.
22. `core/api/routes/settings.py`: `GET /settings`, `PUT /settings` (model name, Ollama URL, `min_confidence`, ignore patterns).

### Phase 8 — React UI (Days 10–12)

23. **Dashboard page** `src/pages/Dashboard.tsx`: directory picker (Electron `showOpenDialog` via preload), "Scan" button, live progress bar polling session status, proposed changes table.
24. **ProposedChanges component** `src/components/ProposedChanges/`: table with columns — original name, proposed name, category, suggested path, confidence badge (green/yellow/red), per-row Approve/Skip toggle. Bulk "Approve All" button. "Apply Changes" CTA disabled until at least one approved.
25. **UndoHistory page** `src/pages/History.tsx`: timeline of sessions, expandable to show per-file operations with their status, per-session "Undo All" button, per-row undo.
26. **Settings page** `src/pages/Settings.tsx`: Ollama URL + model picker (calls `GET /api/tags` on Ollama), confidence threshold slider, ignore patterns editor, test connection button.

### Phase 9 — Packaging (Days 13–14)

27. Add `electron-builder.config.js`: target `AppImage` for Linux, `NSIS` installer for Windows. Bundle the Python sidecar via `extraResources` (PyInstaller one-file build ships as `core.bin` / `core.exe`).
28. Add build scripts to `package.json`: `build:core` (runs `pyinstaller core/main.py --onefile`), `build:app` (runs electron-builder consuming the output).

---

## Key Interface Definitions

### `AIProvider` ABC (Python)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

@dataclass
class ProviderConfig:
    model: str
    base_url: str
    timeout: int = 30

class AIProvider(ABC):
    config: ProviderConfig

    @abstractmethod
    def generate(self, prompt: str) -> str: ...

    @abstractmethod
    def ping(self) -> bool: ...

    @abstractmethod
    def list_models(self) -> List[str]: ...
```

### `OllamaProvider` (Python)

```python
import httpx
from .base import AIProvider, ProviderConfig

class OllamaProvider(AIProvider):
    def __init__(self, config: ProviderConfig):
        self.config = config

    def generate(self, prompt: str) -> str:
        r = httpx.post(
            f"{self.config.base_url}/api/generate",
            json={"model": self.config.model, "prompt": prompt, "stream": False},
            timeout=self.config.timeout,
        )
        r.raise_for_status()
        return r.json()["response"]

    def ping(self) -> bool:
        try:
            httpx.get(f"{self.config.base_url}/api/tags", timeout=3).raise_for_status()
            return True
        except Exception:
            return False

    def list_models(self) -> list[str]:
        r = httpx.get(f"{self.config.base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
```

### `OperationProposal` (Pydantic)

```python
from pydantic import BaseModel
from enum import Enum

class OperationStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    applied = "applied"
    undone = "undone"
    skipped = "skipped"
    error = "error"

class OperationProposal(BaseModel):
    session_id: str
    source_path: str
    dest_path: str
    original_name: str
    proposed_name: str
    category: str
    confidence: float
    ai_reasoning: str
    file_hash: str
    status: OperationStatus = OperationStatus.pending
```

### `UndoResult` (Pydantic)

```python
class UndoResult(BaseModel):
    operation_id: str
    success: bool
    error: str | None = None
```

### `src/api/client.ts` (TypeScript)

```typescript
const base = () => `http://localhost:${window.electronAPI.getBackendPort()}`;

export const api = {
  scan: (directory: string, dryRun: boolean) =>
    fetch(`${base()}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ directory, dry_run: dryRun }),
    }).then((r) => r.json()),

  getOperations: (sessionId: string) =>
    fetch(`${base()}/operations?session_id=${sessionId}`).then((r) => r.json()),

  approveOperation: (id: string) =>
    fetch(`${base()}/operations/${id}/approve`, { method: "POST" }).then((r) => r.json()),

  applySession: (sessionId: string) =>
    fetch(`${base()}/sessions/${sessionId}/apply`, { method: "POST" }).then((r) => r.json()),

  undoOperation: (id: string) =>
    fetch(`${base()}/undo/${id}`, { method: "POST" }).then((r) => r.json()),

  undoSession: (sessionId: string) =>
    fetch(`${base()}/undo/session/${sessionId}`, { method: "POST" }).then((r) => r.json()),

  getSettings: () =>
    fetch(`${base()}/settings`).then((r) => r.json()),

  putSettings: (settings: Record<string, unknown>) =>
    fetch(`${base()}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then((r) => r.json()),
};
```

---

## Verification Plan

- **Unit tests** (`pytest core/`): extractor on a known PDF → expected text; decision engine with low-confidence AI response → `status=skipped`; executor apply → undo → file back at original path.
- **Mock Ollama server**: returns deterministic JSON for integration tests; assert final DB operation states.
- **Manual smoke test**: scan 5 mixed files in dry-run, approve 2, apply, verify moves in filesystem, undo session, verify revert.
- **Packaging**: `npm run build:core && npm run dist` on Linux (AppImage) and Windows (NSIS).

---

## Future Extensions

- **Image OCR**: add `pytesseract` + `Pillow` to extractor, dispatch on `image/*` mime types.
- **LM Studio / OpenAI-compat providers**: implement `OpenAICompatProvider(AIProvider)` pointing at any `/v1/chat/completions` endpoint.
- **Auto-mode**: threshold-gated (`confidence > 0.9`) fully automatic processing with a background scheduler (APScheduler) and folder watcher (`watchdog`).
- **Duplicate detection**: cluster files by content hash and near-duplicate embeddings, propose consolidation.
- **Plugin system**: `core/plugins/` directory where additional extractors register via Python entry points.

---

## Architecture Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Desktop shell | Electron + React | Mature ecosystem, simpler cross-platform packaging vs Tauri |
| Backend language | Pure Python | Single-language stack; rich AI/file libs; avoids Rust/Python FFI |
| IPC mechanism | HTTP (FastAPI on localhost) | Clean REST contract, independently testable, shell-agnostic |
| Data location | OS app-data dir | Follows platform conventions (`platformdirs`) |
| Undo strategy | Event sourcing in SQLite | Full audit trail, idempotent replay, no destructive log writes |
| AI output format | Strict JSON schema | Deterministic parsing, confidence-gated decisions, no hallucination ambiguity |
