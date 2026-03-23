"""Configuration management — read/write ~/.adjutant/config.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".adjutant"
CONFIG_PATH = CONFIG_DIR / "config.toml"
SESSIONS_DIR = CONFIG_DIR / "sessions"
USER_SOP_DIR = CONFIG_DIR / "sop"


class AdjutantConfig(BaseModel):
    """Adjutant configuration."""

    notebook_root: Path = Field(description="Root directory of the user's notebook system")
    ai_tool: str = Field(default="claude", description="Default AI CLI tool")
    ai_model: str = Field(default="", description="Default AI model (empty = CLI default)")
    sop_dirs_builtin: Path = Field(
        default=Path(__file__).resolve().parent / "sop",
        description="Built-in SOP directory",
    )
    sop_dirs_user: Path = Field(
        default=USER_SOP_DIR,
        description="User SOP directory",
    )


def load_config() -> AdjutantConfig | None:
    """Load config from ~/.adjutant/config.toml. Returns None if not found."""
    if not CONFIG_PATH.is_file():
        return None

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    notebook_root = Path(data.get("notebook_root", "")).expanduser()
    ai_tool = data.get("ai_tool", "claude")
    ai_model = data.get("ai_model", "")

    sop_dirs = data.get("sop_dirs", {})
    sop_builtin = Path(sop_dirs.get("builtin", str(AdjutantConfig.model_fields["sop_dirs_builtin"].default)))
    sop_user = Path(sop_dirs.get("user", str(USER_SOP_DIR))).expanduser()

    return AdjutantConfig(
        notebook_root=notebook_root,
        ai_tool=ai_tool,
        ai_model=ai_model,
        sop_dirs_builtin=sop_builtin,
        sop_dirs_user=sop_user,
    )


def save_config(config: AdjutantConfig) -> None:
    """Save config to ~/.adjutant/config.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f'notebook_root = "{config.notebook_root}"',
        f'ai_tool = "{config.ai_tool}"',
        f'ai_model = "{config.ai_model}"',
        "",
        "[sop_dirs]",
        f'builtin = "{config.sop_dirs_builtin}"',
        f'user = "{config.sop_dirs_user}"',
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")
