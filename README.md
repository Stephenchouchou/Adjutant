# ADJUTANT

Personal AI knowledge management adjutant. Inspired by StarCraft's Adjutant — receives your commands, scans your notes, produces intel summaries, and reminds you of forgotten tasks.

> **Note:** This is an opinionated personal tool, not a product. It's built around a specific workflow (capture → triage → daily summary → weekly review) and assumes you're comfortable with plain-text markdown notebooks. Fork and adapt to your own style.

## Core Philosophy

**You command, Adjutant supports.**

- **You** capture raw thoughts into `inbox.md`, write daily logs, mark task priorities.
- **Adjutant** classifies, summarizes, reminds, and connects — but never decides for you.

The system follows a military command model: the commander (you) owns all decisions; the adjutant (AI) processes intelligence and provides actionable briefings.

## Notebook Structure

Adjutant works with a plain-text, markdown-based notebook (compatible with Obsidian, Logseq, or any editor):

```
~/YourNotebook/
    inbox.md              # Capture box — everything starts here
    tasks.md              # Cross-day task tracking (Next Actions / Waiting / Someday)
    journal/daily/        # Daily notes (YYYYMMDD.md)
    projects/             # Project folders with status & context
    notes/                # Atomic notes (knowledge, ideas, references)
    assets/               # Images, attachments
```

## Daily Workflow

```
                  Capture                    Process                     Review
               ┌──────────┐             ┌──────────────┐          ┌──────────────┐
  Phone/PC ──> │ inbox.md │ ──triage──> │ tasks.md     │ ──daily──> │ Daily Report │
  Telegram     │          │             │ projects/    │          │ Carry Forward│
  Web UI       │          │             │ notes/       │          │ Insights     │
               └──────────┘             └──────────────┘          └──────────────┘
```

1. **Capture** — Jot things down without thinking. Use Telegram bot, web UI, or directly edit `inbox.md`.
2. **Triage** — Run `adjutant triage` to classify inbox items into tasks, notes, projects, or someday.
3. **Work** — Do your work. Write observations in today's daily note.
4. **Summarize** — Run `adjutant daily` to generate a structured daily report.
5. **Review** — Weekly, run `adjutant weekly` to produce a week-in-review briefing.

## Installation

```bash
# Clone & one-command install
git clone https://github.com/Stephenchouchou/Adjutant.git
cd Adjutant
./install.sh
```

The install script handles everything: Python version check, venv creation, dependency installation (including Telegram bot), and initial configuration.

**Manual install** (if you prefer):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
adjutant init
```

**Optional extras:**

```bash
# Local embedding models (for RAG/memory without Ollama)
pip install -e ".[local-embeddings]"

# Development tools
pip install -e ".[dev]"
```

Requirements: Python 3.12+, and an AI backend (`claude` CLI by default, or Ollama).

## Usage

### CLI Chat

```bash
# Interactive REPL
adjutant

# Single question
adjutant chat "inbox 裡有什麼需要處理的？"

# Chat with file context
adjutant chat --file projects/my-project.md "這個專案目前的進度？"
```

### SOP Commands

```bash
adjutant triage     # Classify inbox items
adjutant daily      # Generate daily report
adjutant tasks      # Scan task status
adjutant weekly     # Generate weekly report

