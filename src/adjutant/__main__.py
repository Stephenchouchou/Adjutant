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

    scan = scan_notebook_structure(notebook_root)  # uses default paths for init
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

    dispatcher = Dispatcher(ollama_base_url=config.ollama_base_url)
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


def _collect_sop_inputs(sop) -> dict[str, str]:
    """Prompt user for any required SOP input parameters (v2)."""
    from adjutant.core.sop import resolve_inputs

    if not sop.inputs:
        return {}

    # Pre-fill defaults
    resolved = resolve_inputs(sop)

    # Prompt for missing required inputs
    for inp in sop.get_required_inputs():
        if inp.name not in resolved:
            label = inp.description or inp.name
            if inp.type == "date":
                label += " (YYYY-MM-DD)"
            value = Prompt.ask(f"  [cyan]{label}[/cyan]")
            resolved[inp.name] = value

    return resolved


def _run_sop(sop_key: str):
    """Run a SOP by key. Supports v1 (single prompt) and v2 (multi-step, inputs)."""
    from adjutant.core.sop import build_step_prompt

    config = _require_config()
    store = _get_sop_store(config)
    sop = store.get_sop(sop_key)

    if sop is None:
        console.print(f"[red]SOP not found: {sop_key}[/red]")
        sys.exit(1)

    console.print(f"[bold]{sop.icon} {sop.label}[/bold] — {sop.description}")
    if sop.is_v2 and sop.tags:
        console.print(f"[dim]Tags: {', '.join(sop.tags)}[/dim]")
    console.print()

    # Collect input parameters (v2)
    input_values = _collect_sop_inputs(sop)

    dispatcher = Dispatcher(ollama_base_url=config.ollama_base_url)
    model = config.ai_model or None

    # Multi-step execution (v2)
    if sop.is_multistep:
        previous_output = None
        for i, step in enumerate(sop.steps, 1):
            console.print(f"\n[bold]── 步驟 {i}/{len(sop.steps)}: {step.name} ──[/bold]\n")
            prompt = build_step_prompt(
                sop, step, config.notebook_root,
                input_values=input_values,
                previous_output=previous_output,
            )
            response = _run_async(
                _stream_and_collect(
                    dispatcher, prompt, config.notebook_root, config.ai_tool, model,
                )
            )
            previous_output = response

        # Final output handling uses last step's response
        if sop.output.startswith("file:"):
            _write_sop_output(sop, previous_output, config.notebook_root)
    else:
        # Single-step execution (v1 or simple v2)
        prompt = build_sop_prompt(
            sop, config.notebook_root, input_values=input_values,
        )
        response = _run_async(
            _stream_and_collect(
                dispatcher, prompt, config.notebook_root, config.ai_tool, model,
            )
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


# ── Index commands ─────────────────────────────────────────────


@cli.group()
def index():
    """Manage the notebook vector index (RAG)."""
    pass


@index.command("build")
@click.option("--full", is_flag=True, help="Full rebuild (ignore cache)")
def index_build(full: bool):
    """Build or update the notebook vector index."""
    config = _require_config()

    async def _build():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.index import build_index

        console.print("[bold]Building notebook index...[/bold]")
        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        console.print(f"  Embedding provider: {type(embedder).__name__}")

        meta = await build_index(
            config.notebook_root, embedder, incremental=not full,
        )

        console.print(f"[green]Index built:[/green]")
        console.print(f"  Files: {meta.file_count}")
        console.print(f"  Chunks: {meta.chunk_count}")
        console.print(f"  Last built: {meta.last_built}")

    _run_async(_build())


@index.command("status")
def index_status():
    """Show index status."""
    from adjutant.core.index import get_index_status

    meta = get_index_status()
    if not meta.last_built:
        console.print("[yellow]Index not built yet.[/yellow] Run [bold]adjutant index build[/bold]")
        return

    console.print("[bold]Index status:[/bold]")
    console.print(f"  Files indexed: {meta.file_count}")
    console.print(f"  Total chunks: {meta.chunk_count}")
    console.print(f"  Last built: {meta.last_built}")


@index.command("search")
@click.argument("query")
@click.option("--top-k", "-k", default=5, help="Number of results")
def index_search(query: str, top_k: int):
    """Search the notebook index."""
    config = _require_config()

    async def _search():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.retriever import retrieve

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        results = await retrieve(query, embedder, top_k=top_k)

        if not results:
            console.print("[yellow]No results found.[/yellow] Is the index built?")
            return

        for i, r in enumerate(results, 1):
            header = f"[bold cyan]{r.source}[/bold cyan]"
            if r.heading:
                header += f" > {r.heading}"
            console.print(f"\n{i}. {header} [dim](score: {r.score:.4f})[/dim]")
            # Show first 200 chars of text
            preview = r.text[:200].replace("\n", " ")
            if len(r.text) > 200:
                preview += "..."
            console.print(f"   {preview}")

    _run_async(_search())


# ── Memory commands ────────────────────────────────────────────


@cli.group()
def memory():
    """Manage the vector memory store."""
    pass


@memory.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
def memory_list(category: str | None):
    """List all stored memories."""
    config = _require_config()

    async def _list():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.memory import MemoryStore

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        store = MemoryStore(embedder)
        entries = store.list_all(category=category)

        if not entries:
            console.print("[yellow]No memories stored.[/yellow]")
            return

        table = Table(title=f"Memories ({len(entries)})")
        table.add_column("ID", style="dim", width=12)
        table.add_column("Category", style="cyan", width=12)
        table.add_column("Content")
        table.add_column("Source", style="dim", width=10)
        table.add_column("Created", style="dim", width=16)

        for e in entries:
            content = e.content[:80] + "..." if len(e.content) > 80 else e.content
            created = e.created[:16] if len(e.created) >= 16 else e.created
            table.add_row(e.id, e.category, content, e.source, created)

        console.print(table)

    _run_async(_list())


@memory.command("add")
@click.argument("content")
@click.option("--category", "-c", default="fact", help="Category: fact, preference, instruction, context")
def memory_add(content: str, category: str):
    """Add a new memory."""
    config = _require_config()

    async def _add():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.memory import MemoryStore

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        store = MemoryStore(embedder)
        entry = await store.add(content, category=category)
        console.print(f"[green]Memory added:[/green] {entry.id}")

    _run_async(_add())


@memory.command("search")
@click.argument("query")
@click.option("--top-k", "-k", default=5, help="Number of results")
def memory_search(query: str, top_k: int):
    """Search memories by semantic similarity."""
    config = _require_config()

    async def _search():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.memory import MemoryStore

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        store = MemoryStore(embedder)
        entries = await store.search(query, top_k=top_k)

        if not entries:
            console.print("[yellow]No matching memories.[/yellow]")
            return

        for i, e in enumerate(entries, 1):
            console.print(f"\n{i}. [bold cyan]{e.category}[/bold cyan] [dim]({e.id})[/dim]")
            console.print(f"   {e.content}")

    _run_async(_search())


@memory.command("forget")
@click.argument("memory_id")
def memory_forget(memory_id: str):
    """Delete a memory by ID."""
    config = _require_config()

    async def _forget():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.memory import MemoryStore

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        store = MemoryStore(embedder)
        deleted = store.forget(memory_id)
        if deleted:
            console.print(f"[green]Memory {memory_id} deleted.[/green]")
        else:
            console.print(f"[red]Memory {memory_id} not found.[/red]")

    _run_async(_forget())


@memory.command("import")
def memory_import():
    """Import memories from ~/.adjutant/memory.md into the vector store."""
    config = _require_config()

    async def _import():
        from adjutant.core.embeddings import get_embedding_provider
        from adjutant.core.memory import MemoryStore

        embedder = await get_embedding_provider(ollama_base_url=config.ollama_base_url)
        store = MemoryStore(embedder)

        console.print("[bold]Importing from memory.md...[/bold]")
        count = await store.import_from_file()
        if count:
            console.print(f"[green]Imported {count} memories.[/green]")
        else:
            console.print("[yellow]No memories to import (file empty or not found).[/yellow]")

    _run_async(_import())


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

    # Pre-load wiki context if available
    wiki_context = None
    try:
        from adjutant.core.wiki import WikiManager

        wiki_root = config.notebook_root / config.paths.wiki_dir
        wiki_mgr = WikiManager(
            wiki_root, config.notebook_root,
            Dispatcher(ollama_base_url=config.ollama_base_url),
            config.ai_tool, config.ai_model or None,
        )
        wiki_context = wiki_mgr.get_wiki_context_for_chat()
        if wiki_context:
            console.print("[dim]Wiki knowledge base loaded.[/dim]\n")
    except Exception:
        pass

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

    dispatcher = Dispatcher(ollama_base_url=config.ollama_base_url)
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
        full_prompt = build_chat_prompt(user_input, session, wiki_context=wiki_context)
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


# ── Wiki commands ─────────────────────────────────────────────


@cli.group()
def wiki():
    """Manage the LLM Wiki knowledge base."""
    pass


def _get_wiki_manager(config: AdjutantConfig) -> "WikiManager":
    """Create a WikiManager with current config."""
    from adjutant.core.wiki import WikiManager

    wiki_root = config.notebook_root / config.paths.wiki_dir
    dispatcher = Dispatcher(ollama_base_url=config.ollama_base_url)
    model = config.ai_model or None
    return WikiManager(wiki_root, config.notebook_root, dispatcher, config.ai_tool, model)


@wiki.command("init")
def wiki_init():
    """Initialize the wiki directory structure."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    if wm.wiki_exists():
        console.print("[yellow]Wiki already initialized.[/yellow]")
        console.print(f"  Location: {wm.wiki_root}")
        return

    _run_async(wm.init_wiki())
    console.print(f"[green]Wiki initialized at {wm.wiki_root}[/green]")
    console.print("  Created: _schema.md, index.md, log.md")
    console.print("  Directories: summaries/, entities/, concepts/, comparisons/")
    console.print("\nNext: [bold]adjutant wiki ingest <file>[/bold] to add your first source.")


@wiki.command("ingest")
@click.argument("file_path", type=click.Path(exists=True, path_type=Path))
def wiki_ingest(file_path: Path):
    """Ingest a source document into the wiki."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    if not wm.wiki_exists():
        console.print("[red]Wiki not initialized.[/red] Run [bold]adjutant wiki init[/bold] first.")
        return

    # Resolve path relative to notebook root
    file_path = file_path.resolve()
    console.print(f"[bold]Ingesting:[/bold] {file_path.name}")
    console.print()

    async def _ingest():
        return await wm.ingest(file_path)

    result = _run_async(_ingest())

    if result.pages_created:
        console.print(f"[green]Created {len(result.pages_created)} page(s):[/green]")
        for p in result.pages_created:
            console.print(f"  + {p}")
    if result.pages_updated:
        console.print(f"[cyan]Updated {len(result.pages_updated)} page(s):[/cyan]")
        for p in result.pages_updated:
            console.print(f"  ~ {p}")
    if result.errors:
        console.print(f"[red]Errors ({len(result.errors)}):[/red]")
        for e in result.errors:
            console.print(f"  ! {e}")
    if not result.pages_created and not result.pages_updated and not result.errors:
        console.print("[yellow]No pages were created or updated.[/yellow]")


@wiki.command("query")
@click.argument("question", nargs=-1, required=True)
def wiki_query(question: tuple[str, ...]):
    """Query the wiki knowledge base."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    q = " ".join(question)
    console.print(f"[bold]Query:[/bold] {q}\n")

    async def _query():
        return await wm.query(q)

    response = _run_async(_query())
    console.print(Markdown(response))


@wiki.command("lint")
def wiki_lint():
    """Run a health check on the wiki."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    console.print("[bold]Running wiki lint...[/bold]\n")

    async def _lint():
        return await wm.lint()

    report = _run_async(_lint())
    console.print(Markdown(report))


@wiki.command("status")
def wiki_status():
    """Show wiki status summary."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    status = wm.get_status()
    if not status.exists:
        console.print("[yellow]Wiki not initialized.[/yellow] Run [bold]adjutant wiki init[/bold]")
        return

    console.print("[bold]Wiki Status[/bold]")
    console.print(f"  Location: {wm.wiki_root}")
    console.print(f"  Total pages: {status.page_count}")
    if status.categories:
        for cat, count in sorted(status.categories.items()):
            console.print(f"    {cat}/: {count}")
    if status.last_log_entry:
        console.print(f"  Last activity: {status.last_log_entry}")


@wiki.command("pages")
def wiki_pages():
    """List all wiki pages."""
    config = _require_config()
    wm = _get_wiki_manager(config)

    if not wm.wiki_exists():
        console.print("[yellow]Wiki not initialized.[/yellow]")
        return

    pages = wm.list_pages()
    if not pages:
        console.print("[dim]No pages yet.[/dim] Run [bold]adjutant wiki ingest <file>[/bold] to add content.")
        return

    table = Table(title=f"Wiki Pages ({len(pages)})")
    table.add_column("Path", style="cyan")
    table.add_column("Category", style="dim")

    for p in pages:
        cat = p.split("/")[0] if "/" in p else "root"
        table.add_row(p, cat)

    console.print(table)


# ── web ───────────────────────────────────────────────────────


@cli.command()
@click.option("--port", "-p", default=8100, help="Port to listen on")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--no-open", is_flag=True, help="Don't auto-open browser")
@click.option("--fg", is_flag=True, help="Run in foreground (default: background daemon)")
@click.option("--stop", is_flag=True, help="Stop the running web server")
def web(port: int, host: str, no_open: bool, fg: bool, stop: bool):
    """Launch the web UI."""
    import signal
    import subprocess
    import time
    import webbrowser

    from adjutant.config import CONFIG_DIR

    pid_file = CONFIG_DIR / "web.pid"
    log_file = CONFIG_DIR / "web.log"

    if stop:
        if pid_file.is_file():
            pid = int(pid_file.read_text().strip())
            try:
                import os
                os.kill(pid, signal.SIGTERM)
                console.print(f"[green]Stopped Adjutant Web (PID {pid})[/green]")
            except ProcessLookupError:
                console.print("[dim]Server was not running.[/dim]")
            pid_file.unlink(missing_ok=True)
        else:
            console.print("[dim]No running server found.[/dim]")
        return

    # Check if already running
    if pid_file.is_file():
        import os
        old_pid = int(pid_file.read_text().strip())
        try:
            os.kill(old_pid, 0)  # check if alive
            console.print(f"[yellow]Already running (PID {old_pid}).[/yellow] Use [bold]adjutant web --stop[/bold] first.")
            return
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)

    _require_config()
    url = f"http://{host}:{port}"

    if fg:
        # Foreground mode — write PID file so --stop works, clean up on exit
        import atexit
        import logging
        import os

        import uvicorn

        from adjutant.web.server import create_app

        pid_file.write_text(str(os.getpid()))
        atexit.register(lambda: pid_file.unlink(missing_ok=True))

        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        config = _require_config()
        app = create_app(config=config, auto_shutdown=not no_open)
        console.print(f"[bold]Adjutant Web UI[/bold] — {url}")
        if not no_open:
            import threading
            def _open_browser() -> None:
                time.sleep(1)
                webbrowser.open(url)
            threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(app, host=host, port=port, ws_ping_interval=None, ws_ping_timeout=None)
        return

    # Background mode — spawn detached process (always --no-open; fg writes its own PID file)
    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            [sys.executable, "-m", "adjutant", "web", "--fg", "--no-open",
             "--port", str(port), "--host", host],
            stdout=lf,
            stderr=lf,
            start_new_session=True,
        )

    # Wait for the fg process to write its PID and bind the port
    import urllib.request
    ready = False
    for _ in range(30):
        time.sleep(0.3)
        # Check child didn't crash
        if proc.poll() is not None:
            console.print(f"[red]Server failed to start.[/red] Check {log_file}")
            return
        try:
            urllib.request.urlopen(url, timeout=1)
            ready = True
            break
        except Exception:
            pass

    if not ready:
        console.print(f"[yellow]Server slow to start.[/yellow] Check {log_file}")

    # Read PID from file (written by fg process)
    if pid_file.is_file():
        pid = pid_file.read_text().strip()
    else:
        pid = str(proc.pid)
        pid_file.write_text(pid)

    console.print(f"[bold]Adjutant Web UI[/bold] — {url}  [dim](PID {pid})[/dim]")
    console.print(f"[dim]Log: {log_file}[/dim]")
    console.print(f"Stop with: [bold]adjutant web --stop[/bold]")

    if not no_open and ready:
        webbrowser.open(url)


# ── bot ───────────────────────────────────────────────────────


@cli.command()
@click.option("--platform", "-p", default=None, help="Override platform (telegram/line)")
def bot(platform: str | None):
    """Start the chat bot daemon (Telegram / Line)."""
    import logging
    import os

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    config = _require_config()
    token = os.environ.get("ADJUTANT_BOT_TOKEN")
    if not token:
        console.print("[red]Error:[/red] ADJUTANT_BOT_TOKEN environment variable not set.")
        console.print("Set it with: export ADJUTANT_BOT_TOKEN=your_token_here")
        sys.exit(1)

    plat = platform or config.bot.platform
    if plat == "telegram":
        try:
            from adjutant.bot.telegram import AdjutantTelegramBot
        except ImportError:
            console.print("[red]Error:[/red] python-telegram-bot not installed.")
            console.print("Install with: pip install 'adjutant[bot]'")
            sys.exit(1)

        console.print("[bold]Adjutant Telegram Bot[/bold] — starting polling...")
        if config.bot.allowed_chat_ids:
            console.print(f"Authorized chat IDs: {config.bot.allowed_chat_ids}")
        else:
            console.print("[yellow]Warning:[/yellow] No allowed_chat_ids set — accepting all chats (check logs for your chat ID)")

        tg = AdjutantTelegramBot(config, token)
        asyncio.run(tg.run())
    else:
        console.print(f"[red]Unsupported platform:[/red] {plat}")
        sys.exit(1)


# ── MCP Server ────────────────────────────────────────────────


@cli.command("mcp")
def mcp_server():
    """Start the MCP (Model Context Protocol) server on stdio.

    Add to Claude Code / Cursor .mcp.json:
      {"mcpServers": {"adjutant": {"command": "adjutant", "args": ["mcp"]}}}
    """
    try:
        from adjutant.mcp.server import run_server
    except ImportError:
        console.print("[red]Error:[/red] mcp package not installed.")
        console.print("Install with: pip install 'mcp>=1.0'")
        sys.exit(1)

    _require_config()
    run_server()


if __name__ == "__main__":
    cli()
