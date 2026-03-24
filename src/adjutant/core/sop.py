"""SOP (Standard Operating Procedure) loader and executor.

Supports two formats:
- v1: Simple YAML frontmatter with line-by-line parsing (original format)
- v2: Full YAML frontmatter with typed inputs, multi-step workflows, tool declarations
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from adjutant.core.chat import get_persona
from adjutant.core.file_ops import glob_files, read_file


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SOPInput:
    """A typed input parameter for a v2 SOP."""

    name: str
    type: str = "string"  # string, date, file_pattern, search_query
    default: str = ""
    description: str = ""


@dataclass
class SOPStep:
    """A single step in a multi-step v2 SOP workflow."""

    name: str
    prompt: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class SOP:
    """A parsed SOP definition (v1 or v2)."""

    key: str
    label: str
    icon: str
    description: str
    files: list[str]  # glob patterns relative to notebook_root
    output: str  # "stdout" or "file:<path>"
    prompt_template: str  # the body after frontmatter
    path: Path
    is_builtin: bool = False
    # v2 extensions
    version: str = "1"
    author: str = ""
    tags: list[str] = field(default_factory=list)
    inputs: list[SOPInput] = field(default_factory=list)
    steps: list[SOPStep] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    @property
    def is_v2(self) -> bool:
        return self.version == "2"

    @property
    def is_multistep(self) -> bool:
        return len(self.steps) > 1

    def get_required_inputs(self) -> list[SOPInput]:
        """Return inputs that have no default and need user input."""
        return [i for i in self.inputs if not i.default]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_sop_v1(text: str, path: Path, is_builtin: bool) -> SOP:
    """Parse v1 SOP: line-by-line YAML frontmatter."""
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
        prompt_template = text[match.end() :].strip()

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
                files.append(line[2:].strip().strip("'\""))
            elif line.startswith("files:"):
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


def _parse_sop_v2(text: str, path: Path, is_builtin: bool) -> SOP:
    """Parse v2 SOP: full YAML frontmatter via pyyaml."""
    import yaml

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        # Shouldn't happen — caller already detected v2 from frontmatter
        return _parse_sop_v1(text, path, is_builtin)

    fm = yaml.safe_load(match.group(1)) or {}
    prompt_template = text[match.end() :].strip()

    # Parse inputs
    inputs = []
    for inp in fm.get("inputs", []) or []:
        if isinstance(inp, dict):
            inputs.append(
                SOPInput(
                    name=inp.get("name", ""),
                    type=inp.get("type", "string"),
                    default=str(inp.get("default", "")),
                    description=inp.get("description", ""),
                )
            )

    # Parse steps
    steps = []
    for step in fm.get("steps", []) or []:
        if isinstance(step, dict):
            steps.append(
                SOPStep(
                    name=step.get("name", ""),
                    prompt=step.get("prompt", ""),
                    depends_on=step.get("depends_on", []) or [],
                )
            )

    # Parse files — can be a list or a single string
    files_raw = fm.get("files", [])
    if isinstance(files_raw, str):
        files = [files_raw] if files_raw else []
    else:
        files = [str(f) for f in (files_raw or [])]

    # Parse tags
    tags_raw = fm.get("tags", [])
    tags = [str(t) for t in (tags_raw or [])]

    return SOP(
        key=fm.get("key", path.stem),
        label=fm.get("label", path.stem),
        icon=fm.get("icon", ""),
        description=fm.get("description", ""),
        files=files,
        output=fm.get("output", "stdout"),
        prompt_template=prompt_template,
        path=path,
        is_builtin=is_builtin,
        version="2",
        author=fm.get("author", ""),
        tags=tags,
        inputs=inputs,
        steps=steps,
        tools=fm.get("tools", []) or [],
        constraints=fm.get("constraints", []) or [],
    )


def _detect_version(text: str) -> str:
    """Detect SOP format version from frontmatter."""
    match = re.search(r'version:\s*["\']?2["\']?', text[:500])
    return "2" if match else "1"


def _parse_sop(path: Path, is_builtin: bool = False) -> SOP | None:
    """Parse a SOP .md file — auto-detects v1 or v2 format."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    version = _detect_version(text)
    if version == "2":
        return _parse_sop_v2(text, path, is_builtin)
    return _parse_sop_v1(text, path, is_builtin)


