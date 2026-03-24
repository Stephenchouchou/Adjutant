"""Adjutant MCP Server — exposes notebook knowledge and SOPs as MCP tools.

Usage:
    adjutant mcp              # start stdio MCP server
    Claude Code / Cursor:     add to .mcp.json as {"command": "adjutant", "args": ["mcp"]}
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from adjutant.config import AdjutantConfig, load_config

mcp = FastMCP("adjutant")

# ---------------------------------------------------------------------------
# Lazy config + helpers
# ---------------------------------------------------------------------------

_config: AdjutantConfig | None = None


def _get_config() -> AdjutantConfig:
    global _config
    if _config is None:
        _config = load_config()
        if _config is None:
            msg = "Adjutant not configured. Run 'adjutant init' first."
            raise RuntimeError(msg)
    return _config


async def _get_embedder():
    """Get an embedding provider (lazy, graceful failure)."""
    try:
        from adjutant.core.embeddings import get_embedding_provider

        config = _get_config()
        return await get_embedding_provider(ollama_base_url=config.ollama_base_url)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tools — Notebook file operations
# ---------------------------------------------------------------------------


@mcp.tool()
def read_note(path: str) -> str:
    """Read a notebook file by relative path (e.g. 'inbox.md', 'projects/ml.md')."""
    from adjutant.core.file_ops import read_file

    config = _get_config()
    return read_file(config.notebook_root / path, config.notebook_root)


@mcp.tool()
def list_notes(path: str = "") -> str:
    """List files and directories under the notebook root. Pass a relative path to list a subdirectory."""
    from adjutant.core.file_ops import list_directory

    config = _get_config()
    result = list_directory(config.notebook_root, path)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def capture_inbox(text: str) -> str:
    """Append a new item to the inbox as a checkbox entry."""
    from adjutant.core.file_ops import append_to_file

    config = _get_config()
    inbox_path = config.notebook_root / config.paths.inbox
    entry = f"- [ ] {text}\n"
    append_to_file(inbox_path, entry, config.notebook_root)
    return f"Added to inbox: {text}"


@mcp.tool()
def get_stats() -> str:
    """Get notebook statistics: inbox item count, task count, daily note count, etc."""
    from adjutant.core.file_ops import get_notebook_stats

    config = _get_config()
    stats = get_notebook_stats(config.notebook_root, paths=config.paths)
    return json.dumps(stats, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Tools — RAG search (graceful degradation if index not built)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_notes(query: str, top_k: int = 5) -> str:
    """Semantic search across all notebook files. Requires index to be built (adjutant index build)."""
    embedder = await _get_embedder()
    if embedder is None:
        return "Error: Embedding provider unavailable. Install Ollama or sentence-transformers."

    try:
        from adjutant.core.retriever import format_rag_context, retrieve

        results = await retrieve(query, embedder, top_k=top_k)
        if not results:
            return "No matching notes found. Is the index built? Run: adjutant index build"
        return format_rag_context(results)
    except Exception as e:
        return f"Search failed: {e}. Run 'adjutant index build' to create the index."


# ---------------------------------------------------------------------------
# Tools — Memory (graceful degradation)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_memory(query: str, top_k: int = 5) -> str:
    """Search the adjutant's memory store for contextually relevant memories."""
    embedder = await _get_embedder()
    if embedder is None:
        return "Error: Embedding provider unavailable."

    try:
        from adjutant.core.memory import MemoryStore, format_memory_context

        store = MemoryStore(embedder)
        if store.count() == 0:
            return "Memory store is empty. Add memories with: adjutant memory add 'fact'"

        entries = await store.search(query, top_k=top_k)
        return format_memory_context(entries) if entries else "No matching memories found."
    except Exception as e:
        return f"Memory search failed: {e}"


@mcp.tool()
async def add_memory(content: str, category: str = "fact") -> str:
    """Add a new memory to the adjutant's persistent memory store. Categories: fact, preference, instruction, context."""
    embedder = await _get_embedder()
    if embedder is None:
        return "Error: Embedding provider unavailable."

    try:
        from adjutant.core.memory import MemoryStore

        store = MemoryStore(embedder)
        entry = await store.add(content, category=category, source="mcp")
        return f"Memory stored (id: {entry.id}): {content}"
    except Exception as e:
        return f"Failed to add memory: {e}"


# ---------------------------------------------------------------------------
# Tools — SOP execution
# ---------------------------------------------------------------------------


@mcp.tool()
def list_sops() -> str:
    """List all available SOP (Standard Operating Procedure) templates."""
    from adjutant.core.sop import SOPStore

    config = _get_config()
    store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
    sops = store.list_sops()
    result = []
    for s in sops:
        entry = {
            "key": s.key,
            "label": s.label,
            "icon": s.icon,
            "description": s.description,
            "version": s.version,
            "tags": s.tags,
        }
        result.append(entry)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def run_sop(sop_key: str) -> str:
    """Build the full prompt for a SOP template. Returns the composed prompt ready for AI execution.

    This returns the SOP prompt with file contents substituted — the caller
    (Claude Code, Cursor, etc.) should send it to an AI for execution.
    """
    from adjutant.core.sop import SOPStore, build_sop_prompt

    config = _get_config()
    store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
    sop = store.get_sop(sop_key)
    if sop is None:
        return f"SOP not found: {sop_key}. Use list_sops to see available SOPs."

    return build_sop_prompt(sop, config.notebook_root)


# ---------------------------------------------------------------------------
# Resources — Notebook files and config
# ---------------------------------------------------------------------------


@mcp.resource("notebook://{path}")
def notebook_file(path: str) -> str:
    """Read a notebook file as a resource."""
    from adjutant.core.file_ops import read_file

    config = _get_config()
    return read_file(config.notebook_root / path, config.notebook_root)


@mcp.resource("config://current")
def current_config() -> str:
    """Current Adjutant configuration."""
    config = _get_config()
    return json.dumps(
        {
            "notebook_root": str(config.notebook_root),
            "ai_tool": config.ai_tool,
            "ai_model": config.ai_model,
            "ollama_base_url": config.ollama_base_url,
            "paths": {
                "inbox": config.paths.inbox,
                "tasks": config.paths.tasks,
                "daily_dir": config.paths.daily_dir,
                "projects_dir": config.paths.projects_dir,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Prompts — Dynamic SOP templates
# ---------------------------------------------------------------------------


@mcp.prompt()
def inbox_triage() -> str:
    """Run inbox triage — classify inbox items into task/note/project/someday."""
    return run_sop("inbox-triage")


@mcp.prompt()
def daily_summary() -> str:
    """Generate a structured daily summary from today's daily note."""
    return run_sop("daily-summary")


@mcp.prompt()
def weekly_report() -> str:
    """Generate a weekly report from the past 7 days of daily notes."""
    return run_sop("weekly-report")


@mcp.prompt()
def task_update() -> str:
    """Scan task list for stale/blocked items and suggest next actions."""
    return run_sop("task-update")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")
