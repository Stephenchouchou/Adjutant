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

## SOP Operations

Adjutant runs structured operations (SOPs) on your notebook:

| Command | SOP | What it does |
|---------|-----|-------------|
| `adjutant triage` | Inbox Triage | Classify inbox items as task/note/project/someday |
| `adjutant daily` | Daily Summary | Structure today's daily note into Completed/Carry Forward/Insights |
| `adjutant tasks` | Task Update | Scan tasks.md for stale/blocked items, suggest next actions |
| `adjutant weekly` | Weekly Report | Summarize the past 7 days into a weekly briefing |

You can also create custom SOPs in `~/.adjutant/sop/` using the same markdown + YAML frontmatter format.

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

Requirements: Python 3.12+, and an AI CLI tool (`claude` by default).

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
- Command Center interface with real-time notebook stats (inbox count, tasks, daily status)
- Command Palette (`Ctrl+K`) for quick SOP execution
- File browser to view markdown notes
- Image paste/drop to save screenshots into notebook
- Session history archive

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

## Configuration

Config lives at `~/.adjutant/config.toml`:

```toml
notebook_root = "/home/you/YourNotebook"
ai_tool = "claude"        # or "gemini", "codex"
ai_model = ""             # empty = use CLI default

[sop_dirs]
builtin = "/path/to/src/adjutant/sop"
user = "/home/you/.adjutant/sop"

[paths]
inbox = "inbox.md"                # capture box
tasks = "tasks.md"                # task tracking
daily_dir = "journal/daily"       # daily notes directory
projects_dir = "projects"         # projects directory
assets_dir = "assets"             # images & attachments

[bot]
platform = "telegram"
allowed_chat_ids = []     # empty = accept all (check logs for IDs)
```

### Persona & Memory

- **Persona** (`~/.adjutant/persona.md`): Customize the adjutant's personality and behavior. Edit via Web UI (Command Palette → Persona) or directly.
- **Memory** (`~/.adjutant/memory.md`): Persistent memory shared across all sessions and models. The adjutant includes this in every prompt.
- **Model selection**: Switch between AI backends (Claude, Gemini, Codex) and specific models via Web UI or config.

## Architecture

```
┌─────────────────────────────────────────────────┐
│ Interfaces                                       │
│  CLI (Click)  ·  Web UI (FastAPI)  ·  Telegram  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────┐
│ Core Engine                                      │
│  Chat (persona + prompt)  ·  SOP (templates)    │
│  Dispatcher (AI subprocess)  ·  File Ops        │
│  Session (conversation history)                  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────┐
│ External                                         │
│  AI CLI (claude/gemini)  ·  Notebook (markdown) │
│  ~/.adjutant/ (config, sessions, custom SOPs)   │
└─────────────────────────────────────────────────┘
```

## Tech Stack

- Python 3.12+
- Click (CLI framework)
- FastAPI + WebSocket (web UI)
- Pydantic (data models)
- Rich (terminal formatting)
- python-telegram-bot (optional, for Telegram integration)

## License

MIT
