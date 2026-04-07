# Adjutant — Personal AI Adjutant

## Project Overview

A CLI-first personal AI assistant that integrates with your note-taking system. Adjutant reads your notebooks, executes SOP workflows (inbox triage, daily summary, weekly report, task update), and provides conversational access to your knowledge base. Supports Web UI and Telegram bot for mobile capture.

## Key Files

- `src/adjutant/__main__.py` — CLI entry point (Click): chat, SOP commands, web, bot
- `src/adjutant/config.py` — Configuration, model definitions (TOOL_MODELS), persona/memory/token helpers
- `src/adjutant/core/dispatcher.py` — AI dispatcher router (delegates to backends)
- `src/adjutant/core/backends/` — AI backend implementations (subprocess, ollama)
- `src/adjutant/core/chat.py` — Chat logic: persona + memory + wiki + RAG + session history
- `src/adjutant/core/wiki.py` — LLM Wiki: persistent knowledge base (ingest, query, lint)
- `src/adjutant/core/sop.py` — SOP v1/v2 template loading (inputs, multi-step, search: queries)
- `src/adjutant/core/memory.py` — Vector memory store (LanceDB, contextual retrieval)
- `src/adjutant/core/file_ops.py` — Safe file read/write with glob, size limits, diff preview
- `src/adjutant/core/embeddings.py` — Embedding providers (Ollama, sentence-transformers)
- `src/adjutant/core/index.py` — Notebook vector index (markdown chunking, LanceDB)
- `src/adjutant/core/retriever.py` — Semantic search over the notebook index
- `src/adjutant/models/session.py` — Conversation history model
- `src/adjutant/prompts/` — Extractable prompt templates (persona, directives, wiki_schema, wiki_ingest)
- `src/adjutant/sop/` — Built-in SOP templates (v2 format)
- `src/adjutant/mcp/server.py` — MCP Server (stdio transport, tools/resources/prompts)
- `src/adjutant/bot/handlers.py` — Platform-agnostic bot handlers (inbox capture, list items)
- `src/adjutant/bot/telegram.py` — Telegram adapter with AI routing and Web UI broadcast
- `src/adjutant/web/server.py` — FastAPI + WebSocket server, REST APIs, bot lifecycle
- `src/adjutant/web/static/` — Command Center UI (index.html, style.css, app.js)

## Tech Stack

- Python 3.12+
- Click (CLI), Pydantic (models), Rich (terminal)
- FastAPI + WebSocket (Web UI)
- python-telegram-bot (Telegram integration)
- AI: claude, gemini, codex (subprocess), ollama (HTTP)
- LanceDB + pyarrow (vector index for RAG and memory)
- MCP SDK (Model Context Protocol server)
- PyYAML (SOP v2 frontmatter parsing)

## Architecture Notes

- Dispatcher routes to backends: SubprocessBackend (claude/gemini/codex) or OllamaBackend (HTTP)
- Persona: `~/.adjutant/persona.md` override, built-in at `src/adjutant/prompts/persona.md`
- Directives: trigger-keyword prompt injection via `prompts/directives/*.md`
- Memory: vector store (LanceDB) with contextual retrieval, fallback to flat `~/.adjutant/memory.md`
- RAG: LanceDB vector index at `~/.adjutant/index/`, semantic search via embeddings
- Wiki: LLM-maintained knowledge base at `notebook_root/wiki/` (Karpathy's LLM Wiki pattern)
  - Ingest: source → LLM → summaries/entities/concepts pages + index.md + log.md
  - Query: two-pass (index.md → pages → synthesized answer)
  - Lint: health check for contradictions, orphans, missing cross-references
  - Wiki context auto-injected into chat prompts when available
- SOP: v1 (simple) and v2 (typed inputs, multi-step, tools, constraints) formats
- MCP: `adjutant mcp` exposes tools/resources/prompts via stdio for Claude Code/Cursor
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
