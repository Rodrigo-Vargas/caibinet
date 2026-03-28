"""Recursive directory scanner."""
from __future__ import annotations

import fnmatch
import hashlib
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_TREE_MAX_DEPTH = 4      # how deep to recurse when building the folder tree
_TREE_MAX_DIRS = 60      # cap total dirs shown to keep the prompt short


@dataclass
class FileRecord:
    path: Path
    relative_path: str      # relative to scan root
    name: str
    extension: str          # e.g. ".pdf"
    size: int               # bytes
    mime_type: str
    sha256: str
    content_type: str = "text"  # 'text' | 'pdf' | 'metadata_only'


def _compute_sha256(path: Path, block_size: int = 65_536) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _matches_any(relative: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(
            os.path.basename(relative), pattern
        ):
            return True
    return False


def scan_directory(
    root: str | Path,
    ignore_patterns: Optional[List[str]] = None,
) -> List[FileRecord]:
    """Walk *root* recursively and return a list of :class:`FileRecord`.

    Symlinks and directories are skipped.
    """
    root = Path(root)
    ignore_patterns = ignore_patterns or []
    records: List[FileRecord] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored dirs in place so os.walk skips them
        dirnames[:] = [
            d
            for d in dirnames
            if not _matches_any(
                os.path.relpath(os.path.join(dirpath, d), root), ignore_patterns
            )
        ]

        for filename in filenames:
            abs_path = Path(dirpath) / filename
            relative = os.path.relpath(abs_path, root)

            if _matches_any(relative, ignore_patterns):
                continue

            if abs_path.is_symlink():
                continue

            try:
                size = abs_path.stat().st_size
            except OSError:
                continue

            mime_type, _ = mimetypes.guess_type(str(abs_path))
            mime_type = mime_type or "application/octet-stream"

            sha = _compute_sha256(abs_path)
            ext = abs_path.suffix.lower()

            records.append(
                FileRecord(
                    path=abs_path,
                    relative_path=relative,
                    name=filename,
                    extension=ext,
                    size=size,
                    mime_type=mime_type,
                    sha256=sha,
                )
            )

    return records


def build_folder_tree(
    root: str | Path,
    ignore_patterns: Optional[List[str]] = None,
    max_depth: int = _TREE_MAX_DEPTH,
    max_dirs: int = _TREE_MAX_DIRS,
) -> str:
    """Return a compact tree string of the *directories* under *root*.

    Only directories are included (not individual files) so the context
    stays small while still conveying the folder organisation.

    Example output::

        /home/user/docs/
        ├── Finance/
        │   └── reports/
        ├── Work/
        │   ├── meetings/
        │   └── projects/
        └── Personal/
    """
    root = Path(root)
    ignore_patterns = ignore_patterns or []
    lines: List[str] = [str(root) + "/"]
    _dir_count = [0]

    def _walk(path: Path, prefix: str, depth: int) -> None:
        if depth > max_depth or _dir_count[0] >= max_dirs:
            return
        try:
            entries = sorted(
                (e for e in path.iterdir() if e.is_dir() and not e.is_symlink()),
                key=lambda e: e.name.lower(),
            )
        except PermissionError:
            return

        # Filter ignored directories
        entries = [
            e for e in entries
            if not _matches_any(os.path.relpath(e, root), ignore_patterns)
        ]

        for idx, entry in enumerate(entries):
            if _dir_count[0] >= max_dirs:
                lines.append(f"{prefix}    … (truncated)")
                return
            connector = "└── " if idx == len(entries) - 1 else "├── "
            lines.append(f"{prefix}{connector}{entry.name}/")
            _dir_count[0] += 1
            extension = "    " if idx == len(entries) - 1 else "│   "
            _walk(entry, prefix + extension, depth + 1)

    _walk(root, "", 1)
    return "\n".join(lines)