# Or use the generic SOP runner
adjutant sop list
adjutant sop run inbox-triage
```

### Web UI

```bash
adjutant web                    # Opens http://127.0.0.1:8100
adjutant web --port 9000        # Custom port
```

Features:
- Command Center interface with real-time notebook stats (inbox count, tasks, daily status, RAG index)
- Command Palette (`Ctrl+K`) for all operations — SOPs, search, memory, settings, directives
- Notebook semantic search (🔍 Search Notes)
- RAG index build/rebuild from Web UI (click 🧠 INDEX or Ctrl+K → Build Index)
- Vector memory management — add, search, filter by category, delete, import from memory.md
- Directives manager — view, create, delete trigger-keyword prompt injections
- Settings panel — configure Ollama URL, notebook paths, bot settings
- File attachment (📎) — attach notebook files as chat context
- SOP v2 input parameter prompts — Web UI asks for parameters before running
- SOP multi-step execution with step progress display
- SOP file write with diff preview (shows existing file before overwrite)
- Session resume — click archived session to continue the conversation
- File browser to view markdown notes
- Image paste/drop to save screenshots into notebook
- Model selector with Ollama support

### Telegram Bot

Chat with your adjutant from your phone. Questions get AI answers; notes get captured to inbox. You can also set up the bot from the Web UI (click BOT in the top bar).

**Setup:**

1. Open Telegram, find [@BotFather](https://t.me/BotFather)
2. Send `/newbot`, follow the prompts, get your bot token
3. Set the token:
   ```bash
   export ADJUTANT_BOT_TOKEN=your_token_here
   ```
4. Start the bot:
   ```bash
   adjutant bot
   ```
5. Send a message to your bot from Telegram — the console will log your `chat_id`
6. (Optional) Restrict access by adding your chat ID to `~/.adjutant/config.toml`:
   ```toml
   [bot]
   platform = "telegram"
   allowed_chat_ids = [123456789]
   ```

**Bot Commands:**

| Command | What it does |
|---------|-------------|
| `/start` | Show help |
| `/inbox` | List unchecked inbox items |
| `/tasks` | List open tasks |
| *(any text)* | AI-routed: answers questions or captures to inbox |
| *(photo)* | Save to `assets/`, add image link to inbox |

**Tip:** Add `export ADJUTANT_BOT_TOKEN=xxx` to your `~/.zshrc` or `~/.bashrc`, then you can start the bot anytime with just `adjutant bot`.

---

## AI Backends

### Claude / Gemini / Codex (subprocess)

The default backend calls AI CLI tools as subprocesses:

```bash
adjutant init          # Select ai_tool and ai_model during setup
adjutant config        # Change later via Web UI or edit config.toml
```

Requires the corresponding CLI installed: `claude`, `gemini`, or `codex`.

### Ollama (local LLM)

Run AI completely locally via [Ollama](https://ollama.com/):

```bash
# 1. Install & start Ollama
ollama serve

# 2. Pull a model
ollama pull llama3.1
ollama pull nomic-embed-text    # For RAG/memory embedding

# 3. Configure Adjutant to use Ollama
```

Edit `~/.adjutant/config.toml`:

```toml
ai_tool = "ollama"
ai_model = "llama3.1"           # Any model you've pulled
ollama_base_url = "http://localhost:11434"   # Default, change if remote
```

Or select Ollama via Web UI model selector. Available models are auto-detected from your Ollama instance.

---

## RAG — Semantic Notebook Search

Build a vector index of your notebook for semantic search. Instead of keyword matching, Adjutant understands meaning — search for "machine learning progress" and find notes about "ML pipeline architecture" or "model training results".

### Requirements

An embedding provider (one of):
- **Ollama** with `nomic-embed-text` model (recommended): `ollama pull nomic-embed-text`
- **sentence-transformers** (local, no server): `pip install -e ".[local-embeddings]"`

### Build the Index

```bash
# Full build — scans all .md files in your notebook
adjutant index build

# Check index status
adjutant index status
```

The index is stored at `~/.adjutant/index/` and uses **incremental updates** — only files modified since the last build are re-indexed.

### Search

```bash
# Semantic search from CLI
adjutant index search "what did I write about API design?"

# With custom result count
adjutant index search "meeting notes from last week" --top-k 10
```

### Automatic RAG in Chat

Once the index is built, chat automatically retrieves relevant notes and includes them as context:

```bash
adjutant chat "summarize my notes on the deployment pipeline"
# → Adjutant finds related notes via semantic search, then answers with full context
```

### Web API

```
GET /api/search?q=query&top_k=5
```

---

## Vector Memory

Upgrade from flat-file memory to semantic vector memory. Adjutant stores facts, preferences, and instructions as embeddings and retrieves only the relevant ones for each conversation.

### Requirements

Same as RAG — needs an embedding provider (Ollama or sentence-transformers).

### Commands

```bash
# Add a memory
adjutant memory add "The ML project uses PyTorch, not TensorFlow"
adjutant memory add "Commander prefers Traditional Chinese responses" --category preference
adjutant memory add "Always include code examples in explanations" --category instruction

# Search memory
adjutant memory search "what framework does the ML project use?"

# List all memories
adjutant memory list
adjutant memory list --category preference

# Remove a memory
adjutant memory forget <memory-id>

