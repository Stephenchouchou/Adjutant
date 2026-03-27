"""Platform-agnostic bot message handlers.

These functions handle the business logic (append to inbox, save images,
list items) without depending on any bot SDK. Platform adapters (telegram.py,
line.py) translate platform-specific events into calls to these handlers.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from adjutant.core.file_ops import (
    append_to_file,
    get_notebook_stats,
    read_file,
    save_attachment,
)


def handle_text_capture(text: str, notebook_root: Path, inbox: str = "inbox.md") -> str:
    """Append text to inbox as a checkbox item.

    Returns a confirmation message for the bot to reply with.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- [ ] {text}  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / inbox, entry, notebook_root)
    preview = text[:60] + ("..." if len(text) > 60 else "")
    return f"Captured: {preview}"


def handle_image_capture(
    data: bytes, ext: str, caption: str | None, notebook_root: Path,
    inbox: str = "inbox.md", assets_dir: str = "assets",
) -> str:
    """Save image to assets dir and add inbox entry with link.

    Returns a confirmation message.
    """
    rel_path = save_attachment(data, notebook_root, ext, assets_dir=assets_dir)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    desc = caption or "capture"
    entry = f"- [ ] ![{desc}]({rel_path})  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / inbox, entry, notebook_root)
    return f"Image saved: {rel_path}"


def handle_document_capture(
    data: bytes, filename: str, caption: str | None, notebook_root: Path,
    inbox: str = "inbox.md", assets_dir: str = "assets",
) -> str:
    """Save a document (PDF, etc.) to assets dir and add inbox entry with link.

    Returns a confirmation message.
    """
    ext = Path(filename).suffix or ".bin"
    rel_path = save_attachment(data, notebook_root, ext, assets_dir=assets_dir)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    desc = caption or filename
    entry = f"- [ ] [{desc}]({rel_path})  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / inbox, entry, notebook_root)
    return f"File saved: {rel_path}"


def handle_sticker_capture(
    data: bytes, emoji: str | None, notebook_root: Path,
    inbox: str = "inbox.md", assets_dir: str = "assets",
) -> str:
    """Save a sticker image to assets dir and add inbox entry.

    Returns a confirmation message.
    """
    rel_path = save_attachment(data, notebook_root, ".webp", assets_dir=assets_dir)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    desc = emoji or "sticker"
    entry = f"- [ ] ![{desc}]({rel_path})  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / inbox, entry, notebook_root)
    return f"Sticker saved: {rel_path}"


def handle_list_inbox(notebook_root: Path, paths=None) -> str:
    """Return formatted list of unchecked inbox items."""
    stats = get_notebook_stats(notebook_root, paths=paths)
    items = stats.get("inbox_items", [])
    if not items:
        return "Inbox is empty."

    lines = [f"*INBOX* ({len(items)} items)\n"]
    for i, item in enumerate(items[:20], 1):
        lines.append(f"{i}. {item}")
    if len(items) > 20:
        lines.append(f"\n...and {len(items) - 20} more")
    return "\n".join(lines)


def parse_reminder_time(time_str: str) -> datetime | None:
    """Parse a time string into a UTC datetime.

    Supports:
    - Relative: "5m", "1h", "30s", "2h30m"
    - Absolute today: "09:00", "14:30"
    - Absolute date+time: "2026-03-28 09:00", "03-28 14:30"

    Returns None if parsing fails. All results are UTC.
    """
    time_str = time_str.strip()
    now = datetime.now(timezone.utc)

    # Relative: "5m", "1h", "30s", "2h30m", "1h30"
    rel_match = re.fullmatch(
        r"(?:(\d+)h)?(?:(\d+)m(?:in)?)?(?:(\d+)s)?", time_str
    )
    if rel_match and any(rel_match.groups()):
        hours = int(rel_match.group(1) or 0)
        minutes = int(rel_match.group(2) or 0)
        seconds = int(rel_match.group(3) or 0)
        delta = timedelta(hours=hours, minutes=minutes, seconds=seconds)
        if delta.total_seconds() > 0:
            return now + delta

    # Absolute date+time: "2026-03-28 09:00"
    for fmt in ("%Y-%m-%d %H:%M", "%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(time_str, fmt)
            if fmt == "%m-%d %H:%M":
                parsed = parsed.replace(year=now.year)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    # Absolute time today: "09:00", "14:30"
    time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", time_str)
    if time_match:
        hour, minute = int(time_match.group(1)), int(time_match.group(2))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    return None


def handle_list_tasks(notebook_root: Path, paths=None) -> str:
    """Return formatted list of unchecked tasks."""
    stats = get_notebook_stats(notebook_root, paths=paths)
    items = stats.get("task_items", [])
    if not items:
        return "No open tasks."

    lines = [f"*TASKS* ({len(items)} open)\n"]
    for i, item in enumerate(items[:20], 1):
        lines.append(f"{i}. {item}")
    if len(items) > 20:
        lines.append(f"\n...and {len(items) - 20} more")
    return "\n".join(lines)
