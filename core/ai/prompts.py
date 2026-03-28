"""Jinja2 prompt templates and AI response parsing."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from jinja2 import Environment, BaseLoader

# ---------------------------------------------------------------------------
# Prompt 1 — content summarizer
# ---------------------------------------------------------------------------

_SUMMARY_TEMPLATE_SRC = """\
You are a file content analyzer. Read the file below and write a concise 1-3 sentence plain-English description of what this file is about. Focus on the subject matter, purpose, and any notable details. Do NOT return JSON — just plain text.

File metadata: name={{ name }}, extension={{ ext }}, size={{ size }} bytes
{% if content_type == 'metadata_only' %}
Content: [binary file – metadata only]
{% else %}
Content:
{{ content }}
{% endif %}
"""

# ---------------------------------------------------------------------------
# Prompt 2 — rename checker
# ---------------------------------------------------------------------------

_RENAME_TEMPLATE_SRC = """\
You are a file naming expert. Review whether the current filename accurately reflects the file's content.

Rules:
- Keep the original file extension unchanged.
- Use lowercase_underscores for any new name you suggest.
- The suggested filename (including extension) must not exceed 40 characters. Abbreviate or shorten as needed.
- If the original filename contains words in a specific language (e.g. Portuguese, Spanish, French), keep the new name in that same language. Do NOT translate to English.
- Only suggest a rename when the current name is unclear, misleading, or too generic (e.g. "document.txt", "file1.pdf").
- If the name already describes the content well, return should_rename=false and keep filename unchanged.
- Do NOT invent facts not supported by the summary.

Output exactly one JSON object:
{"filename": "...", "should_rename": true|false, "confidence": 0.0–1.0, "reasoning": "one sentence"}

File: name={{ name }}, extension={{ ext }}, size={{ size }} bytes
Content summary: {{ summary }}
"""

# ---------------------------------------------------------------------------
# Prompt 3 — organization decision maker
# ---------------------------------------------------------------------------

_DECISION_TEMPLATE_SRC = """\
You are a file organization assistant. Using the information below, return **only** valid JSON — no explanation, no markdown.

Rules:
- Use the filename exactly as provided in the file metadata. Do NOT modify it in any way.
- Do not invent facts.
- Be consistent across similar files.
- Choose category from: Finance, Work, Personal, Media, Code, Other.
- The "path" field MUST be a SHORT RELATIVE folder path. It must:
    • Start with exactly one of the six category names listed below — nothing else.
    • Never be an absolute path (never start with "/" or a drive letter).
    • Never copy verbatim folder names from the folder tree unless they already match a category name.
    • End with "/".
    • Not start with ".".
    • Have at most TWO levels: `Category/` or `Category/subfolder/`. Never propose a path with more than one subfolder level.
  IMPORTANT: Only propose a two-level path (`Category/subfolder/`) when the subfolder already exists in the folder tree shown below. If the Category folder itself does not exist yet, use only `Category/` — do not add a subfolder.
  Add a subfolder only when it clearly adds meaningful grouping AND it already exists.
- The folder tree shows the existing layout of the scanned directory. Use it ONLY to reuse
  existing sub-folders inside the correct category. Do NOT borrow folder names from
  unrelated parts of the tree.

Category → path root mapping (the path MUST start with one of these, and nothing else):
  Finance  → Finance/
  Work     → Work/
  Personal → Personal/
  Media    → Media/
  Code     → Code/
  Other    → Other/

Examples of CORRECT output:
  {"filename": "report_q1_2025.txt", "category": "Finance", "path": "Finance/reports/", "confidence": 0.95, "reasoning": "Quarterly financial report with revenue and expense figures."}
  {"filename": "meeting_notes_2025.md", "category": "Work", "path": "Work/meetings/", "confidence": 0.9, "reasoning": "Team meeting notes with action items."}
  {"filename": "main.py", "category": "Code", "path": "Code/", "confidence": 0.9, "reasoning": "Python entry-point script."}
  {"filename": "invoice_2025_001.pdf", "category": "Finance", "path": "Finance/invoices/", "confidence": 0.95, "reasoning": "Invoice document with payment details."}

