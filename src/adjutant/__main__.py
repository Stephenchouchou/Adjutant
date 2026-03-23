"""Adjutant CLI — personal AI knowledge management assistant."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table

from adjutant.config import (
    AdjutantConfig,
    CONFIG_PATH,
    USER_SOP_DIR,
    load_config,
    save_config,
)
from adjutant.core.chat import build_chat_prompt, chat_once, chat_stream
from adjutant.core.dispatcher import Dispatcher
from adjutant.core.file_ops import read_file
from adjutant.core.sop import SOPStore, build_sop_prompt
from adjutant.models.session import Session

console = Console()


def _require_config() -> AdjutantConfig:
    """Load config or exit with helpful error."""
    config = load_config()
    if config is None:
        console.print(
            f"[red]Config not found.[/red] Run [bold]adjutant init[/bold] first.",
        )
        sys.exit(1)
    return config


def _get_sop_store(config: AdjutantConfig) -> SOPStore:
    return SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)


def _run_async(coro):
    """Run an async coroutine."""
    return asyncio.run(coro)


async def _stream_and_collect(
    dispatcher: Dispatcher,
    prompt: str,
    work_dir: Path,
    ai_tool: str = "claude",
    model: str | None = None,
) -> str:
    """Stream AI response to console and return full text."""
    parts: list[str] = []
    async for chunk in dispatcher.run(ai_tool, prompt, work_dir, model=model):
        console.print(chunk, end="", highlight=False)
        parts.append(chunk)
    console.print()  # final newline
    return "".join(parts)


# ── CLI Group ──────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Adjutant — your personal AI knowledge management assistant."""
    if ctx.invoked_subcommand is None:
        # Enter REPL mode
        _repl()


# ── init ───────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--notebook-root", "-n",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root directory of your notebook system",
)
@click.option("--ai-tool", default="claude", help="Default AI CLI tool")
@click.option("--ai-model", default="", help="Default AI model")
def init(notebook_root: Path | None, ai_tool: str, ai_model: str):
    """Initialize Adjutant configuration."""
    if notebook_root is None:
        path_str = Prompt.ask(
            "Notebook root directory",
            default=str(Path.home() / "04-ZKNote"),
        )
        notebook_root = Path(path_str).expanduser().resolve()

    if not notebook_root.is_dir():
        console.print(f"[red]Directory not found: {notebook_root}[/red]")
        sys.exit(1)

    # Scan notebook structure
    from adjutant.core.file_ops import scan_notebook_structure

    scan = scan_notebook_structure(notebook_root)
    console.print("\n[bold]Notebook structure scan:[/bold]")
    missing = []
    for label, path in scan.items():
        if path is not None:
            console.print(f"  [green]\u2713[/green] {label}")
        else:
            console.print(f"  [yellow]\u2717[/yellow] {label} [dim](not found)[/dim]")
            missing.append(label)

    if missing:
        create = Prompt.ask(
            "\nCreate missing items? [y/N]",
            default="n",
        ).lower().startswith("y")
        if create:
            for label in missing:
                target = notebook_root / label.rstrip("/")
                if label.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                    console.print(f"  [green]Created directory: {label}[/green]")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(
                        f"# {label.replace('.md', '').title()}\n\n",
                        encoding="utf-8",
                    )
                    console.print(f"  [green]Created file: {label}[/green]")

    config = AdjutantConfig(
        notebook_root=notebook_root,
        ai_tool=ai_tool,
        ai_model=ai_model,
    )
    save_config(config)
    console.print(f"\n[green]Config saved to {CONFIG_PATH}[/green]")
    console.print(f"  notebook_root: {config.notebook_root}")
    console.print(f"  ai_tool: {config.ai_tool}")


# ── chat ───────────────────────────────────────────────────────


@cli.command()
@click.argument("prompt", nargs=-1, required=True)
@click.option("--file", "-f", multiple=True, help="Additional files to include as context")
def chat(prompt: tuple[str, ...], file: tuple[str, ...]):
    """Chat with your adjutant."""
    config = _require_config()
    user_prompt = " ".join(prompt)

    # Load or create session
    session = Session(name="cli-chat")

    # Read optional file context
    file_context = None
    if file:
        sections: list[str] = []
        for f in file:
            try:
                content = read_file(
                    config.notebook_root / f,
                    config.notebook_root,
                )
                sections.append(f"### {f}\n\n{content}")
            except (FileNotFoundError, OSError) as e:
                console.print(f"[yellow]Warning: {e}[/yellow]")
        if sections:
            file_context = "\n\n---\n\n".join(sections)

    full_prompt = build_chat_prompt(user_prompt, session, file_context)

    dispatcher = Dispatcher()
    model = config.ai_model or None

    response = _run_async(
        _stream_and_collect(dispatcher, full_prompt, config.notebook_root, config.ai_tool, model)
    )

    # Save session
    session.add_message("user", user_prompt)
    session.add_message("adjutant", response)
    session.save()


