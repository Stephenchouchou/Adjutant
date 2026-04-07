"""Configuration management — read/write ~/.adjutant/config.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".adjutant"
CONFIG_PATH = CONFIG_DIR / "config.toml"
SESSIONS_DIR = CONFIG_DIR / "sessions"
USER_SOP_DIR = CONFIG_DIR / "sop"
BOT_TOKEN_PATH = CONFIG_DIR / ".bot_token"
PERSONA_PATH = CONFIG_DIR / "persona.md"
MEMORY_PATH = CONFIG_DIR / "memory.md"
REMINDERS_PATH = CONFIG_DIR / "reminders.json"

# CLI tools and their available models
TOOL_MODELS: dict[str, list[tuple[str, str]]] = {
    "claude": [
        ("", "(CLI default)"),
        ("claude-opus-4-6", "Opus 4.6"),
        ("claude-sonnet-4-6", "Sonnet 4.6"),
        ("claude-haiku-4-5-20251001", "Haiku 4.5"),
        ("sonnet", "Sonnet (latest)"),
        ("opus", "Opus (latest)"),
        ("haiku", "Haiku (latest)"),
    ],
    "gemini": [
        ("", "(CLI default)"),
        ("gemini-2.5-pro", "Gemini 2.5 Pro"),
        ("gemini-2.5-flash", "Gemini 2.5 Flash"),
        ("gemini-2.0-flash", "Gemini 2.0 Flash"),
    ],
    "codex": [
        ("", "(CLI default)"),
        ("o3", "o3"),
        ("o4-mini", "o4-mini"),
        ("gpt-4.1", "GPT-4.1"),
        ("gpt-4o", "GPT-4o"),
    ],
    "ollama": [
        ("", "(default)"),
        ("llama3.1", "Llama 3.1"),
        ("llama3.2", "Llama 3.2"),
        ("mistral", "Mistral"),
        ("codellama", "Code Llama"),
        ("phi3", "Phi-3"),
        ("gemma2", "Gemma 2"),
        ("qwen2.5", "Qwen 2.5"),
    ],
}


class BotConfig(BaseModel):
    """Bot integration configuration."""

    platform: str = Field(default="telegram", description="Bot platform: telegram | line")
    allowed_chat_ids: list[int] = Field(
        default_factory=list,
        description="Authorized chat IDs. Empty = log IDs for setup.",
    )


class NotebookPaths(BaseModel):
    """Configurable notebook structure paths (relative to notebook_root)."""

    inbox: str = Field(default="inbox.md", description="Inbox file for capturing items")
    tasks: str = Field(default="tasks.md", description="Task tracking file")
    daily_dir: str = Field(default="journal/daily", description="Daily notes directory")
    projects_dir: str = Field(default="projects", description="Projects directory")
    assets_dir: str = Field(default="assets", description="Attachments/images directory")
    wiki_dir: str = Field(default="wiki", description="LLM Wiki directory")


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
    paths: NotebookPaths = Field(default_factory=NotebookPaths, description="Notebook structure")
    ollama_base_url: str = Field(
        default="http://localhost:11434", description="Ollama server URL"
    )
    bot: BotConfig = Field(default_factory=BotConfig, description="Bot integration")


def load_config() -> AdjutantConfig | None:
    """Load config from ~/.adjutant/config.toml. Returns None if not found."""
    if not CONFIG_PATH.is_file():
        return None

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    notebook_root = Path(data.get("notebook_root", "")).expanduser()
    ai_tool = data.get("ai_tool", "claude")
    ai_model = data.get("ai_model", "")
    ollama_base_url = data.get("ollama_base_url", "http://localhost:11434")

    sop_dirs = data.get("sop_dirs", {})
    sop_builtin = Path(sop_dirs.get("builtin", str(AdjutantConfig.model_fields["sop_dirs_builtin"].default)))
    sop_user = Path(sop_dirs.get("user", str(USER_SOP_DIR))).expanduser()

    # Notebook paths
    paths_data = data.get("paths", {})
    notebook_paths = NotebookPaths(
        inbox=paths_data.get("inbox", "inbox.md"),
        tasks=paths_data.get("tasks", "tasks.md"),
        daily_dir=paths_data.get("daily_dir", "journal/daily"),
        projects_dir=paths_data.get("projects_dir", "projects"),
        assets_dir=paths_data.get("assets_dir", "assets"),
        wiki_dir=paths_data.get("wiki_dir", "wiki"),
    )

    # Bot config
    bot_data = data.get("bot", {})
    bot_config = BotConfig(
        platform=bot_data.get("platform", "telegram"),
        allowed_chat_ids=bot_data.get("allowed_chat_ids", []),
    )

    return AdjutantConfig(
        notebook_root=notebook_root,
        ai_tool=ai_tool,
        ai_model=ai_model,
        ollama_base_url=ollama_base_url,
        sop_dirs_builtin=sop_builtin,
        sop_dirs_user=sop_user,
        paths=notebook_paths,
        bot=bot_config,
    )


def save_config(config: AdjutantConfig) -> None:
    """Save config to ~/.adjutant/config.toml."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f'notebook_root = "{config.notebook_root}"',
        f'ai_tool = "{config.ai_tool}"',
        f'ai_model = "{config.ai_model}"',
        f'ollama_base_url = "{config.ollama_base_url}"',
        "",
        "[sop_dirs]",
        f'builtin = "{config.sop_dirs_builtin}"',
        f'user = "{config.sop_dirs_user}"',
        "",
        "[paths]",
        f'inbox = "{config.paths.inbox}"',
        f'tasks = "{config.paths.tasks}"',
        f'daily_dir = "{config.paths.daily_dir}"',
        f'projects_dir = "{config.paths.projects_dir}"',
        f'assets_dir = "{config.paths.assets_dir}"',
        f'wiki_dir = "{config.paths.wiki_dir}"',
        "",
        "[bot]",
        f'platform = "{config.bot.platform}"',
        f"allowed_chat_ids = {config.bot.allowed_chat_ids}",
        "",
    ]
    CONFIG_PATH.write_text("\n".join(lines), encoding="utf-8")


def load_bot_token() -> str | None:
    """Load bot token. Env var ADJUTANT_BOT_TOKEN takes precedence over file."""
    import os

    token = os.environ.get("ADJUTANT_BOT_TOKEN")
    if token:
        return token
    if BOT_TOKEN_PATH.is_file():
        return BOT_TOKEN_PATH.read_text(encoding="utf-8").strip()
    return None


def save_bot_token(token: str) -> None:
    """Save bot token to ~/.adjutant/.bot_token with restricted permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    BOT_TOKEN_PATH.write_text(token.strip(), encoding="utf-8")
    BOT_TOKEN_PATH.chmod(0o600)


def load_persona() -> str | None:
    """Load custom persona from ~/.adjutant/persona.md. Returns None if not found."""
    if PERSONA_PATH.is_file():
        content = PERSONA_PATH.read_text(encoding="utf-8").strip()
        if content:
            return content
    return None


def save_persona(content: str) -> None:
    """Save persona to ~/.adjutant/persona.md."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PERSONA_PATH.write_text(content, encoding="utf-8")


def load_memory() -> str | None:
    """Load memory from ~/.adjutant/memory.md. Returns None if not found."""
    if MEMORY_PATH.is_file():
        content = MEMORY_PATH.read_text(encoding="utf-8").strip()
        if content:
            return content
    return None


def save_memory(content: str) -> None:
    """Save memory to ~/.adjutant/memory.md."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(content, encoding="utf-8")
