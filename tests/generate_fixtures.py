"""
Generate a dummy folder tree with many different file types for use in tests.

Usage:
    python tests/generate_fixtures.py              # creates tests/fixtures/
    python tests/generate_fixtures.py /tmp/mydir   # creates files in given path
"""

from __future__ import annotations

import argparse
import io
import json
import os
import struct
import zipfile
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers to build minimal valid binary files
# ---------------------------------------------------------------------------

def _png_1x1(r: int = 255, g: int = 0, b: int = 0) -> bytes:
    """Return bytes of a minimal 1×1 RGB PNG."""
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = chunk(b"IHDR", ihdr_data)
    raw_row = b"\x00" + bytes([r, g, b])
    idat = chunk(b"IDAT", zlib.compress(raw_row))
    iend = chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _jpeg_1x1() -> bytes:
    """Return bytes of a minimal valid JPEG (1×1 black pixel)."""
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
        0xFF, 0xDB, 0x00, 0x43, 0x00,
        *([0x08] * 64),
        0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01,
        0x01, 0x01, 0x11, 0x00,
        0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01,
        0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
        0x0A, 0x0B,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
        0xF5, 0x0A, 0xFF, 0xD9,
    ])


def _gif_1x1() -> bytes:
    """Return bytes of a minimal 1×1 GIF."""
    return (
        b"GIF89a"
        b"\x01\x00\x01\x00\x80\xFF\x00"
        b"\xFF\xFF\xFF\x00\x00\x00"
        b"!\xF9\x04\x00\x00\x00\x00\x00"
        b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )


def _bmp_1x1() -> bytes:
    """Return bytes of a minimal 1×1 BMP."""
    file_size = 58
    pixel_data_offset = 54
    return struct.pack(
        "<2sIHHI",
        b"BM", file_size, 0, 0, pixel_data_offset
    ) + struct.pack(
        "<IIIHHIIIIII",
        40, 1, 1, 1, 24,
        0, 4, 2835, 2835, 0, 0
    ) + b"\x00\x00\xFF\x00"


def _pdf_minimal(title: str = "Sample") -> bytes:
    """Return bytes of a minimal single-page PDF."""
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (" + title.encode() + b") Tj ET\n"
        b"endstream\nendobj\n"
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
    )
    return content


def _zip_with_text(filename: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(filename, text)
    return buf.getvalue()


def _wav_silence(duration_ms: int = 100) -> bytes:
    """Return bytes of a minimal PCM WAV with silence."""
    sample_rate = 8000
    num_samples = sample_rate * duration_ms // 1000
    audio_data = b"\x00" * num_samples  # 8-bit mono silence
    data_size = len(audio_data)
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate, 1, 8)
        + b"data"
        + struct.pack("<I", data_size)
    )
    return header + audio_data


# ---------------------------------------------------------------------------
# File specifications
# ---------------------------------------------------------------------------