# ── SOP commands ───────────────────────────────────────────────


def _write_sop_output(sop, response: str, notebook_root: Path):
    """Write SOP output to file if sop.output starts with 'file:'."""
    from datetime import datetime

    from adjutant.core.file_ops import make_diff, read_file, write_file

    rel_path = sop.output[5:]  # strip "file:"
    today = datetime.now().strftime("%Y-%m-%d")
    rel_path = rel_path.replace("{today}", today)
    target = notebook_root / rel_path

    # Show diff if file exists
    if target.is_file():
        try:
            original = read_file(target, notebook_root)
            diff = make_diff(original, response, rel_path)
            if diff:
                console.print(f"\n[bold]Diff preview for {rel_path}:[/bold]")
                console.print(diff)
        except Exception:
            pass

    confirm = Prompt.ask(
        f"\nWrite output to [cyan]{rel_path}[/cyan]? [Y/n]",
        default="y",
    ).lower().startswith("y")
    if confirm:
        write_file(target, response, notebook_root)
        console.print(f"[green]Written to {rel_path}[/green]")
    else:
        console.print("[dim]Skipped file write.[/dim]")


def _run_sop(sop_key: str):
    """Run a SOP by key."""
    config = _require_config()
    store = _get_sop_store(config)
    sop = store.get_sop(sop_key)

    if sop is None:
        console.print(f"[red]SOP not found: {sop_key}[/red]")
        sys.exit(1)

    console.print(f"[bold]{sop.icon} {sop.label}[/bold] — {sop.description}\n")

    prompt = build_sop_prompt(sop, config.notebook_root)

    dispatcher = Dispatcher()
    model = config.ai_model or None
    response = _run_async(
        _stream_and_collect(dispatcher, prompt, config.notebook_root, config.ai_tool, model)
    )

    if sop.output.startswith("file:"):
        _write_sop_output(sop, response, config.notebook_root)


@cli.command()
def triage():
    """Run inbox triage SOP."""
    _run_sop("inbox-triage")


@cli.command()
def daily():
    """Run daily summary SOP."""
    _run_sop("daily-summary")


@cli.command()
def weekly():
    """Run weekly report SOP."""
    _run_sop("weekly-report")


@cli.command()
def tasks():
    """Run task update SOP."""
    _run_sop("task-update")


# ── SOP management ─────────────────────────────────────────────


@cli.group()
def sop():
    """Manage SOP templates."""
    pass


@sop.command("list")
def sop_list():
    """List all available SOPs."""
    config = _require_config()
    store = _get_sop_store(config)
    sops = store.list_sops()

    if not sops:
        console.print("[yellow]No SOPs found.[/yellow]")
        return

    table = Table(title="Available SOPs")
    table.add_column("Key", style="cyan")
    table.add_column("Label", style="bold")
    table.add_column("Description")
    table.add_column("Files")
    table.add_column("Source", style="dim")

    for s in sops:
        table.add_row(
            s.key,
            f"{s.icon} {s.label}" if s.icon else s.label,
            s.description,
            ", ".join(s.files) or "-",
            "builtin" if s.is_builtin else "user",
        )

    console.print(table)


@sop.command("run")
@click.argument("key")
def sop_run(key: str):
    """Run a specific SOP by key."""
    _run_sop(key)


@sop.command("new")
@click.argument("key")
def sop_new(key: str):
    """Create a new custom SOP template."""
    config = _require_config()
    store = _get_sop_store(config)

    label = Prompt.ask("Label", default=key.replace("-", " ").title())
    description = Prompt.ask("Description")
    files_str = Prompt.ask("File patterns (comma-separated)", default="")
    files = [f.strip() for f in files_str.split(",") if f.strip()]

    path = store.save_sop(
        key=key,
        label=label,
        description=description,
        files=files,
        content=f"你是 Adjutant，指揮官的知識管理副官。\n\n{{file_contents}}\n\n請根據以上內容...",
    )
    console.print(f"[green]SOP template created: {path}[/green]")
    console.print(f"Edit the file to customize the prompt template.")