# Import from existing memory.md
adjutant memory import
```

### Categories

| Category | Use case |
|----------|----------|
| `fact` (default) | Facts about projects, people, systems |
| `preference` | Commander's preferences and style |
| `instruction` | Standing orders for the adjutant |
| `context` | Background context and relationships |

### How It Works

- Memories are stored as vectors in the same LanceDB database as the RAG index (separate table).
- During chat, Adjutant searches for memories relevant to your current prompt and injects only those.
- **Fallback**: If vector memory is empty or unavailable, falls back to the flat `~/.adjutant/memory.md` file.

### Web API

```
GET  /api/memory/entries              # List all
POST /api/memory/entries              # Add (JSON: {"content": "...", "category": "fact"})
DELETE /api/memory/entries/{id}       # Remove
```

---

## SOP v2 Format

SOPs (Standard Operating Procedures) now support typed inputs, multi-step workflows, tool declarations, and constraints via full YAML frontmatter.

### v1 vs v2

v1 SOPs continue to work unchanged. v2 is auto-detected by `version: "2"` in the frontmatter.

### Writing a v2 SOP

Create a `.md` file in `~/.adjutant/sop/`:

```markdown
---
key: my-review
version: "2"
label: Code Review
icon: 🔍
description: Review code changes and provide feedback
author: my-name
tags: [code, review, dev]
inputs:
  - name: branch
    type: string
    default: "main"
    description: Branch to review against
  - name: focus
    type: string
    default: ""
    description: Specific area to focus on
files:
  - "projects/current.md"
output: stdout
tools: [read_file, search_notes]
constraints:
  - "Focus on correctness and security, not style"
  - "Provide specific line references"
steps:
  - name: gather
    prompt: |
      Read the project context and understand the current state.
      Branch: {branch}
      Focus: {focus}
      {file_contents}
  - name: review
    prompt: |
      Based on the context from the previous step:
      {step_context}

      Provide a structured code review.
---

{file_contents}

Review focus: {focus}
Target branch: {branch}
```

### v2 Features

**Typed Inputs** — Parameters with defaults. If a default exists, it's used automatically. If not, the CLI prompts the user:

```yaml
inputs:
  - name: date
    type: date
    default: today
    description: Date for the report
```

**Multi-step Workflows** — Chain multiple prompts where each step can reference previous step output via `{step_context}`:

```yaml
steps:
  - name: analyze
    prompt: "Analyze the data: {file_contents}"
  - name: summarize
    prompt: "Based on analysis: {step_context}\n\nSummarize findings."
    depends_on: [analyze]
```

**Tool Declarations** — Metadata declaring which tools the SOP uses (informational for MCP integration):

```yaml
tools: [read_file, search_notes, add_memory]
```

**Constraints** — Rules appended to every step prompt:

```yaml
constraints:
  - "Keep responses under 500 words"
  - "Use bullet points, not paragraphs"
```

**Search-based File Inclusion** — Use `search:` prefix in `files:` to pull in semantically relevant content instead of specific files:

```yaml
files:
  - "tasks.md"
  - search: "ML pipeline architecture"
```

---

## MCP Server

Expose Adjutant's capabilities to AI coding tools (Claude Code, Cursor, Windsurf, etc.) via the [Model Context Protocol](https://modelcontextprotocol.io/).

### Setup for Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "adjutant": {
      "command": "adjutant",
      "args": ["mcp"]
    }
  }
}
```

Or if using the script entry point:

```json
{
  "mcpServers": {
    "adjutant": {
      "command": "adjutant-mcp"
    }
  }
}
```

### Setup for Cursor

Add to Cursor's MCP settings (Settings → MCP Servers):

```json
{
  "adjutant": {
    "command": "adjutant",
    "args": ["mcp"],
    "transport": "stdio"
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `read_note(path)` | Read a notebook file by relative path |
| `list_notes(path?)` | List files/directories under notebook root |
| `capture_inbox(text)` | Append a new item to inbox |
| `get_stats()` | Notebook statistics (inbox count, tasks, etc.) |
| `search_notes(query, top_k?)` | Semantic search across notebook (requires index) |
| `search_memory(query, top_k?)` | Search the adjutant's memory store |
| `add_memory(content, category?)` | Add a memory to persistent store |
| `list_sops()` | List available SOP templates |
| `run_sop(sop_key)` | Build and return a SOP prompt for execution |

### MCP Resources

| URI | Description |
|-----|-------------|
| `notebook://{path}` | Read any notebook file as a resource |
| `config://current` | Current Adjutant configuration |

### MCP Prompts

| Prompt | Description |
|--------|-------------|
| `inbox_triage` | Run inbox triage SOP |
| `daily_summary` | Generate daily summary |
| `weekly_report` | Generate weekly report |
| `task_update` | Scan tasks for stale/blocked items |

### Usage Example

Once configured, you can use Adjutant tools directly in Claude Code:

