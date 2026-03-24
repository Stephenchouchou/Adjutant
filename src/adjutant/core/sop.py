"""SOP (Standard Operating Procedure) loader and executor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from adjutant.core.chat import get_persona
from adjutant.core.file_ops import glob_files, read_file


@dataclass
class SOP:
    """A parsed SOP definition."""

    key: str
    label: str
    icon: str
    description: str
    files: list[str]  # glob patterns relative to notebook_root
    output: str  # "stdout" or "file:<path>"
    prompt_template: str  # the body after frontmatter
    path: Path
    is_builtin: bool = False


def _parse_sop(path: Path, is_builtin: bool = False) -> SOP | None:
    """Parse a SOP .md file with YAML frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    key = path.stem
    label = key
    icon = ""
    description = ""
    files: list[str] = []
    output = "stdout"
    prompt_template = text

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if match:
        frontmatter = match.group(1)
        prompt_template = text[match.end():].strip()

        for line in frontmatter.split("\n"):
            line = line.strip()
            if line.startswith("key:"):
                key = line[4:].strip().strip("'\"")
            elif line.startswith("label:"):
                label = line[6:].strip().strip("'\"")
            elif line.startswith("icon:"):
                icon = line[5:].strip().strip("'\"")
            elif line.startswith("description:"):
                description = line[12:].strip().strip("'\"")
            elif line.startswith("output:"):
                output = line[7:].strip().strip("'\"")
            elif line.startswith("- ") and "files:" not in line:
                # YAML list item under files:
                files.append(line[2:].strip().strip("'\""))
            elif line.startswith("files:"):
                # Inline single file: files: "inbox.md"
                val = line[6:].strip().strip("'\"")
                if val and val != "":
                    files.append(val)

    return SOP(
        key=key,
        label=label,
        icon=icon,
        description=description,
        files=files,
        output=output,
        prompt_template=prompt_template,
        path=path,
        is_builtin=is_builtin,
    )


class SOPStore:
    """Manages SOP templates from builtin and user directories."""

    def __init__(self, builtin_dir: Path, user_dir: Path) -> None:
        self.builtin_dir = builtin_dir
        self.user_dir = user_dir

    def list_sops(self) -> list[SOP]:
        """List all available SOPs (builtin + user). User overrides builtin."""
        sops: dict[str, SOP] = {}

        if self.builtin_dir.is_dir():
            for path in sorted(self.builtin_dir.glob("*.md")):
                s = _parse_sop(path, is_builtin=True)
                if s:
                    sops[s.key] = s

        if self.user_dir.is_dir():
            for path in sorted(self.user_dir.glob("*.md")):
                s = _parse_sop(path, is_builtin=False)
                if s:
                    sops[s.key] = s

        return sorted(sops.values(), key=lambda s: s.label)

    def get_sop(self, key: str) -> SOP | None:
        """Get a SOP by key."""
        # User dir takes priority
        user_path = self.user_dir / f"{key}.md"
        if user_path.is_file():
            return _parse_sop(user_path)

        builtin_path = self.builtin_dir / f"{key}.md"
        if builtin_path.is_file():
            return _parse_sop(builtin_path, is_builtin=True)

        return None

    def save_sop(self, key: str, label: str, description: str, files: list[str], content: str) -> Path:
        """Save a SOP to the user directory."""
        self.user_dir.mkdir(parents=True, exist_ok=True)
        safe_key = re.sub(r"[^\w\-]", "-", key.lower().strip()) or "custom"
        path = self.user_dir / f"{safe_key}.md"

        files_yaml = "\n".join(f'  - "{f}"' for f in files)
        text = (
            f"---\nkey: {safe_key}\nlabel: {label}\n"
            f"description: {description}\nfiles:\n{files_yaml}\n"
            f"output: stdout\n---\n\n{content.strip()}\n"
        )
        path.write_text(text, encoding="utf-8")
        return path


def build_sop_prompt(sop: SOP, notebook_root: Path) -> str:
    """Build a complete prompt from a SOP template by reading files and substituting.

    Supports special patterns:
    - {today} → YYYY-MM-DD
    - {file_contents} → concatenated contents of matched files
    - journal/daily/*.md with date filtering for weekly reports
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Resolve file patterns
    resolved_patterns: list[str] = []
    for pattern in sop.files:
        resolved = pattern.replace("{today}", today)
        resolved_patterns.append(resolved)

    matched_files = glob_files(notebook_root, resolved_patterns)

    # For weekly report: filter to last 7 days if pattern includes daily
    if sop.key == "weekly-report":
        week_ago = datetime.now() - timedelta(days=7)
        filtered = []
        for f in matched_files:
            # Try to extract date from filename
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", f.name)
            if date_match:
                try:
                    file_date = datetime.strptime(date_match.group(1), "%Y-%m-%d")
                    if file_date >= week_ago:
                        filtered.append(f)
                except ValueError:
                    filtered.append(f)
            else:
                filtered.append(f)
        matched_files = filtered

    # Read file contents
    file_sections: list[str] = []
    for path in matched_files:
        try:
            content = read_file(path, notebook_root)
            rel_path = path.relative_to(notebook_root)
            file_sections.append(f"### {rel_path}\n\n{content}")
        except (FileNotFoundError, OSError):
            continue

    file_contents = "\n\n---\n\n".join(file_sections) if file_sections else "(no matching files found)"

    # Substitute template variables
    prompt = sop.prompt_template
    prompt = prompt.replace("{today}", today)
    prompt = prompt.replace("{file_contents}", file_contents)

    return get_persona() + "\n\n" + prompt
