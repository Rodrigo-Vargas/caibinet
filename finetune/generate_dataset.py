"""
Generate a JSONL fine-tuning dataset from the tests/fixtures directory.

Two modes:
  --mode manual   Use the hardcoded ground-truth labels (fast, no API needed).
  --mode llm      Call an OpenAI-compatible API (e.g. GPT-4o) to label each
                  file automatically and write the results to the JSONL file.

Usage:
  # Activate the project venv first
  source .venv/bin/activate

  # Generate from hardcoded labels
  python finetune/generate_dataset.py --mode manual --out finetune/dataset.jsonl

  # Generate using a cloud LLM as teacher (needs OPENAI_API_KEY in environment)
  python finetune/generate_dataset.py --mode llm --out finetune/dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Ensure the repo root is on the path so we can import core.ai.prompts
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.ai.prompts import render_prompt  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"

# ---------------------------------------------------------------------------
# Hardcoded ground-truth labels for the fixture files.
# Add more entries here as you add new fixture files.
# ---------------------------------------------------------------------------
GROUND_TRUTH: dict[str, dict] = {
    "report_q1_2025.txt": {
        "category": "Finance",
        "path": "Finance/reports/",
        "confidence": 0.97,
        "reasoning": "Quarterly financial report with revenue, expenses and net profit figures.",
    },
    "invoice_2025_001.pdf": {
        "category": "Finance",
        "path": "Finance/invoices/",
        "confidence": 0.97,
        "reasoning": "Invoice document identified by invoice number and year.",
    },
    "tax_return_2024.pdf": {
        "category": "Finance",
        "path": "Finance/tax/",
        "confidence": 0.97,
        "reasoning": "Annual tax return document for the year 2024.",
    },
    "sales_data_2025.csv": {
        "category": "Finance",
        "path": "Finance/sales/",
        "confidence": 0.95,
        "reasoning": "CSV with product sales figures including units and revenue columns.",
    },
    "employee_roster.csv": {
        "category": "Work",
        "path": "Work/hr/",
        "confidence": 0.95,
        "reasoning": "HR employee roster with department, salary and start date fields.",
    },
    "meeting_notes_2025-03-10.md": {
        "category": "Work",
        "path": "Work/meetings/",
        "confidence": 0.95,
        "reasoning": "Meeting notes markdown file with a date-stamped filename.",
    },
    "contract_vendor_acme.txt": {
        "category": "Work",
        "path": "Work/contracts/",
        "confidence": 0.95,
        "reasoning": "Vendor contract document referencing ACME as a third party.",
    },
    "user_manual_v3.pdf": {
        "category": "Work",
        "path": "Work/manuals/",
        "confidence": 0.90,
        "reasoning": "Versioned user manual PDF for internal or customer use.",
    },
    "resume_jane_doe.txt": {
        "category": "Personal",
        "path": "Personal/",
        "confidence": 0.97,
        "reasoning": "Personal resume document for Jane Doe.",
    },
    "main.py": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.97,
        "reasoning": "Python entry-point script for a data pipeline.",
    },
    "utils.js": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.95,
        "reasoning": "JavaScript utility module exporting a debounce helper.",
    },
    "query.sql": {
        "category": "Code",
        "path": "Code/sql/",
        "confidence": 0.95,
        "reasoning": "SQL query file containing database statements.",
    },
    "styles.css": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.92,
        "reasoning": "CSS stylesheet file for web application styling.",
    },
    "index.html": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.92,
        "reasoning": "HTML document file for a web page.",
    },
    "pyproject.toml": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.95,
        "reasoning": "Python project configuration file (PEP 517 build system).",
    },
    "Makefile": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.95,
        "reasoning": "Build automation Makefile with shell targets.",
    },
    "docker-compose.yml": {
        "category": "Code",
        "path": "Code/",
        "confidence": 0.95,
        "reasoning": "Docker Compose configuration for multi-container setup.",
    },
    "nginx.conf": {
        "category": "Code",
        "path": "Code/config/",
        "confidence": 0.90,
        "reasoning": "Nginx web server configuration file.",
    },
    "settings.ini": {
        "category": "Other",
        "path": "Other/config/",
        "confidence": 0.85,
        "reasoning": "Application settings file in INI format.",
    },
    "config.json": {
        "category": "Other",
        "path": "Other/config/",
        "confidence": 0.85,
        "reasoning": "Generic JSON configuration file.",
    },
    "notebook_results.json": {
        "category": "Work",
        "path": "Work/",
        "confidence": 0.80,
        "reasoning": "JSON file containing notebook experiment results.",
    },
    "logo_company.png": {
        "category": "Media",
        "path": "Media/images/",
        "confidence": 0.95,
        "reasoning": "Company logo image file in PNG format.",
    },
    "photo_vacation_beach.png": {
        "category": "Media",
        "path": "Media/photos/",
        "confidence": 0.97,
        "reasoning": "Personal vacation photo of a beach.",
    },
    "screenshot_dashboard.jpeg": {
        "category": "Media",
        "path": "Media/screenshots/",
        "confidence": 0.92,
        "reasoning": "Screenshot of a dashboard application.",
    },
    "avatar_profile.jpg": {
        "category": "Media",
        "path": "Media/images/",
        "confidence": 0.92,
        "reasoning": "Profile avatar image in JPEG format.",
    },
    "banner_promo.gif": {
        "category": "Media",
        "path": "Media/images/",
        "confidence": 0.90,
        "reasoning": "Promotional banner GIF used for marketing.",
    },
    "notification_sound.wav": {
        "category": "Media",
        "path": "Media/audio/",
        "confidence": 0.95,
        "reasoning": "WAV audio file for a notification sound.",
    },
    "podcast_intro.wav": {
        "category": "Media",
        "path": "Media/audio/",
        "confidence": 0.95,
        "reasoning": "Podcast intro audio clip in WAV format.",
    },
    "diagram_architecture.svg": {
        "category": "Work",
        "path": "Work/diagrams/",
        "confidence": 0.88,
        "reasoning": "Architecture diagram in SVG vector format.",
    },
    "README.md": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.80,
        "reasoning": "Project README documentation file.",
    },
    "large_text.txt": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.70,
        "reasoning": "Generic large text file with no clear category signal.",
    },
    "unicode_sample.txt": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.70,
        "reasoning": "Text file containing unicode sample content.",
    },
    "app_2025-03-20.log": {
        "category": "Other",
        "path": "Other/logs/",
        "confidence": 0.92,
        "reasoning": "Application log file with a date-stamped filename.",
    },
    "error_2025-03-21.log": {
        "category": "Other",
        "path": "Other/logs/",
        "confidence": 0.95,
        "reasoning": "Error log file with timestamped entries.",
    },
    "project_backup.zip": {
        "category": "Other",
        "path": "Other/backups/",
        "confidence": 0.88,
        "reasoning": "ZIP archive of a project backup.",
    },
    "assets_bundle.zip": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.75,
        "reasoning": "Bundled assets archive in ZIP format.",
    },
    "random_data.bin": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.60,
        "reasoning": "Binary file with no identifiable content or category.",
    },
    "empty_file.txt": {
        "category": "Other",
        "path": "Other/",
        "confidence": 0.50,
        "reasoning": "Empty text file with no content to classify.",
    },
}

# ---------------------------------------------------------------------------
# Text extraction: read up to 512 bytes from text files
# ---------------------------------------------------------------------------
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".py", ".js", ".ts", ".html", ".css",
    ".sql", ".json", ".toml", ".ini", ".conf", ".yml", ".yaml",
    ".sh", ".log", ".xml", ".svg",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".wav", ".mp3",
    ".mp4", ".zip", ".bin", ".pdf",
}


def read_content(path: Path) -> tuple[str, str]:
    """Return (content_snippet, content_type) for a fixture file."""
    ext = path.suffix.lower()
    if ext in BINARY_EXTENSIONS:
        return "", "metadata_only"
    try:
        raw = path.read_bytes()[:1024].decode("utf-8", errors="replace")
        # Return only first 512 chars (similar to what the scanner does)
        return raw[:512], "text"
    except Exception:
        return "", "metadata_only"


# ---------------------------------------------------------------------------
# Manual mode: use hardcoded labels
# ---------------------------------------------------------------------------

def build_manual(out_path: Path, fixtures_dir: Path) -> None:
    records: list[dict] = []
    skipped: list[str] = []

    for name, label in GROUND_TRUTH.items():
        fixture_path = fixtures_dir / name
        if not fixture_path.exists():
            # Try subdirectories
            matches = list(fixtures_dir.rglob(name))
            if not matches:
                skipped.append(name)
                continue
            fixture_path = matches[0]

        content, content_type = read_content(fixture_path)
        size = fixture_path.stat().st_size
        ext = fixture_path.suffix

        prompt = render_prompt(
            name=name,
            ext=ext,
            size=size,
            content=content,
            content_type=content_type,
        )

        # The expected completion — a clean JSON object
        completion = json.dumps({
            "filename": name,
            "category": label["category"],
            "path": label["path"],
            "confidence": label["confidence"],
            "reasoning": label["reasoning"],
        })

        records.append({"prompt": prompt, "completion": completion})

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Written {len(records)} examples to {out_path}")
    if skipped:
        print(f"Skipped (file not found): {skipped}")


# ---------------------------------------------------------------------------
# LLM teacher mode: call an OpenAI-compatible API to label each file
# ---------------------------------------------------------------------------

def build_llm(out_path: Path, fixtures_dir: Path, model: str) -> None:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        print("openai package not installed. Run: pip install openai")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        print("Set OPENAI_API_KEY or LLM_API_KEY environment variable.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    records: list[dict] = []

    fixture_files = sorted(
        [p for p in fixtures_dir.rglob("*") if p.is_file()],
        key=lambda p: p.name,
    )

    for fixture_path in fixture_files:
        name = fixture_path.name
        content, content_type = read_content(fixture_path)
        size = fixture_path.stat().st_size
        ext = fixture_path.suffix

        prompt = render_prompt(
            name=name,
            ext=ext,
            size=size,
            content=content,
            content_type=content_type,
        )

        print(f"  Labeling {name} ...", end=" ", flush=True)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a file classification assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            completion = resp.choices[0].message.content.strip()
            # Validate it's proper JSON
            data = json.loads(completion)
            completion = json.dumps(data)
            records.append({"prompt": prompt, "completion": completion})
            print(f"OK ({data.get('category')})")
        except Exception as e:
            print(f"FAILED: {e}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nWritten {len(records)} examples to {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fine-tuning dataset")
    parser.add_argument(
        "--mode",
        choices=["manual", "llm"],
        default="manual",
        help="Label source: 'manual' (hardcoded) or 'llm' (calls an API)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("finetune/dataset.jsonl"),
        help="Output JSONL file path",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=FIXTURES_DIR,
        help="Path to fixtures directory",
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-4o-mini",
        help="OpenAI model to use as teacher (only for --mode llm)",
    )
    args = parser.parse_args()

    print(f"Mode: {args.mode}")
    print(f"Fixtures: {args.fixtures}")
    print(f"Output: {args.out}")
    print()

    if args.mode == "manual":
        build_manual(args.out, args.fixtures)
    else:
        build_llm(args.out, args.fixtures, args.llm_model)


if __name__ == "__main__":
    main()
