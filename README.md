# Caibinet — Local AI File Organizer

Caibinet scans a folder, asks a local LLM (via [Ollama](https://ollama.com)) to propose a clean filename + directory for each file, then lets you review and apply the changes — with full undo support.

## Stack

| Layer | Technology |
|---|---|
| Desktop shell | Electron 31 + Vite |
| Renderer | React 18 + TypeScript + Tailwind |
| Backend | Python 3.11+ + FastAPI + Uvicorn |
| AI | Ollama (local LLM) |
| Database | SQLite via SQLAlchemy |
| State | Zustand + TanStack Query |

## Quick start (development)

### Prerequisites
- Node.js ≥ 18
- Python ≥ 3.11
- [Ollama](https://ollama.com) running locally with at least one model pulled (e.g. `ollama pull llama3`)

### 1. Install Node dependencies
```bash
npm install
```

### 2. Install Python dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r core/requirements.txt
```

### 3. Run in dev mode
```bash
npm run dev
```

Electron will spawn the FastAPI sidecar automatically and open the UI.

## Running tests

```bash
source .venv/bin/activate
pytest
```

## Building for distribution

```bash
# 1. Bundle Python sidecar (requires pyinstaller in venv)
npm run build:core

# 2. Build Electron app (AppImage on Linux, NSIS on Windows)
npm run dist
```

## Architecture

```
caibinet/
├── electron/        # Main process: BrowserWindow, sidecar spawn
├── src/             # React renderer: pages, components, API client
└── core/            # Python FastAPI backend
    ├── ai/          # Ollama provider + prompt templates
    ├── engine/      # Scanner, extractor, decision, executor
    ├── api/routes/  # FastAPI route handlers
    └── db/          # SQLAlchemy models + Alembic migrations
```

The renderer never touches the filesystem directly — all file logic lives in Python and is accessed via a local HTTP API on `127.0.0.1:<random_port>`.

## License

MIT