# ---------------------------------------------------------------------------
# SOP Store
# ---------------------------------------------------------------------------


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
        user_path = self.user_dir / f"{key}.md"
        if user_path.is_file():
            return _parse_sop(user_path)

        builtin_path = self.builtin_dir / f"{key}.md"
        if builtin_path.is_file():
            return _parse_sop(builtin_path, is_builtin=True)

        return None

    def save_sop(
        self, key: str, label: str, description: str, files: list[str], content: str
    ) -> Path:
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


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def resolve_inputs(sop: SOP, provided: dict[str, str] | None = None) -> dict[str, str]:
    """Resolve SOP input parameters.

    Merges provided values with defaults. Returns a dict of name → value.
    """
    provided = provided or {}
    resolved: dict[str, str] = {}
    today = datetime.now().strftime("%Y-%m-%d")

    for inp in sop.inputs:
        if inp.name in provided:
            resolved[inp.name] = provided[inp.name]
        elif inp.default:
            resolved[inp.name] = inp.default.replace("{today}", today)
        # else: missing — caller should prompt user

    return resolved


def build_sop_prompt(
    sop: SOP,
    notebook_root: Path,
    search_context: str | None = None,
    input_values: dict[str, str] | None = None,
    step_context: str | None = None,
) -> str:
    """Build a complete prompt from a SOP template by reading files and substituting.

    Supports special patterns:
    - {today} → YYYY-MM-DD
    - {file_contents} → concatenated contents of matched files
    - {search_results} → RAG search results (passed via search_context)
    - {input_name} → resolved input parameter values (v2)
    - {step_context} → output from previous step (v2 multi-step)
    - journal/daily/*.md with date filtering for weekly reports

    File entries prefixed with ``search:`` are handled by the caller via RAG
    and injected as *search_context*.
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # Separate glob patterns from search queries
    resolved_patterns: list[str] = []
    for pattern in sop.files:
        if pattern.startswith("search:"):
            continue
        resolved = pattern.replace("{today}", today)
        resolved_patterns.append(resolved)

    matched_files = glob_files(notebook_root, resolved_patterns) if resolved_patterns else []

    # For weekly report: filter to last 7 days if pattern includes daily
    if sop.key == "weekly-report":
        week_ago = datetime.now() - timedelta(days=7)
        filtered = []
        for f in matched_files:
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

    file_contents = (
        "\n\n---\n\n".join(file_sections) if file_sections else "(no matching files found)"
    )

    # Substitute template variables
    prompt = sop.prompt_template
    prompt = prompt.replace("{today}", today)
    prompt = prompt.replace("{file_contents}", file_contents)
    prompt = prompt.replace("{search_results}", search_context or "(no search results)")

    # v2: substitute input parameters
    if input_values:
        for name, value in input_values.items():
            prompt = prompt.replace(f"{{{name}}}", value)

    # v2: inject previous step output
    if step_context:
        prompt = prompt.replace("{step_context}", step_context)
        # Also inject as a section if not explicitly referenced
        if "{step_context}" not in sop.prompt_template:
            prompt = f"## 上一步驟輸出\n\n{step_context}\n\n---\n\n{prompt}"

    # v2: append constraints if present
    if sop.constraints:
        constraints_text = "\n".join(f"- {c}" for c in sop.constraints)
        prompt += f"\n\n## 限制條件\n\n{constraints_text}"

    return get_persona() + "\n\n" + prompt


def build_step_prompt(
    sop: SOP,
    step: SOPStep,
    notebook_root: Path,
    input_values: dict[str, str] | None = None,
    previous_output: str | None = None,
) -> str:
    """Build a prompt for a single step in a multi-step SOP."""
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = step.prompt
    prompt = prompt.replace("{today}", today)

    if input_values:
        for name, value in input_values.items():
            prompt = prompt.replace(f"{{{name}}}", value)

    if previous_output:
        prompt = prompt.replace("{step_context}", previous_output)

    parts = [get_persona(), f"\n## SOP: {sop.label} — 步驟: {step.name}\n\n{prompt}"]

    if previous_output and "{step_context}" not in step.prompt:
        parts.insert(1, f"\n## 上一步驟輸出\n\n{previous_output}\n")

    if sop.constraints:
        constraints_text = "\n".join(f"- {c}" for c in sop.constraints)
        parts.append(f"\n## 限制條件\n\n{constraints_text}")

    return "\n".join(parts)


def get_sop_search_queries(sop: SOP) -> list[str]:
    """Extract search: queries from a SOP's file list (for RAG retrieval by caller)."""
    queries = []
    for pattern in sop.files:
        if pattern.startswith("search:"):
            query = pattern[7:].strip().strip("'\"")
            if query:
                queries.append(query)
    return queries
