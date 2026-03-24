"""Platform-agnostic bot message handlers.

These functions handle the business logic (append to inbox, save images,
list items) without depending on any bot SDK. Platform adapters (telegram.py,
line.py) translate platform-specific events into calls to these handlers.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from adjutant.core.file_ops import (
    append_to_file,
    get_notebook_stats,
    read_file,
    save_attachment,
)


def handle_text_capture(text: str, notebook_root: Path) -> str:
    """Append text to inbox.md as a checkbox item.

    Returns a confirmation message for the bot to reply with.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- [ ] {text}  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / "inbox.md", entry, notebook_root)
    preview = text[:60] + ("..." if len(text) > 60 else "")
    return f"Captured: {preview}"


def handle_image_capture(
    data: bytes, ext: str, caption: str | None, notebook_root: Path
) -> str:
    """Save image to assets/ and add inbox entry with link.

    Returns a confirmation message.
    """
    rel_path = save_attachment(data, notebook_root, ext)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    desc = caption or "capture"
    entry = f"- [ ] ![{desc}]({rel_path})  <!-- captured {ts} -->\n"
    append_to_file(notebook_root / "inbox.md", entry, notebook_root)
    return f"Image saved: {rel_path}"


def handle_list_inbox(notebook_root: Path) -> str:
    """Return formatted list of unchecked inbox items."""
    stats = get_notebook_stats(notebook_root)
    items = stats.get("inbox_items", [])
    if not items:
        return "Inbox is empty."

    lines = [f"*INBOX* ({len(items)} items)\n"]
    for i, item in enumerate(items[:20], 1):
        lines.append(f"{i}. {item}")
    if len(items) > 20:
        lines.append(f"\n...and {len(items) - 20} more")
    return "\n".join(lines)


def handle_list_tasks(notebook_root: Path) -> str:
    """Return formatted list of unchecked tasks."""
    stats = get_notebook_stats(notebook_root)
    items = stats.get("task_items", [])
    if not items:
        return "No open tasks."

    lines = [f"*TASKS* ({len(items)} open)\n"]
    for i, item in enumerate(items[:20], 1):
        lines.append(f"{i}. {item}")
    if len(items) > 20:
        lines.append(f"\n...and {len(items) - 20} more")
    return "\n".join(lines)
