"""Safe file operations — glob matching, size limits, diff preview."""

from __future__ import annotations

import difflib
from pathlib import Path

# Max file size to read (256 KB)
MAX_FILE_SIZE = 256 * 1024


class FileTooLargeError(Exception):
    """Raised when a file exceeds the size limit."""


class FileOutsideRootError(Exception):
    """Raised when a file path escapes the notebook root."""


def resolve_safe(path: Path, root: Path) -> Path:
    """Resolve a path and ensure it's within root."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        raise FileOutsideRootError(
            f"Path '{resolved}' is outside notebook root '{root_resolved}'"
        )
    return resolved


def read_file(path: Path, root: Path) -> str:
    """Read a file safely (within root, under size limit)."""
    safe_path = resolve_safe(path, root)

    if not safe_path.is_file():
        raise FileNotFoundError(f"File not found: {safe_path}")

    size = safe_path.stat().st_size
    if size > MAX_FILE_SIZE:
        raise FileTooLargeError(
            f"File '{safe_path.name}' is {size / 1024:.0f} KB (limit: {MAX_FILE_SIZE / 1024:.0f} KB)"
        )

    return safe_path.read_text(encoding="utf-8")


def glob_files(root: Path, patterns: list[str]) -> list[Path]:
    """Glob for files matching patterns within root."""
    results: list[Path] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                safe = resolve_safe(path, root)
                results.append(safe)
    return results


def make_diff(original: str, modified: str, filename: str = "file") -> str:
    """Generate a unified diff between original and modified content."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    )
    return "".join(diff)


def scan_notebook_structure(root: Path, paths=None) -> dict[str, Path | None]:
    """Scan notebook root for standard files/dirs.

    Returns dict mapping expected items to found paths (or None if missing).
    ``paths`` is a NotebookPaths instance (from config); uses defaults if None.
    """
    if paths is None:
        from adjutant.config import NotebookPaths
        paths = NotebookPaths()

    expected = {
        paths.inbox: root / paths.inbox,
        paths.tasks: root / paths.tasks,
        paths.daily_dir + "/": root / paths.daily_dir,
        paths.projects_dir + "/": root / paths.projects_dir,
    }
    results: dict[str, Path | None] = {}
    for label, path in expected.items():
        if label.endswith("/"):
            results[label] = path if path.is_dir() else None
        else:
            results[label] = path if path.is_file() else None
    return results


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


def save_attachment(data: bytes, root: Path, ext: str = ".png", assets_dir: str = "assets") -> str:
    """Save binary attachment to {assets_dir}/YYYY-MM-DD-HHMMSS{ext}.

    Returns the relative path from root.
    """
    from datetime import datetime as dt

    if len(data) > MAX_UPLOAD_SIZE:
        raise FileTooLargeError(
            f"Upload is {len(data) / 1024 / 1024:.1f} MB (limit: {MAX_UPLOAD_SIZE / 1024 / 1024:.0f} MB)"
        )

    now = dt.now()
    rel_dir = Path(assets_dir)
    abs_dir = resolve_safe(root / rel_dir, root)
    abs_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{now.strftime('%Y-%m-%d-%H%M%S')}{ext}"
    target = abs_dir / fname
    counter = 1
    while target.exists():
        fname = f"{now.strftime('%Y-%m-%d-%H%M%S')}-{counter}{ext}"
        target = abs_dir / fname
        counter += 1

    target.write_bytes(data)
    return str(rel_dir / fname)


def list_directory(root: Path, rel_path: str = "") -> list[dict]:
    """List files and directories under root/rel_path.

    Returns list of dicts with keys: name, type ('file'|'dir'), path (relative).
    Only shows .md files and directories (hides dotfiles, assets, etc.).
    """
    target = resolve_safe(root / rel_path, root) if rel_path else root.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"Directory not found: {target}")

    items: list[dict] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            rel = str(entry.relative_to(root.resolve()))
            if entry.is_dir():
                items.append({"name": entry.name, "type": "dir", "path": rel})
            elif entry.suffix.lower() == ".md":
                items.append({"name": entry.name, "type": "file", "path": rel})
    except PermissionError:
        pass
    return items


def get_notebook_stats(root: Path, paths=None) -> dict:
    """Gather quick stats about the notebook for the HUD.

    Returns counts plus preview lists for the top-bar popups.
    """
    from datetime import datetime as dt

    if paths is None:
        from adjutant.config import NotebookPaths
        paths = NotebookPaths()

    stats: dict = {
        "inbox_count": 0,
        "inbox_items": [],
        "task_count": 0,
        "task_items": [],
        "has_today_daily": False,
        "daily_recent": [],
        "total_notes": 0,
    }

    # Inbox items (unchecked)
    inbox = root / paths.inbox
    if inbox.is_file():
        try:
            text = inbox.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    label = stripped[5:].strip()
                    stats["inbox_items"].append(label)
            stats["inbox_count"] = len(stats["inbox_items"])
        except Exception:
            pass

    # Task count (unchecked)
    tasks = root / paths.tasks
    if tasks.is_file():
        try:
            text = tasks.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("- [ ]"):
                    label = stripped[5:].strip()
                    stats["task_items"].append(label)
            stats["task_count"] = len(stats["task_items"])
        except Exception:
            pass

    # Today's daily note — support YYYYMMDD and YYYY-MM-DD formats
    today_compact = dt.now().strftime("%Y%m%d")
    today_dashed = dt.now().strftime("%Y-%m-%d")
    daily_dir = root / paths.daily_dir
    if daily_dir.is_dir():
        try:
            daily_files = sorted(
                [f for f in daily_dir.iterdir() if f.is_file() and f.suffix == ".md"],
                key=lambda f: f.name,
                reverse=True,
            )
            stats["has_today_daily"] = any(
                f.stem.startswith(today_compact) or f.stem.startswith(today_dashed)
                for f in daily_files
            )
            # Recent 7 daily files for preview
            for f in daily_files[:7]:
                stats["daily_recent"].append({
                    "name": f.stem,
                    "path": str(f.relative_to(root.resolve())),
                })
        except Exception:
            pass

    # Total .md files
    try:
        stats["total_notes"] = sum(1 for _ in root.rglob("*.md"))
    except Exception:
        pass

    return stats


def append_to_file(path: Path, content: str, root: Path) -> None:
    """Append content to a file safely (within root).

    Uses open('a') for atomic single-line appends, avoiding
    read-modify-write race conditions with concurrent writers.
    """
    safe_path = resolve_safe(path, root)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    with open(safe_path, "a", encoding="utf-8") as f:
        f.write(content)


def write_file(path: Path, content: str, root: Path) -> None:
    """Write content to a file safely (within root)."""
    safe_path = resolve_safe(path, root)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(content, encoding="utf-8")