FILES: list[dict] = [
    # ── Documents ───────────────────────────────────────────────────────────
    {
        "rel": "documents/report_q1_2025.txt",
        "text": (
            "Q1 2025 Financial Report\n"
            "========================\n\n"
            "Revenue: $1,200,000\n"
            "Expenses: $850,000\n"
            "Net profit: $350,000\n\n"
            "Key highlights:\n"
            "- Product line A exceeded targets by 12%\n"
            "- New partnership signed with Acme Corp\n"
            "- Headcount grew from 45 to 52\n"
        ),
    },
    {
        "rel": "documents/meeting_notes_2025-03-10.md",
        "text": (
            "# Team Meeting — 10 March 2025\n\n"
            "**Attendees:** Alice, Bob, Carol, Dave\n\n"
            "## Agenda\n"
            "1. Sprint retrospective\n"
            "2. Roadmap review\n"
            "3. Hiring update\n\n"
            "## Action items\n"
            "- [ ] Alice: finalize API spec by Friday\n"
            "- [ ] Bob: set up CI pipeline\n"
            "- [ ] Carol: interview candidate pool\n"
        ),
    },
    {
        "rel": "documents/contract_vendor_acme.txt",
        "text": (
            "SERVICE AGREEMENT\n\n"
            "This agreement is entered into between Caibinet Inc. (\"Client\") "
            "and Acme Corp (\"Vendor\").\n\n"
            "1. SERVICES\n"
            "Vendor shall provide cloud hosting services as described in Exhibit A.\n\n"
            "2. TERM\n"
            "This agreement begins on 1 January 2025 and continues for 12 months.\n\n"
            "3. PAYMENT\n"
            "Client shall pay $2,000/month within 30 days of invoice.\n"
        ),
    },
    {
        "rel": "documents/resume_jane_doe.txt",
        "text": (
            "Jane Doe\njane.doe@email.com | +1-555-0100\n\n"
            "EXPERIENCE\n"
            "─────────────────────────────────────────\n"
            "Senior Software Engineer  @ TechCorp  2020–present\n"
            "  • Led migration of monolith to microservices\n"
            "  • Reduced p99 latency by 40%\n\n"
            "Software Engineer         @ StartupXYZ  2017–2020\n"
            "  • Built real-time data pipeline (Kafka + Spark)\n\n"
            "EDUCATION\n"
            "B.Sc. Computer Science, State University, 2017\n"
        ),
    },
    # ── PDFs ────────────────────────────────────────────────────────────────
    {"rel": "documents/invoice_2025_001.pdf", "bytes": _pdf_minimal("Invoice #2025-001")},
    {"rel": "documents/user_manual_v3.pdf",   "bytes": _pdf_minimal("User Manual v3.0")},
    {"rel": "documents/tax_return_2024.pdf",  "bytes": _pdf_minimal("Tax Return 2024")},
    # ── Spreadsheet-like CSVs ────────────────────────────────────────────────
    {
        "rel": "spreadsheets/sales_data_2025.csv",
        "text": (
            "date,product,units,revenue\n"
            "2025-01-05,Widget A,120,2400.00\n"
            "2025-01-12,Widget B,85,4250.00\n"
            "2025-02-03,Widget A,200,4000.00\n"
            "2025-02-19,Gadget X,14,2800.00\n"
            "2025-03-01,Widget B,95,4750.00\n"
        ),
    },
    {
        "rel": "spreadsheets/employee_roster.csv",
        "text": (
            "id,name,department,salary,start_date\n"
            "1,Alice Smith,Engineering,95000,2021-03-15\n"
            "2,Bob Jones,Marketing,72000,2019-07-01\n"
            "3,Carol White,Engineering,105000,2020-11-22\n"
            "4,Dave Brown,HR,65000,2022-01-10\n"
            "5,Eve Davis,Engineering,88000,2023-05-30\n"
        ),
    },
    # ── Code & configs ───────────────────────────────────────────────────────
    {
        "rel": "code/main.py",
        "text": (
            '#!/usr/bin/env python3\n"""Entry point for the data pipeline."""\n\n'
            "import argparse\nfrom pathlib import Path\n\n\n"
            "def parse_args() -> argparse.Namespace:\n"
            "    p = argparse.ArgumentParser()\n"
            '    p.add_argument("input", type=Path)\n'
            '    p.add_argument("--output", type=Path, default=Path("out"))\n'
            "    return p.parse_args()\n\n\n"
            "def main() -> None:\n"
            "    args = parse_args()\n"
            '    print(f"Processing {args.input} → {args.output}")\n\n\n'
            'if __name__ == "__main__":\n    main()\n'
        ),
    },
    {
        "rel": "code/utils.js",
        "text": (
            '"use strict";\n\n'
            "/**\n * Debounce a function call.\n"
            " * @param {Function} fn\n * @param {number} delay\n */\n"
            "function debounce(fn, delay) {\n  let timer;\n"
            "  return (...args) => {\n    clearTimeout(timer);\n"
            "    timer = setTimeout(() => fn(...args), delay);\n  };\n}\n\n"
            "module.exports = { debounce };\n"
        ),
    },
    {
        "rel": "code/styles.css",
        "text": (
            "/* Global styles */\n:root {\n  --primary: #4f46e5;\n"
            "  --bg: #f9fafb;\n  --text: #111827;\n}\n\n"
            "body {\n  margin: 0;\n  font-family: Inter, sans-serif;\n"
            "  background: var(--bg);\n  color: var(--text);\n}\n\n"
            ".btn {\n  padding: 0.5rem 1rem;\n  border-radius: 6px;\n"
            "  background: var(--primary);\n  color: #fff;\n  cursor: pointer;\n}\n"
        ),
    },
    {
        "rel": "code/config.json",
        "text": json.dumps({
            "app": "data-pipeline",
            "version": "1.0.0",
            "database": {"host": "localhost", "port": 5432, "name": "pipeline_db"},
            "workers": 4,
            "retry": {"max_attempts": 3, "backoff_seconds": 5},
        }, indent=2) + "\n",
    },
    {
        "rel": "code/docker-compose.yml",
        "text": (
            "version: '3.9'\nservices:\n"
            "  api:\n    build: .\n    ports:\n      - '8000:8000'\n"
            "    environment:\n      - DATABASE_URL=postgresql://user:pass@db/app\n"
            "    depends_on:\n      - db\n"
            "  db:\n    image: postgres:15\n"
            "    environment:\n      POSTGRES_USER: user\n"
            "      POSTGRES_PASSWORD: pass\n      POSTGRES_DB: app\n"
        ),
    },
    {
        "rel": "code/query.sql",
        "text": (
            "-- Monthly revenue by product\n"
            "SELECT\n"
            "    DATE_TRUNC('month', sale_date)  AS month,\n"
            "    product_name,\n"
            "    SUM(amount)                     AS total_revenue,\n"
            "    COUNT(*)                        AS transactions\n"
            "FROM sales\n"
            "WHERE sale_date >= '2025-01-01'\n"
            "GROUP BY 1, 2\n"
            "ORDER BY 1, 3 DESC;\n"
        ),
    },
    {
        "rel": "code/Makefile",
        "text": (
            ".PHONY: install test lint\n\n"
            "install:\n\tpip install -r requirements.txt\n\n"
            "test:\n\tpytest tests/ -v\n\n"
            "lint:\n\truff check . && mypy .\n"
        ),
    },
    # ── Images ───────────────────────────────────────────────────────────────
    {"rel": "images/photo_vacation_beach.png",  "bytes": _png_1x1(0, 120, 255)},
    {"rel": "images/logo_company.png",          "bytes": _png_1x1(79, 70, 229)},
    {"rel": "images/screenshot_dashboard.jpeg", "bytes": _jpeg_1x1()},
    {"rel": "images/avatar_profile.jpg",        "bytes": _jpeg_1x1()},
    {"rel": "images/banner_promo.gif",          "bytes": _gif_1x1()},
    {"rel": "images/icon_app.bmp",              "bytes": _bmp_1x1()},
    {
        "rel": "images/diagram_architecture.svg",
        "text": (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">\n'
            '  <rect x="10" y="10" width="80" height="40" fill="#4f46e5" rx="6"/>\n'
            '  <text x="50" y="35" fill="white" text-anchor="middle" font-size="12">Frontend</text>\n'
            '  <rect x="110" y="10" width="80" height="40" fill="#059669" rx="6"/>\n'
            '  <text x="150" y="35" fill="white" text-anchor="middle" font-size="12">Backend</text>\n'
            '  <line x1="90" y1="30" x2="110" y2="30" stroke="#374151" stroke-width="2"/>\n'
            '</svg>\n'
        ),
    },
    # ── Audio ────────────────────────────────────────────────────────────────
    {"rel": "audio/notification_sound.wav", "bytes": _wav_silence(200)},
    {"rel": "audio/podcast_intro.wav",      "bytes": _wav_silence(500)},
    # ── Archives ─────────────────────────────────────────────────────────────
    {
        "rel": "archives/project_backup.zip",
        "bytes": _zip_with_text("README.md", "# Project Backup\n\nArchived on 2025-03-25.\n"),
    },
    {
        "rel": "archives/assets_bundle.zip",
        "bytes": _zip_with_text("assets/placeholder.txt", "placeholder asset\n"),
    },
    # ── Logs ─────────────────────────────────────────────────────────────────
    {
        "rel": "logs/app_2025-03-20.log",
        "text": (
            "2025-03-20 08:01:03 INFO  server: Starting on port 8080\n"
            "2025-03-20 08:01:04 INFO  db: Connected to postgresql://localhost/app\n"
            "2025-03-20 09:15:22 WARN  auth: Failed login attempt for user=admin ip=10.0.0.5\n"
            "2025-03-20 11:42:55 ERROR worker: Task timed out after 30s job_id=abc-123\n"
            "2025-03-20 11:42:56 INFO  worker: Retrying job_id=abc-123 attempt=2\n"
            "2025-03-20 11:43:30 INFO  worker: Job completed job_id=abc-123\n"
            "2025-03-20 18:00:00 INFO  server: Graceful shutdown initiated\n"
        ),
    },
    {
        "rel": "logs/error_2025-03-21.log",
        "text": (
            "2025-03-21 03:14:07 ERROR api: Unhandled exception in /api/v1/export\n"
            "Traceback (most recent call last):\n"
            "  File 'app/routes/export.py', line 88, in handle_export\n"
            "    result = exporter.run(job)\n"
            "  File 'app/exporters/csv.py', line 42, in run\n"
            "    raise MemoryError('buffer exceeded 512 MB')\n"
            "MemoryError: buffer exceeded 512 MB\n"
        ),
    },
    # ── Config / data files ──────────────────────────────────────────────────
    {
        "rel": "configs/settings.ini",
        "text": (
            "[general]\napp_name = MyApp\ndebug = false\nlog_level = INFO\n\n"
            "[database]\nhost = localhost\nport = 5432\nname = myapp_db\n\n"
            "[cache]\nbackend = redis\nttl = 300\n"
        ),
    },
    {
        "rel": "configs/pyproject.toml",
        "text": (
            '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n\n'
            "[project]\n"
            'name = "my-package"\nversion = "0.1.0"\n'
            'description = "A sample Python package"\n'
            'requires-python = ">=3.11"\n'
            'dependencies = ["httpx>=0.27", "fastapi>=0.110"]\n\n'
            "[tool.ruff]\nline-length = 100\n"
            'select = ["E", "F", "I"]\n'
        ),
    },
    {
        "rel": "configs/.env.example",
        "text": (
            "# Copy to .env and fill in real values\n"
            "DATABASE_URL=postgresql://user:password@localhost:5432/mydb\n"
            "SECRET_KEY=change-me-please\n"
            "DEBUG=false\n"
            "ALLOWED_HOSTS=localhost,127.0.0.1\n"
        ),
    },
    {
        "rel": "configs/nginx.conf",
        "text": (
            "server {\n    listen 80;\n    server_name example.com;\n\n"
            "    location / {\n        proxy_pass http://127.0.0.1:8000;\n"
            "        proxy_set_header Host $host;\n"
            "        proxy_set_header X-Real-IP $remote_addr;\n    }\n\n"
            "    location /static/ {\n        alias /var/www/static/;\n"
            "        expires 30d;\n    }\n}\n"
        ),
    },
    # ── Misc binary ──────────────────────────────────────────────────────────
    {
        "rel": "misc/random_data.bin",
        "bytes": bytes(range(256)) * 4,
    },
    {
        "rel": "misc/empty_file.txt",
        "text": "",
    },
    {
        "rel": "misc/unicode_sample.txt",
        "text": (
            "English: Hello, World!\n"
            "Spanish: ¡Hola, Mundo!\n"
            "French: Bonjour, le Monde!\n"
            "Japanese: こんにちは世界！\n"
            "Arabic: مرحبا بالعالم\n"
            "Russian: Привет, мир!\n"
            "Emoji: 🎉🚀🔥💡\n"
        ),
    },
    {
        "rel": "misc/large_text.txt",
        "text": ("The quick brown fox jumps over the lazy dog. " * 50 + "\n") * 40,
    },
    # ── Nested sub-folder ────────────────────────────────────────────────────
    {
        "rel": "projects/website/index.html",
        "text": (
            "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
            "  <meta charset='UTF-8'/>\n  <title>Sample Page</title>\n</head>\n"
            "<body>\n  <h1>Hello from the test fixture!</h1>\n"
            "  <p>This file was auto-generated for testing.</p>\n</body>\n</html>\n"
        ),
    },
    {
        "rel": "projects/website/README.md",
        "text": "# Sample Website\n\nA placeholder project for fixture-based tests.\n",
    },
    {
        "rel": "projects/data-analysis/notebook_results.json",
        "text": json.dumps({
            "experiment": "ablation-study-v2",
            "date": "2025-03-22",
            "metrics": {
                "accuracy": 0.934,
                "f1": 0.921,
                "precision": 0.948,
                "recall": 0.895,
            },
            "hyperparameters": {"lr": 0.001, "epochs": 50, "batch_size": 32},
            "notes": "Best run so far. Dropout=0.3 helped significantly.",
        }, indent=2) + "\n",
    },
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate(root: Path) -> list[Path]:
    created: list[Path] = []
    for spec in FILES:
        # Use only the filename so everything lands in a single messy flat folder
        dest = root / Path(spec["rel"]).name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if "bytes" in spec:
            dest.write_bytes(spec["bytes"])
        else:
            dest.write_text(spec["text"], encoding="utf-8")
        created.append(dest)
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output",
        nargs="?",
        default=str(Path(__file__).parent / "fixtures"),
        help="Directory to create fixtures in (default: tests/fixtures/)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove and recreate the output directory if it exists",
    )
    args = parser.parse_args()

    root = Path(args.output)
    if args.clean and root.exists():
        import shutil
        shutil.rmtree(root)
        print(f"Cleaned {root}")

    root.mkdir(parents=True, exist_ok=True)
    created = generate(root)

    print(f"Created {len(created)} files in {root.resolve()}")
    for p in sorted(created):
        size = p.stat().st_size
        rel  = str(p.relative_to(root))
        print(f"  {rel:<55}  {size:>7,} bytes")


if __name__ == "__main__":
    main()