Examples of WRONG output (never do this):
  {"path": "/home/user/Downloads/Finance/reports/"}   ← absolute path, forbidden
  {"path": "Finance/some_unrelated_tool_v1.2/"}       ← copied unrelated folder name from tree, forbidden
  {"path": "Finance/reports/invoices/2025/"}          ← more than one subfolder level, forbidden
  {"path": "Finance/reports/invoices/"}              ← more than one subfolder level, forbidden

Output exactly one JSON object:
{"filename": "...", "category": "Finance|Work|Personal|Media|Code|Other", "path": "Category/optional_subfolder/", "confidence": 0.0–1.0, "reasoning": "one sentence"}
{% if folder_role %}
--- Folder analysis ---
The primary role of this folder is: "{{ folder_role }}".{% if is_outlier %}
NOTE: This file has been identified as NOT matching the folder's primary role. It should be moved to the most appropriate category, away from this folder.{% endif %}
{% endif %}
{% if related_group %}
--- Related-files grouping ---
This file belongs to a group of closely related files. Suggested subfolder for the whole group: "{{ related_group }}".{% if related_files %}
Other files in this group: {{ related_files | join(', ') }}.{% endif %}
Place this file at the same path as its related files (keep them together).
{% endif %}
File metadata: name={{ name }}, extension={{ ext }}, size={{ size }} bytes

Content summary:
{{ summary }}

Folder tree of the directory being scanned:
{{ folder_tree }}
"""

# ---------------------------------------------------------------------------
# Prompt 4 — folder role analyzer
# ---------------------------------------------------------------------------

_FOLDER_ROLE_TEMPLATE_SRC = """\
You are a file organization assistant. Given the list of files and their summaries below, determine the PRIMARY ROLE of this folder.

Return exactly one JSON object — no explanation, no markdown:
{"role": "short description of main purpose (2-5 words)", "outlier_files": ["filename_that_does_not_fit.ext", ...]}

Rules:
- "role": what the MAJORITY of the files are about, e.g. "quarterly financial reports", "software project source code", "personal meeting notes".
- "outlier_files": filenames that clearly do NOT belong to this folder's primary role. Only flag obvious mismatches (high confidence). Leave the list empty when all files fit.
- If the files are diverse with no clear majority theme, set role to "mixed" and outlier_files to [].

Files in this folder:
{% for f in files %}  - {{ f.name }}: {{ f.summary }}
{% endfor %}
"""

# ---------------------------------------------------------------------------
# Prompt 5 — related files grouper
# ---------------------------------------------------------------------------

_RELATED_FILES_TEMPLATE_SRC = """\
You are a file organization assistant. Given the list of files and their summaries, identify groups of files that are CLOSELY RELATED to each other (same project, same event, same document series, same topic, etc.).

Return exactly one JSON array — no explanation, no markdown:
[{"subfolder": "lowercase_underscore_name", "files": ["file1.ext", "file2.ext"]}, ...]

Rules:
- Only group files with STRONG, CLEAR relationships. Do not force groupings.
- A file can only belong to ONE group.
- "subfolder" must be lowercase_underscores, 1-3 words, describing the shared topic.
- Do NOT create a group with only a single file.
- If no meaningful groups exist, return: []