# ── REPL mode ──────────────────────────────────────────────────


def _repl():
    """Interactive REPL mode."""
    config = load_config()
    if config is None:
        console.print(
            "[red]Config not found.[/red] Run [bold]adjutant init[/bold] first.",
        )
        sys.exit(1)

    from datetime import datetime

    console.print("[bold]Adjutant[/bold] — Interactive Mode")
    console.print("Commands: /triage /daily /weekly /tasks /history /quit\n")

    # Check for recent sessions to resume
    session = None
    recent = Session.recent_sessions(minutes=30)
    if recent:
        console.print(f"[dim]Found {len(recent)} recent session(s):[/dim]")
        for i, s in enumerate(recent[:3]):
            age = datetime.now() - s.created_at
            mins = int(age.total_seconds() / 60)
            msg_count = len(s.messages)
            preview = ""
            if s.messages:
                last = s.messages[-1].content[:60].replace("\n", " ")
                preview = f" — {last}..."
            console.print(f"  [{i + 1}] {mins}m ago, {msg_count} messages{preview}")
        choice = Prompt.ask(
            "Resume? (1-3 or Enter for new)",
            default="",
        )
        if choice.isdigit() and 1 <= int(choice) <= len(recent[:3]):
            session = recent[int(choice) - 1]
            console.print(f"[green]Resumed session[/green]\n")

    if session is None:
        session = Session(name="repl")

    dispatcher = Dispatcher()
    model = config.ai_model or None

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()
        if cmd in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        if cmd == "/history":
            all_sessions = Session.list_sessions()[:10]
            if not all_sessions:
                console.print("[dim]No saved sessions.[/dim]")
            else:
                table = Table(title="Recent Sessions")
                table.add_column("#", style="dim")
                table.add_column("Date", style="cyan")
                table.add_column("Messages")
                table.add_column("Preview", style="dim")
                for i, s in enumerate(all_sessions, 1):
                    preview = ""
                    if s.messages:
                        preview = s.messages[-1].content[:50].replace("\n", " ")
                    table.add_row(
                        str(i),
                        s.created_at.strftime("%Y-%m-%d %H:%M"),
                        str(len(s.messages)),
                        preview,
                    )
                console.print(table)
            continue

        # SOP shortcuts
        sop_shortcuts = {
            "/triage": "inbox-triage",
            "/daily": "daily-summary",
            "/weekly": "weekly-report",
            "/tasks": "task-update",
        }

        if cmd in sop_shortcuts:
            store = _get_sop_store(config)
            sop_def = store.get_sop(sop_shortcuts[cmd])
            if sop_def:
                console.print(f"\n[bold]{sop_def.icon} {sop_def.label}[/bold]\n")
                prompt = build_sop_prompt(sop_def, config.notebook_root)
                response = _run_async(
                    _stream_and_collect(
                        dispatcher, prompt, config.notebook_root, config.ai_tool, model,
                    )
                )
                session.add_message("user", cmd)
                session.add_message("adjutant", response)
                if sop_def.output.startswith("file:"):
                    _write_sop_output(sop_def, response, config.notebook_root)
            continue

        # Regular chat
        full_prompt = build_chat_prompt(user_input, session)
        console.print()
        response = _run_async(
            _stream_and_collect(
                dispatcher, full_prompt, config.notebook_root, config.ai_tool, model,
            )
        )
        session.add_message("user", user_input)
        session.add_message("adjutant", response)

    # Save session on exit
    if session.messages:
        session.save()
        console.print(f"[dim]Session saved: {session.id}[/dim]")


# ── web ───────────────────────────────────────────────────────


@cli.command()
@click.option("--port", "-p", default=8000, help="Port to listen on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--no-open", is_flag=True, help="Don't auto-open browser")
def web(port: int, host: str, no_open: bool):
    """Launch the web UI."""
    import logging
    import threading
    import time
    import webbrowser

    import uvicorn

    from adjutant.web.server import create_app

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = _require_config()
    app = create_app(config=config, auto_shutdown=True)

    url = f"http://{host}:{port}"
    console.print(f"[bold]Adjutant Web UI[/bold] — {url}")

    if not no_open:
        def _open_browser() -> None:
            time.sleep(1)
            webbrowser.open(url)
        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(app, host=host, port=port, ws_ping_interval=None, ws_ping_timeout=None)


if __name__ == "__main__":
    cli()
