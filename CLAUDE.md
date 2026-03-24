# Adjutant — Personal AI Adjutant

## Project Overview

A CLI-first personal AI assistant that integrates with your note-taking system. Adjutant reads your notebooks, executes SOP workflows (inbox triage, daily summary, weekly report, task update), and provides conversational access to your knowledge base. Supports Web UI and Telegram bot for mobile capture.

## Key Files

- `src/adjutant/__main__.py` — CLI entry point (Click): chat, SOP commands, web, bot
- `src/adjutant/config.py` — Configuration, model definitions (TOOL_MODELS), persona/memory/token helpers
- `src/adjutant/core/dispatcher.py` — AI CLI streaming dispatcher (claude/gemini/codex)
- `src/adjutant/core/chat.py` — Chat logic: configurable persona + memory injection + session history
- `src/adjutant/core/sop.py` — SOP template loading and execution
- `src/adjutant/core/file_ops.py` — Safe file read/write with glob, size limits, diff preview
- `src/adjutant/models/session.py` — Conversation history model
- `src/adjutant/sop/` — Built-in SOP templates
- `src/adjutant/bot/handlers.py` — Platform-agnostic bot handlers (inbox capture, list items)
- `src/adjutant/bot/telegram.py` — Telegram adapter with AI routing and Web UI broadcast
- `src/adjutant/web/server.py` — FastAPI + WebSocket server, REST APIs, bot lifecycle
- `src/adjutant/web/static/` — Command Center UI (index.html, style.css, app.js)

## Tech Stack

- Python 3.12+
- Click (CLI), Pydantic (models), Rich (terminal)
- FastAPI + WebSocket (Web UI)
- python-telegram-bot (Telegram integration)
- AI CLI: claude (default), gemini, codex

## Architecture Notes

- Ported from CrossVal's dispatcher (simplified to single-AI mode)
- Persona: customizable via `~/.adjutant/persona.md`, falls back to built-in DEFAULT_PERSONA
- Memory: persistent at `~/.adjutant/memory.md`, injected into every AI prompt
- Model selection: TOOL_MODELS in config.py, persisted in config.toml
- Bot: AI-routed messages (question → AI answer, note → inbox capture, fallback on failure)
- Bot ↔ Web UI: broadcast() pushes Telegram conversations to all WebSocket clients
- Config: `~/.adjutant/config.toml`
- Sessions: `~/.adjutant/sessions/`
- User SOPs: `~/.adjutant/sop/`
- Bot token: `~/.adjutant/.bot_token` (chmod 0600) or `ADJUTANT_BOT_TOKEN` env var

## Development Conventions

- All worklog entries go in `worklog/agent/` with format `YYYY-MM-DD-HHMMSS-description.md`
- Update `worklog/README.md` index after each worklog entry
