"""Prompt loader — reads .md prompt files with user override support.

Resolution order for each prompt file:
  1. ~/.adjutant/prompts/<name>.md  (user override)
  2. <package>/prompts/<name>.md    (built-in default)

Directives:
  .md files under prompts/directives/ with YAML frontmatter ``trigger: <keyword>``.
  When the keyword appears in user input, the file body is injected into the prompt.
  User can add custom directives in ~/.adjutant/prompts/directives/.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_BUILTIN_DIR = Path(__file__).resolve().parent
_USER_DIR = Path.home() / ".adjutant" / "prompts"


# ---------------------------------------------------------------------------
# Prompt file loader
# ---------------------------------------------------------------------------

def _load_prompt(name: str) -> str:
    """Load a prompt file by name (without .md extension).

    User overrides in ~/.adjutant/prompts/ take precedence over built-in defaults.
    """
    user_file = _USER_DIR / f"{name}.md"
    if user_file.is_file():
        content = user_file.read_text(encoding="utf-8").strip()
        if content:
            return content

    builtin_file = _BUILTIN_DIR / f"{name}.md"
    if builtin_file.is_file():
        return builtin_file.read_text(encoding="utf-8").strip()

    return ""


@lru_cache(maxsize=None)
def load_default_persona() -> str:
    """Load the built-in default persona (ignoring user ~/.adjutant/persona.md)."""
    return _load_prompt("persona")


# ---------------------------------------------------------------------------
# Directives — trigger-based prompt injection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Directive:
    """A trigger keyword paired with the prompt text to inject."""

    trigger: str
    body: str
    source: Path


def _parse_directive(path: Path) -> Directive | None:
    """Parse a directive .md file with YAML-style frontmatter.

    Expected format::

        ---
        trigger: 關鍵字
        ---

        Prompt body here...
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    frontmatter = text[3:end]
    body = text[end + 3:].strip()
    if not body:
        return None

    trigger = ""
    for line in frontmatter.splitlines():
        line = line.strip()
        if line.lower().startswith("trigger:"):
            trigger = line.split(":", 1)[1].strip()
            break

    if not trigger:
        return None

    return Directive(trigger=trigger, body=body, source=path)


def _scan_directives_dir(directory: Path) -> dict[str, Directive]:
    """Scan a directory for directive .md files, keyed by stem (filename without .md)."""
    results: dict[str, Directive] = {}
    if not directory.is_dir():
        return results
    for path in sorted(directory.glob("*.md")):
        directive = _parse_directive(path)
        if directive:
            results[path.stem] = directive
    return results


def load_directives() -> list[Directive]:
    """Load all directives. User directives override built-in ones with the same filename."""
    # Built-in first, then user overrides by stem
    merged = _scan_directives_dir(_BUILTIN_DIR / "directives")
    merged.update(_scan_directives_dir(_USER_DIR / "directives"))
    return list(merged.values())


def match_directives(user_prompt: str) -> list[Directive]:
    """Return all directives whose trigger keyword appears in the user prompt."""
    return [d for d in load_directives() if d.trigger in user_prompt]