```
> Search my notes for anything about the API redesign
  → (Claude Code calls search_notes("API redesign"))

> Add to my inbox: review PR #42 before Thursday
  → (Claude Code calls capture_inbox("review PR #42 before Thursday"))

> What SOPs do I have available?
  → (Claude Code calls list_sops())
```

### Graceful Degradation

MCP tools that depend on RAG or memory (like `search_notes` and `search_memory`) return helpful error messages if the index hasn't been built yet, rather than crashing. Basic tools (`read_note`, `list_notes`, `capture_inbox`, etc.) always work.

---

## Persona & Directives

### Persona

Customize the adjutant's personality and behavior by editing `~/.adjutant/prompts/persona.md` (or `~/.adjutant/persona.md` for legacy support). Edit via Web UI (Command Palette → Persona) or directly.

The default persona is a StarCraft-inspired military adjutant using Traditional Chinese.

### Directives

Directives are trigger-based prompt injections. When a keyword appears in the user's message, the corresponding directive is appended to the AI prompt.

**Built-in directives:**

| Trigger | Effect |
|---------|--------|
| `服從指令` | Switches to unconditional command execution mode |

**Creating custom directives:**

Create a `.md` file in `~/.adjutant/prompts/directives/`:

```markdown
---
trigger: 我的關鍵字
---

This text is injected into the AI prompt whenever the user's message
contains "我的關鍵字".
```

The directive file uses YAML frontmatter with a `trigger:` field. The body (after the second `---`) is the prompt text that gets injected.

**Resolution order:** User directives (`~/.adjutant/prompts/directives/`) override built-in directives with the same filename.

### Memory

Persistent memory shared across all sessions. Two modes:

- **Vector memory** (recommended): `adjutant memory add/search/list` — semantic retrieval, only relevant memories injected per prompt
- **Flat file** (fallback): `~/.adjutant/memory.md` — entire file injected into every prompt

---

## Configuration

Config lives at `~/.adjutant/config.toml`:

```toml
notebook_root = "/home/you/YourNotebook"
ai_tool = "claude"                  # "claude", "gemini", "codex", or "ollama"
ai_model = ""                       # Empty = use CLI default
ollama_base_url = "http://localhost:11434"   # Ollama server URL

[sop_dirs]
builtin = "/path/to/src/adjutant/sop"
user = "/home/you/.adjutant/sop"

[paths]
inbox = "inbox.md"
tasks = "tasks.md"
daily_dir = "journal/daily"
projects_dir = "projects"
assets_dir = "assets"

[bot]
platform = "telegram"
allowed_chat_ids = []
```

### Directory Layout

```
~/.adjutant/
    config.toml               # Main configuration
    persona.md                # Legacy persona location
    memory.md                 # Flat-file memory (fallback)
    sessions/                 # Conversation history
    sop/                      # User-defined SOPs
    index/                    # LanceDB vector index (RAG + memory)
    prompts/
        persona.md            # Persona override
        directives/           # Custom trigger directives
    .bot_token                # Telegram bot token (chmod 0600)
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Interfaces                                                │
│  CLI (Click)  ·  Web UI (FastAPI)  ·  Telegram  ·  MCP  │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│ Core Engine                                               │
│  Chat (persona + directives + RAG + memory)              │
│  SOP v2 (inputs, steps, constraints)                     │
│  Dispatcher (subprocess + Ollama HTTP)                   │
│  File Ops  ·  Session  ·  Prompts                        │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│ Intelligence Layer                                        │
│  Embeddings (Ollama / sentence-transformers)             │
│  RAG Index (LanceDB, markdown-aware chunking)            │
│  Vector Memory (LanceDB, semantic retrieval)             │
│  Retriever (query → relevant context)                    │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│ External                                                  │
│  AI (claude/gemini/codex CLI · Ollama HTTP)              │
│  Notebook (markdown files)                                │
│  ~/.adjutant/ (config, index, sessions, SOPs, prompts)   │
└──────────────────────────────────────────────────────────┘
```

## Tech Stack

- Python 3.12+
- Click (CLI framework)
- FastAPI + WebSocket (web UI)
- Pydantic (data models)
- Rich (terminal formatting)
- httpx (Ollama HTTP client)
- LanceDB + PyArrow (vector storage)
- sentence-transformers (optional local embeddings)
- PyYAML (SOP v2 frontmatter)
- MCP SDK (Model Context Protocol server)
- python-telegram-bot (optional, for Telegram integration)

## License

MIT
