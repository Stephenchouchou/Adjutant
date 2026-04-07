# ADJUTANT

Personal AI knowledge management adjutant. Inspired by StarCraft's Adjutant — receives your commands, scans your notes, produces intel summaries, and reminds you of forgotten tasks.

> **Note:** This is an opinionated personal tool, not a product. It's built around a specific workflow (capture → triage → daily summary → weekly review) and assumes you're comfortable with plain-text markdown notebooks. Fork and adapt to your own style.

**[中文說明](#中文說明)** | [English](#core-philosophy)

## Core Philosophy

**You command, Adjutant supports.**

- **You** capture raw thoughts into `inbox.md`, write daily logs, mark task priorities.
- **Adjutant** classifies, summarizes, reminds, and connects — but never decides for you.

The system follows a military command model: the commander (you) owns all decisions; the adjutant (AI) processes intelligence and provides actionable briefings.

## Features

| Feature | CLI | Web UI | Telegram | MCP |
|---------|:---:|:------:|:--------:|:---:|
| Chat with AI | ✓ | ✓ | ✓ | — |
| SOP workflows (triage, daily, weekly) | ✓ | ✓ | — | ✓ |
| Inbox capture | ✓ | ✓ | ✓ | ✓ |
| Notebook file browser & editor | — | ✓ | — | ✓ |
| Wiki knowledge base (graph/browse/edit) | ✓ | ✓ | — | ✓ |
| RAG semantic search | ✓ | ✓ | — | ✓ |
| Vector memory | ✓ | ✓ | — | ✓ |
| Reminders | — | ✓ | ✓ | — |
| Image capture | — | ✓ | ✓ | — |
| Persona & directives | ✓ | ✓ | — | — |
| Model switching (Claude/Gemini/Ollama) | ✓ | ✓ | — | — |

## Notebook Structure

Adjutant works with a plain-text, markdown-based notebook (compatible with Obsidian, Logseq, or any editor):

```
~/YourNotebook/
    inbox.md              # Capture box — everything starts here
    tasks.md              # Cross-day task tracking (Next Actions / Waiting / Someday)
    journal/daily/        # Daily notes (YYYYMMDD.md)
    projects/             # Project folders with status & context
    notes/                # Atomic notes (knowledge, ideas, references)
    wiki/                 # LLM-maintained knowledge base (auto-generated)
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

### Web UI (Command Center)

```bash
adjutant web                    # Opens http://127.0.0.1:8100
adjutant web --port 9000        # Custom port
adjutant web --daemon           # Run in background
```

Features:
- **Command Center** — HUD-style interface with real-time stats (inbox, tasks, reminders, wiki)
- **Command Palette** (`Ctrl+K`) — unified entry point for all operations
- **Wiki Knowledge Base** — force-directed graph view, page browser, inline editor
- **Notebook file browser & editor** — browse, read, and edit markdown files in-browser
- **Semantic search** — RAG-powered notebook search
- **Reminder system** — set timed reminders, delivered via Web UI and Telegram
- **Session management** — resume archived conversations
- **Image paste/drop** — screenshot capture directly into notebook
- **SOP execution** — v2 input prompts, multi-step progress, file write with diff preview
- **Memory & directives manager** — vector memory CRUD, trigger-keyword directive editor
- **Model selector** — switch between AI backends with Ollama model auto-detection
- **Responsive layout** — adapts to desktop, tablet, and mobile screens

### Wiki Knowledge Base

Adjutant maintains an LLM-powered wiki (inspired by [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)) — a persistent knowledge layer where the AI continuously distills your notes into structured pages.

```bash
adjutant wiki init                          # Initialize wiki structure
adjutant wiki ingest notes/my-note.md       # Distill a note into wiki pages
adjutant wiki query "How does X work?"      # Two-pass query over wiki
adjutant wiki lint                          # Health check (contradictions, orphans)
adjutant wiki pages                         # List all wiki pages
```

Three-layer architecture: **Raw notes** (yours, untouched) → **Wiki** (LLM-maintained summaries, entities, concepts, comparisons) → **Schema** (conventions & rules).

Web UI features interactive graph view (nodes sized by connections, hover to highlight neighbors, click to open page), page browser, and inline page editor.

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
| *(photo/sticker/document)* | Save to `assets/`, add link to inbox |

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
| `wiki_status()` | Wiki initialization and page count |
| `wiki_query(question)` | Two-pass query over wiki knowledge base |
| `wiki_ingest(source)` | Ingest a source file into wiki |
| `read_wiki_page(path)` | Read a wiki page |
| `list_wiki_pages()` | List all wiki pages |

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
wiki_dir = "wiki"

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
│  Chat (persona + directives + wiki + RAG + memory)       │
│  SOP v2 (inputs, steps, constraints)                     │
│  Wiki (ingest, query, lint, graph)                       │
│  Dispatcher (subprocess + Ollama HTTP)                   │
│  File Ops  ·  Session  ·  Prompts  ·  Reminders         │
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
│  Notebook (markdown files + wiki/)                       │
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

---

# 中文說明

## 概述

**Adjutant** 是一個以 CLI 為核心的個人 AI 副官系統，靈感來自《星海爭霸》中的副官角色。它整合你的 Markdown 筆記本，執行標準化作業流程（收件匣分類、每日摘要、週報、任務追蹤），並透過多個介面提供對話式的知識管理。

> 這是一個「有主見」的個人工具，不是通用產品。它圍繞特定工作流程建構（捕獲 → 分類 → 每日摘要 → 每週回顧），假設你習慣使用純文字 Markdown 筆記。

## 核心理念

**你下令，副官支援。**

- **你** 把零碎想法丟進 `inbox.md`、寫每日記錄、標記任務優先順序。
- **副官** 分類、摘要、提醒、串連知識 — 但從不替你做決定。

遵循軍事指揮模型：指揮官（你）擁有所有決策權；副官（AI）處理情報並提供可執行的簡報。

## 功能一覽

| 功能 | CLI | Web UI | Telegram | MCP |
|------|:---:|:------:|:--------:|:---:|
| AI 對話 | ✓ | ✓ | ✓ | — |
| SOP 工作流程（分類、日報、週報） | ✓ | ✓ | — | ✓ |
| 收件匣捕獲 | ✓ | ✓ | ✓ | ✓ |
| 筆記瀏覽與編輯 | — | ✓ | — | ✓ |
| Wiki 知識庫（圖譜/瀏覽/編輯） | ✓ | ✓ | — | ✓ |
| RAG 語意搜尋 | ✓ | ✓ | — | ✓ |
| 向量記憶 | ✓ | ✓ | — | ✓ |
| 定時提醒 | — | ✓ | ✓ | — |
| 圖片捕獲 | — | ✓ | ✓ | — |
| 人設與觸發指令 | ✓ | ✓ | — | — |
| 模型切換（Claude/Gemini/Ollama） | ✓ | ✓ | — | — |

## 筆記本結構

Adjutant 使用純文字 Markdown 筆記本（相容 Obsidian、Logseq 或任何編輯器）：

```
~/YourNotebook/
    inbox.md              # 收件匣 — 所有東西從這裡開始
    tasks.md              # 跨天任務追蹤（Next Actions / Waiting / Someday）
    journal/daily/        # 每日筆記（YYYYMMDD.md）
    projects/             # 專案資料夾
    notes/                # 原子筆記（知識、靈感、參考）
    wiki/                 # LLM 維護的知識庫（自動生成）
    assets/               # 圖片、附件
```

## 每日工作流程

1. **捕獲** — 不假思索地記下。用 Telegram bot、Web UI 或直接編輯 `inbox.md`。
2. **分類** — 執行 `adjutant triage`，把收件匣項目分類到任務、筆記、專案或「以後再說」。
3. **工作** — 做你的事。在當天的 daily note 記錄觀察。
4. **摘要** — 執行 `adjutant daily` 產出結構化日報。
5. **回顧** — 每週執行 `adjutant weekly` 產出週回顧簡報。

## 安裝

```bash
# 一鍵安裝
git clone https://github.com/Stephenchouchou/Adjutant.git
cd Adjutant
./install.sh
```

安裝腳本處理所有事：Python 版本檢查、虛擬環境建立、依賴安裝（含 Telegram bot）、初始設定。

```bash
# 手動安裝
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
adjutant init
```

需求：Python 3.12+，以及 AI 後端（預設 `claude` CLI，或 Ollama）。

## 使用方式

### CLI 對話

```bash
adjutant                                          # 互動式 REPL
adjutant chat "inbox 裡有什麼需要處理的？"           # 單次提問
adjutant chat --file projects/xxx.md "進度？"       # 附帶檔案上下文
```

### SOP 指令

```bash
adjutant triage     # 收件匣分類
adjutant daily      # 每日報告
adjutant tasks      # 任務掃描
adjutant weekly     # 週報
adjutant sop list   # 列出所有 SOP
```

### Web UI（指揮中心）

```bash
adjutant web                    # 開啟 http://127.0.0.1:8100
adjutant web --daemon           # 背景執行
```

主要功能：
- **指揮中心介面** — HUD 風格，即時顯示收件匣、任務、提醒、Wiki 狀態
- **命令面板**（`Ctrl+K`）— 統一入口，搜尋並執行所有操作
- **Wiki 知識庫** — force-directed 互動圖譜、頁面瀏覽器、行內編輯
- **筆記瀏覽與編輯** — 在瀏覽器內瀏覽和編輯 Markdown 檔案
- **語意搜尋** — RAG 驅動的全筆記本搜尋
- **提醒系統** — 設定定時提醒，透過 Web UI 和 Telegram 送達
- **Session 管理** — 恢復歷史對話
- **截圖貼上** — 直接把圖片丟進筆記本
- **響應式排版** — 適配桌面、平板、手機螢幕

### Wiki 知識庫

基於 [Karpathy 的 LLM Wiki 模式](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — AI 持續將你的筆記蒸餾成結構化的知識頁面。

```bash
adjutant wiki init                          # 初始化 wiki 結構
adjutant wiki ingest notes/my-note.md       # 將筆記消化成 wiki 頁面
adjutant wiki query "X 怎麼運作的？"          # 兩階段查詢
adjutant wiki lint                          # 健康檢查（矛盾、孤立頁面、缺少交叉引用）
```

三層架構：**原始筆記**（你的，不動）→ **Wiki**（LLM 維護的摘要/實體/概念/比較頁）→ **Schema**（慣例與規範）。

Web UI 的圖譜視圖：節點大小反映連結數、hover 高亮鄰居節點、單擊開啟頁面。

### Telegram Bot

從手機和副官對話。提問會得到 AI 回答；筆記會被捕獲到收件匣。

```bash
adjutant bot    # 啟動 Telegram bot
```

設定方式：向 [@BotFather](https://t.me/BotFather) 申請 token，設定環境變數 `ADJUTANT_BOT_TOKEN`，也可從 Web UI 頂部列的 BOT 按鈕操作。

### AI 後端

支援多種 AI 後端：

| 後端 | 設定方式 | 需求 |
|------|---------|------|
| Claude | `ai_tool = "claude"` | `claude` CLI |
| Gemini | `ai_tool = "gemini"` | `gemini` CLI |
| Codex | `ai_tool = "codex"` | `codex` CLI |
| Ollama（本地） | `ai_tool = "ollama"` | Ollama 服務 + 模型 |

Ollama 設定：

```toml
# ~/.adjutant/config.toml
ai_tool = "ollama"
ai_model = "llama3.1"
ollama_base_url = "http://localhost:11434"
```

### MCP Server

透過 [Model Context Protocol](https://modelcontextprotocol.io/) 將 Adjutant 的能力暴露給 AI 編碼工具（Claude Code、Cursor 等）。

```json
// .mcp.json
{
  "mcpServers": {
    "adjutant": { "command": "adjutant", "args": ["mcp"] }
  }
}
```

提供 15 個 MCP tools（讀寫筆記、收件匣、搜尋、記憶、SOP、Wiki 操作），2 個 resources，4 個 prompts。

## 設定

設定檔：`~/.adjutant/config.toml`

```toml
notebook_root = "/home/you/YourNotebook"
ai_tool = "claude"
ai_model = ""
ollama_base_url = "http://localhost:11434"

[paths]
inbox = "inbox.md"
tasks = "tasks.md"
daily_dir = "journal/daily"
wiki_dir = "wiki"

[bot]
platform = "telegram"
allowed_chat_ids = []
```

## 架構

```
介面層    CLI · Web UI · Telegram · MCP
            │
核心引擎    對話（人設 + 指令 + Wiki + RAG + 記憶）
            SOP v2（輸入參數、多步驟、約束）
            Wiki（消化、查詢、健檢、圖譜）
            Dispatcher · 檔案操作 · Session · 提醒
            │
情報層      Embeddings（Ollama / sentence-transformers）
            RAG 索引（LanceDB, Markdown 分塊）
            向量記憶（LanceDB, 語意檢索）
            │
外部        AI 後端 · Markdown 筆記本 · ~/.adjutant/
```

## 授權

MIT
