# Adjutant — Personal AI Adjutant

## Project Overview

A CLI-first personal AI assistant that integrates with your note-taking system. Adjutant reads your notebooks, executes SOP workflows (inbox triage, daily summary, weekly report, task update), and provides conversational access to your knowledge base.

## Key Files

- `src/adjutant/__main__.py` — CLI entry point (Click)
- `src/adjutant/config.py` — Configuration management (~/.adjutant/config.toml)
- `src/adjutant/core/dispatcher.py` — AI CLI streaming dispatcher (simplified from CrossVal)
- `src/adjutant/core/chat.py` — Adjutant chat logic (persona + context + streaming)
- `src/adjutant/core/sop.py` — SOP template loading and execution
- `src/adjutant/core/file_ops.py` — Safe file read/write with glob, size limits, diff preview
- `src/adjutant/models/session.py` — Conversation history model
- `src/adjutant/sop/` — Built-in SOP templates

## Tech Stack

- Python 3.12+
- Click (CLI)
- Pydantic (data models)
- Rich (terminal formatting)
- AI CLI: claude (default)

## Development Conventions

- All worklog entries go in `worklog/agent/` with format `YYYY-MM-DD-HHMMSS-description.md`
- Update `worklog/README.md` index after each worklog entry

## Architecture Notes

- Ported from CrossVal's dispatcher (simplified to single-AI mode)
- SOP templates use markdown + YAML frontmatter (from CrossVal's persona pattern)
- Config stored in `~/.adjutant/config.toml`
- Sessions stored in `~/.adjutant/sessions/`
- User SOPs in `~/.adjutant/sop/`