Files in this folder:
{% for f in files %}  - {{ f.name }}: {{ f.summary }}
{% endfor %}"""

_jinja_env = Environment(loader=BaseLoader())
_summary_template = _jinja_env.from_string(_SUMMARY_TEMPLATE_SRC)
_rename_template = _jinja_env.from_string(_RENAME_TEMPLATE_SRC)
_decision_template = _jinja_env.from_string(_DECISION_TEMPLATE_SRC)
_folder_role_template = _jinja_env.from_string(_FOLDER_ROLE_TEMPLATE_SRC)
_related_files_template = _jinja_env.from_string(_RELATED_FILES_TEMPLATE_SRC)


def render_summary_prompt(
    name: str,
    ext: str,
    size: int,
    content: str,
    content_type: str = "text",
) -> str:
    """Render the first-pass prompt that asks the AI to summarise the file content."""
    return _summary_template.render(
        name=name,
        ext=ext,
        size=size,
        content=content,
        content_type=content_type,
    )


def render_rename_prompt(
    name: str,
    ext: str,
    size: int,
    summary: str,
) -> str:
    """Render the rename-check prompt (pass 2a): ask the AI whether the filename is appropriate."""
    return _rename_template.render(
        name=name,
        ext=ext,
        size=size,
        summary=summary,
    )


def render_decision_prompt(
    name: str,
    ext: str,
    size: int,
    summary: str,
    folder_tree: str,
    folder_role: str | None = None,
    is_outlier: bool = False,
    related_group: str | None = None,
    related_files: list[str] | None = None,
) -> str:
    """Render the organisation prompt (pass 2b): ask the AI to propose a file operation.

    Optional folder-level context (produced by the "analyzing" phase):
    - *folder_role*: the primary role/theme of the scanned folder (e.g. "quarterly financial reports").
    - *is_outlier*: True when this file was flagged as not matching the folder role.
    - *related_group*: suggested subfolder name when this file belongs to a related-file group.
    - *related_files*: other filenames in the same related group (excluding the current file).
    """
    return _decision_template.render(
        name=name,
        ext=ext,
        size=size,
        summary=summary,
        folder_tree=folder_tree,
        folder_role=folder_role or "",
        is_outlier=is_outlier,
        related_group=related_group or "",
        related_files=related_files or [],
    )


def render_folder_role_prompt(files: list[dict]) -> str:
    """Render the folder-role analysis prompt.

    *files* is a list of ``{name, summary}`` dicts representing every file in the
    scanned folder.  The AI returns the folder's primary role and a list of outlier
    filenames that don't match that role.
    """
    return _folder_role_template.render(files=files)


def render_related_files_prompt(files: list[dict]) -> str:
    """Render the related-files grouping prompt.

    *files* is a list of ``{name, summary}`` dicts.  The AI returns groups of closely
    related files with a suggested subfolder name for each group.
    """
    return _related_files_template.render(files=files)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

@dataclass
class AIRenameDecision:
    filename: str
    should_rename: bool
    confidence: float
    reasoning: str
    parse_error: str = ""


@dataclass
class AIDecision:
    filename: str
    category: str
    path: str
    confidence: float
    reasoning: str
    parse_error: str = ""


@dataclass
class FolderRole:
    role: str
    outlier_files: list[str] = field(default_factory=list)
    parse_error: str = ""


@dataclass
class RelatedGroup:
    subfolder: str
    files: list[str] = field(default_factory=list)


_VALID_CATEGORIES = {"Finance", "Work", "Personal", "Media", "Code", "Other"}


def _extract_json_block(raw: str) -> str:
    """Try to pull the first {...} block out of a raw response."""
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    return match.group(0) if match else raw


def parse_response(raw: str) -> AIDecision:
    """Parse the AI text response into an AIDecision.

    Falls back gracefully on parse failures.
    """
    text = raw.strip()

    # Try direct parse, then fallback to regex extraction
    for attempt in (text, _extract_json_block(text)):
        try:
            data = json.loads(attempt)
            break
        except (json.JSONDecodeError, ValueError):
            data = None

    if not isinstance(data, dict):
        return AIDecision(
            filename="",
            category="Other",
            path="",
            confidence=0.0,
            reasoning="",
            parse_error=f"Could not parse JSON from: {raw[:200]}",
        )

    # Normalise category
    category = data.get("category", "Other")
    if category not in _VALID_CATEGORIES:
        category = "Other"

    # Clamp confidence
    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    path = str(data.get("path", ""))
    path = _sanitize_path(path, category)

    return AIDecision(
        filename=str(data.get("filename", "")),
        category=category,
        path=path,
        confidence=confidence,
        reasoning=str(data.get("reasoning", "")),
    )


def parse_rename_response(raw: str, original_name: str) -> "AIRenameDecision":
    """Parse the rename-check response into an :class:`AIRenameDecision`.

    Falls back gracefully: if the response can't be parsed, keep the original name.
    """
    text = raw.strip()
    data: dict | None = None
    for attempt in (text, _extract_json_block(text)):
        try:
            data = json.loads(attempt)
            break
        except (json.JSONDecodeError, ValueError):
            pass

    if not isinstance(data, dict):
        return AIRenameDecision(
            filename=original_name,
            should_rename=False,
            confidence=0.0,
            reasoning="",
            parse_error=f"Could not parse JSON from: {raw[:200]}",
        )

    try:
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    should_rename = bool(data.get("should_rename", False))
    filename = str(data.get("filename", original_name)) if should_rename else original_name

    # Safety: preserve original extension if the model dropped it
    from pathlib import Path as _Path
    orig_ext = _Path(original_name).suffix.lower()
    if orig_ext and not _Path(filename).suffix:
        filename += orig_ext

    return AIRenameDecision(
        filename=filename,
        should_rename=should_rename,
        confidence=confidence,
        reasoning=str(data.get("reasoning", "")),
    )


def parse_folder_role_response(raw: str) -> "FolderRole":
    """Parse the folder-role prompt response into a :class:`FolderRole`.

    Expected JSON: ``{"role": "...", "outlier_files": ["file.ext", ...]}``
    Falls back gracefully on parse failures.
    """
    text = raw.strip()
    data: dict | None = None
    for attempt in (text, _extract_json_block(text)):
        try:
            data = json.loads(attempt)
            break
        except (json.JSONDecodeError, ValueError):
            pass

    if not isinstance(data, dict):
        return FolderRole(
            role="",
            outlier_files=[],
            parse_error=f"Could not parse JSON from: {raw[:200]}",
        )

    role = str(data.get("role", "")).strip()
    raw_outliers = data.get("outlier_files", [])
    outlier_files = [str(f) for f in raw_outliers] if isinstance(raw_outliers, list) else []

    return FolderRole(role=role, outlier_files=outlier_files)


def parse_related_files_response(raw: str) -> "list[RelatedGroup]":
    """Parse the related-files prompt response into a list of :class:`RelatedGroup`.

    Expected JSON array: ``[{"subfolder": "...", "files": ["f1.ext", ...]}, ...]``
    Returns an empty list on parse failure.
    """
    text = raw.strip()

    # Try to extract a [...] array block
    def _extract_json_array(s: str) -> str:
        match = re.search(r"\[.*\]", s, re.DOTALL)
        return match.group(0) if match else s

    data: list | None = None
    for attempt in (text, _extract_json_array(text)):
        try:
            parsed = json.loads(attempt)
            if isinstance(parsed, list):
                data = parsed
                break
        except (json.JSONDecodeError, ValueError):
            pass

    if not isinstance(data, list):
        return []

    groups: list[RelatedGroup] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subfolder = str(item.get("subfolder", "")).strip()
        raw_files = item.get("files", [])
        files = [str(f) for f in raw_files] if isinstance(raw_files, list) else []
        if subfolder and len(files) >= 2:
            groups.append(RelatedGroup(subfolder=subfolder, files=files))

    return groups


def _sanitize_path(path: str, category: str) -> str:
    """Ensure the path is a folder path, not a filename or dot-relative path.

    Falls back to ``Category/`` when the model ignores the instructions.
    """
    # Strip leading ./ or just a bare dot
    path = re.sub(r"^\./", "", path).strip()
    if path in (".", "./", ""):
        return f"{category}/"

    # Collapse consecutive slashes (e.g. "Finance//reports/")
    path = re.sub(r"/+", "/", path)

    # Strip absolute prefix — keep only from the first valid category segment onward.
    # e.g. "/home/user/Downloads/Finance/reports/" → "Finance/reports/"
    _VALID_ROOTS = {"Finance", "Work", "Personal", "Media", "Code", "Other"}
    parts = path.lstrip("/").split("/")
    for i, part in enumerate(parts):
        if part in _VALID_ROOTS:
            path = "/".join(parts[i:])
            break
    else:
        # No valid category root found anywhere — fall back
        return f"{category}/"

    # Reject paths that look like a filename (no slash separator)
    # e.g. "report_q1_2025.txt" or "drive_download.zip"
    if "/" not in path:
        return f"{category}/"

    # Ensure trailing slash
    if not path.endswith("/"):
        path += "/"

    return path
