"""Content extractor — dispatches on MIME type to produce text for the AI."""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from .scanner import FileRecord
from ..config import settings

if TYPE_CHECKING:
    from ..ai.ollama import OllamaProvider

log = logging.getLogger(__name__)

_TEXT_LIMIT = 4_000        # chars fed to LLM for text files
_PDF_PAGES  = 3            # first N pages extracted from PDFs


def _configure_tesseract() -> None:
    """Point pytesseract at the bundled tesseract binary when running from a
    PyInstaller one-file bundle (sys._MEIPASS is set in that case).

    Also sets TESSDATA_PREFIX so Tesseract finds the bundled language files.
    Has no effect in development because pytesseract falls back to PATH.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is None:
        return  # dev mode — use system tesseract on PATH

    base = Path(meipass)
    tess_exe = base / "tesseract" / ("tesseract.exe" if sys.platform == "win32" else "tesseract")
    if tess_exe.exists():
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = str(tess_exe)
            log.debug("[OCR] Using bundled tesseract: %s", tess_exe)
        except ImportError:
            pass

    tessdata = base / "tessdata"
    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tessdata))
        log.debug("[OCR] TESSDATA_PREFIX set to: %s", tessdata)


# Configure once at import time so any later pytesseract call picks it up.
_configure_tesseract()


# MIME prefixes / types considered images for OCR
_IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/tiff",
    "image/bmp", "image/webp", "image/gif",
}


def extract(record: FileRecord) -> Tuple[str, str]:
    """Return ``(text_content, content_type)`` for *record*.

    *content_type* is one of ``"text"``, ``"pdf"``, ``"image_ocr"``,
    ``"image_no_ocr"``, or ``"metadata_only"``.
    """
    mime = record.mime_type or ""

    if mime.startswith("text/"):
        return _read_text(record.path), "text"

    if mime == "application/pdf":
        return _read_pdf(record.path), "pdf"

    if mime in _IMAGE_MIMES or mime.startswith("image/"):
        if settings.ocr_enabled:
            return _read_image_ocr(record.path), "image_ocr"
        return "", "image_no_ocr"

    # Everything else — use metadata only
    return "", "metadata_only"


def extract_image_vision(path: Path, vision_provider: "OllamaProvider") -> str:
    """Describe an image using a multimodal vision model.

    Returns a plain-text description suitable for use as a file content
    summary.  On failure returns an empty string so the scan can continue
    using the normal metadata-only path.
    """
    _VISION_PROMPT = (
        "Describe this image in 2-3 concise sentences. "
        "Focus on the main subject, key visual elements, and any text visible in the image. "
        "Be specific and factual."
    )
    try:
        description = vision_provider.generate_with_image(_VISION_PROMPT, path)
        return description.strip()
    except Exception as exc:
        log.warning("Vision model description failed for %s: %s", path, exc)
        return ""


def score_summary(text: str) -> float:
    """Score an AI-generated summary by information richness.

    Higher is better. Three independent signals are combined:

    1. **Unique meaningful words** — alphabetic tokens with >= 3 chars, counted
       after lowercasing and deduplication. Captures vocabulary breadth.
    2. **Specific detail bonus** — digit sequences ("2025", "$1,200", "ref #42")
       each add 1.5 points. Numbers make names more precise.
    3. **Proper-noun bonus** — distinct capitalised words (e.g. ``Acme``,
       ``March``, ``Invoice``) add 0.5 points each. Sentence-initial capitals
       appear in both summaries equally so they don't skew relative comparison.
    """
    if not text or not text.strip():
        return 0.0

    # Signal 1: unique vocabulary
    unique_words = len(set(re.findall(r"[a-zA-Z]{3,}", text.lower())))

    # Signal 2: numeric specificity
    digit_sequences = len(re.findall(r"\d+", text))

    # Signal 3: unique proper nouns (distinct capitalised words with >= 3 chars)
    # Sentence-initial capitals appear in both summaries equally, so they don't
    # skew the relative comparison.
    proper_nouns = len(set(re.findall(r"\b[A-Z][a-z]{2,}", text)))

    return float(unique_words) + digit_sequences * 1.5 + proper_nouns * 0.5


def pick_best_summary(
    ocr_summary: str,
    vision_summary: str,
    file_name: str = "",
) -> tuple[str, str, str]:
    """Compare two image summaries and return the richer one.

    Both summaries are scored with :func:`score_summary`. The one with the
    higher score is returned.

    Returns ``(chosen_summary, winner_label, reason)`` where *winner_label* is
    ``"ocr"`` or ``"vision"`` and *reason* is a human-readable explanation
    suitable for log output.
    """
    ocr_score = score_summary(ocr_summary)
    vision_score = score_summary(vision_summary)

    log.debug(
        "SUMMARY BENCHMARK  file=%s  ocr_score=%.1f  vision_score=%.1f",
        file_name, ocr_score, vision_score,
    )

    if ocr_score >= vision_score:
        reason = f"OCR score={ocr_score:.1f} >= vision score={vision_score:.1f}"
        return ocr_summary, "ocr", reason
    else:
        reason = f"vision score={vision_score:.1f} > OCR score={ocr_score:.1f}"
        return vision_summary, "vision", reason


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


def _read_image_ocr(path: Path) -> str:
    """Run Tesseract OCR on *path* and return extracted text.

    Requires the ``tesseract-ocr`` system package and the Python
    ``pytesseract`` + ``Pillow`` packages.
    """
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(path)
        # Convert palette/transparency modes so Tesseract receives clean RGB
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text: str = pytesseract.image_to_string(img)
        return text.strip()[:_TEXT_LIMIT]
    except ImportError:
        log.warning(
            "pytesseract or Pillow not installed — OCR skipped for %s. "
            "Install them with: pip install pytesseract Pillow",
            path,
        )
        return ""
    except Exception as exc:
        # pytesseract.TesseractNotFoundError (EnvironmentError subclass) lands here too
        if "tesseract" in str(exc).lower() and "not found" in str(exc).lower():
            log.warning(
                "Tesseract binary not found — OCR skipped for %s. "
                "Install it with: sudo apt install tesseract-ocr  "
                "(or brew install tesseract on macOS)",
                path,
            )
        else:
            log.warning("OCR failed for %s: %s", path, exc)
        return ""
