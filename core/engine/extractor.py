"""Content extractor — dispatches on MIME type to produce text for the AI."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from .scanner import FileRecord

log = logging.getLogger(__name__)

_TEXT_LIMIT = 4_000        # chars fed to LLM for text files
_PDF_PAGES  = 3            # first N pages extracted from PDFs


def extract(record: FileRecord) -> Tuple[str, str]:
    """Return ``(text_content, content_type)`` for *record*.

    *content_type* is one of ``"text"``, ``"pdf"``, or ``"metadata_only"``.
    """
    mime = record.mime_type or ""

    if mime.startswith("text/"):
        return _read_text(record.path), "text"

    if mime == "application/pdf":
        return _read_pdf(record.path), "pdf"

    # Everything else — use metadata only
    return "", "metadata_only"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    try:
        text = path.read_text(errors="replace")
        return text[:_TEXT_LIMIT]
    except OSError as exc:
        log.warning("Could not read %s: %s", path, exc)
        return ""


def _read_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages_text = []
        for page_num in range(min(_PDF_PAGES, len(doc))):
            page = doc.load_page(page_num)
            pages_text.append(page.get_text())
        doc.close()
        return "\n".join(pages_text)[:_TEXT_LIMIT]
    except Exception as exc:
        log.warning("PDF extraction failed for %s: %s", path, exc)
        return ""
