"""Adjutant Web UI — FastAPI + WebSocket server."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel as PydanticBaseModel

from adjutant.config import (
    AdjutantConfig,
    TOOL_MODELS,
    load_config,
    load_bot_token,
    load_memory,
    load_persona,
    save_bot_token,
    save_config,
    save_memory,
    save_persona,
)
from adjutant.core.chat import DEFAULT_PERSONA
from adjutant.core.chat import build_chat_prompt
from adjutant.core.dispatcher import Dispatcher
from adjutant.core.sop import SOPStore, build_sop_prompt, build_step_prompt, resolve_inputs
from adjutant.models.session import Session


class ImageUpload(PydanticBaseModel):
    data: str  # base64-encoded image
    filename: str = ""


class TokenPayload(PydanticBaseModel):
    token: str


class ContentPayload(PydanticBaseModel):
    content: str
    category: str = "fact"


class ModelPayload(PydanticBaseModel):
    ai_tool: str
    ai_model: str


class ConfigPayload(PydanticBaseModel):
    ollama_base_url: str | None = None
    notebook_root: str | None = None
    inbox: str | None = None
    tasks: str | None = None
    daily_dir: str | None = None
    projects_dir: str | None = None
    assets_dir: str | None = None
    bot_allowed_chat_ids: list[int] | None = None


class DirectivePayload(PydanticBaseModel):
    filename: str
    trigger: str
    body: str


class ReminderPayload(PydanticBaseModel):
    text: str
    fire_at: str  # ISO8601 or relative time string
    chat_ids: list[int] | None = None


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


async def _safe_send(ws: WebSocket, data: dict) -> bool:
    """Send JSON over WebSocket, return False if connection is gone."""
    try:
        await ws.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        return False


def create_app(
    config: AdjutantConfig | None = None,
    auto_shutdown: bool = True,
) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Adjutant Web UI")

    if config is None:
        config = load_config()
    if config is None:
        raise RuntimeError("Adjutant not configured. Run 'adjutant init' first.")

    active_connections: dict[int, WebSocket] = {}
    shutdown_task: asyncio.Task | None = None
    SHUTDOWN_GRACE_SECONDS = 5

    async def _schedule_shutdown():
        await asyncio.sleep(SHUTDOWN_GRACE_SECONDS)
        if not active_connections:
            os.kill(os.getpid(), signal.SIGINT)

    async def broadcast(data: dict) -> None:
        """Send a message to all connected WebSocket clients."""
        dead = []
        for conn_id, ws in active_connections.items():
            if not await _safe_send(ws, data):
                dead.append(conn_id)
        for conn_id in dead:
            active_connections.pop(conn_id, None)

    # ── Static files & index ──────────────────────────────

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    # ── REST APIs ─────────────────────────────────────────

    @app.get("/api/sops")
    async def list_sops():
        store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
        return [
            {
                "key": s.key,
                "label": s.label,
                "icon": s.icon,
                "description": s.description,
            }
            for s in store.list_sops()
        ]

    @app.get("/api/sessions")
    async def list_sessions():
        sessions = Session.list_sessions()
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "message_count": len(s.messages),
                "created": s.created_at.isoformat(),
            }
            for s in sessions[:20]
        ]

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        s = Session.load(session_id)
        if not s:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Session not found"}, status_code=404)
        return {
            "id": str(s.id),
            "name": s.name,
            "created": s.created_at.isoformat(),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                }
                for m in s.messages
            ],
        }

    @app.post("/api/upload")
    async def upload_image(payload: ImageUpload):
        import base64
        from adjutant.core.file_ops import save_attachment

        ext = ".png"
        if payload.filename:
            suffix = Path(payload.filename).suffix.lower()
            if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                ext = suffix
        try:
            raw = base64.b64decode(payload.data)
            rel_path = save_attachment(raw, config.notebook_root, ext, assets_dir=config.paths.assets_dir)
            return {"path": rel_path}
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/api/config")
    async def get_config():
        return {
            "ai_tool": config.ai_tool,
            "ai_model": config.ai_model,
            "notebook_root": str(config.notebook_root),
        }

    @app.get("/api/stats")
    async def get_stats():
        from adjutant.core.file_ops import get_notebook_stats
        return get_notebook_stats(config.notebook_root, paths=config.paths)

    @app.get("/api/index/status")
    async def index_status():
        """Get RAG index build status."""
        from adjutant.core.index import IndexMeta
        meta = IndexMeta.load()
        return {
            "built": bool(meta.last_built),
            "last_built": meta.last_built,
            "file_count": meta.file_count,
            "chunk_count": meta.chunk_count,
        }

    _index_building = False

    @app.post("/api/index/build")
    async def build_index_api():
        """Build or rebuild the RAG index."""
        nonlocal _index_building
        if _index_building:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Index build already in progress"}, status_code=409)
        try:
            _index_building = True
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.index import build_index

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            meta = await build_index(config.notebook_root, embedder)
            return {
                "ok": True,
                "file_count": meta.file_count,
                "chunk_count": meta.chunk_count,
                "last_built": meta.last_built,
            }
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)
        finally:
            _index_building = False

    @app.get("/api/search")
    async def search_notes(q: str = "", k: int = 5):
        """Semantic search over the notebook index."""
        if not q:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "q (query) parameter required"}, status_code=400)
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.retriever import retrieve

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            results = await retrieve(q, embedder, top_k=k)
            return {
                "query": q,
                "results": [
                    {
                        "source": r.source,
                        "heading": r.heading,
                        "text": r.text,
                        "score": r.score,
                    }
                    for r in results
                ],
            }
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                {"error": f"Search failed: {e}. Is the index built?"},
                status_code=500,
            )

    @app.get("/api/files")
    async def list_files(path: str = ""):
        from adjutant.core.file_ops import list_directory, FileOutsideRootError
        try:
            return list_directory(config.notebook_root, path)
        except (FileNotFoundError, FileOutsideRootError) as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/api/files/read")
    async def read_file_api(path: str = ""):
        from adjutant.core.file_ops import read_file, FileOutsideRootError, FileTooLargeError
        if not path:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "path required"}, status_code=400)
        try:
            content = read_file(config.notebook_root / path, config.notebook_root)
            return {"path": path, "content": content}
        except (FileNotFoundError, FileOutsideRootError, FileTooLargeError) as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=400)

    # ── Persona & Memory ─────────────────────────────────────

    @app.get("/api/persona")
    async def get_persona_api():
        custom = load_persona()
        return {
            "content": custom if custom else DEFAULT_PERSONA,
            "is_custom": custom is not None,
            "default": DEFAULT_PERSONA,
        }

    @app.post("/api/persona")
    async def save_persona_api(payload: ContentPayload):
        save_persona(payload.content)
        return {"ok": True}

    @app.post("/api/persona/reset")
    async def reset_persona_api():
        from adjutant.config import PERSONA_PATH
        if PERSONA_PATH.is_file():
            PERSONA_PATH.unlink()
        return {"ok": True, "content": DEFAULT_PERSONA}

    @app.get("/api/memory")
    async def get_memory_api():
        content = load_memory()
        return {"content": content or ""}

    @app.post("/api/memory")
    async def save_memory_api(payload: ContentPayload):
        save_memory(payload.content)
        return {"ok": True}

    @app.get("/api/memory/entries")
    async def list_memory_entries(category: str | None = None):
        """List all vector memory entries."""
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.memory import MemoryStore

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            store = MemoryStore(embedder)
            entries = store.list_all(category=category)
            return {
                "count": len(entries),
                "entries": [
                    {
                        "id": e.id,
                        "content": e.content,
                        "category": e.category,
                        "created": e.created,
                        "source": e.source,
                    }
                    for e in entries
                ],
            }
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/memory/entries")
    async def add_memory_entry(payload: ContentPayload):
        """Add a new vector memory entry."""
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.memory import MemoryStore

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            store = MemoryStore(embedder)
            entry = await store.add(payload.content, category=payload.category, source="web")
            return {"ok": True, "id": entry.id}
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/api/memory/entries/{memory_id}")
    async def delete_memory_entry(memory_id: str):
        """Delete a vector memory entry by ID."""
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.memory import MemoryStore

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            store = MemoryStore(embedder)
            deleted = store.forget(memory_id)
            if not deleted:
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": "Memory not found"}, status_code=404)
            return {"ok": True}
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)

    # ── Model Selection ────────────────────────────────────────

    @app.get("/api/models")
    async def get_models():
        return {
            "current_tool": config.ai_tool,
            "current_model": config.ai_model,
            "tools": {
                tool: [{"id": m[0], "label": m[1]} for m in models]
                for tool, models in TOOL_MODELS.items()
            },
        }

    @app.post("/api/models")
    async def set_model(payload: ModelPayload):
        config.ai_tool = payload.ai_tool
        config.ai_model = payload.ai_model
        save_config(config)
        return {"ok": True, "ai_tool": config.ai_tool, "ai_model": config.ai_model}

    # ── Settings Management ────────────────────────────────────

    @app.get("/api/settings")
    async def get_settings():
        """Get full configuration for settings panel."""
        return {
            "ai_tool": config.ai_tool,
            "ai_model": config.ai_model,
            "ollama_base_url": config.ollama_base_url,
            "notebook_root": str(config.notebook_root),
            "paths": {
                "inbox": config.paths.inbox,
                "tasks": config.paths.tasks,
                "daily_dir": config.paths.daily_dir,
                "projects_dir": config.paths.projects_dir,
                "assets_dir": config.paths.assets_dir,
            },
            "bot": {
                "platform": config.bot.platform,
                "allowed_chat_ids": config.bot.allowed_chat_ids,
                "has_token": bool(load_bot_token()),
            },
        }

    @app.post("/api/settings")
    async def save_settings(payload: ConfigPayload):
        """Update configuration settings."""
        if payload.ollama_base_url is not None:
            config.ollama_base_url = payload.ollama_base_url
        if payload.notebook_root is not None:
            config.notebook_root = Path(payload.notebook_root)
        if payload.inbox is not None:
            config.paths.inbox = payload.inbox
        if payload.tasks is not None:
            config.paths.tasks = payload.tasks
        if payload.daily_dir is not None:
            config.paths.daily_dir = payload.daily_dir
        if payload.projects_dir is not None:
            config.paths.projects_dir = payload.projects_dir
        if payload.assets_dir is not None:
            config.paths.assets_dir = payload.assets_dir
        if payload.bot_allowed_chat_ids is not None:
            config.bot.allowed_chat_ids = payload.bot_allowed_chat_ids
        save_config(config)
        return {"ok": True}

    # ── Memory Search ──────────────────────────────────────────

    @app.get("/api/memory/search")
    async def search_memory_api(q: str = "", k: int = 5):
        """Semantic search over vector memory."""
        if not q:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "q (query) parameter required"}, status_code=400)
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.memory import MemoryStore, format_memory_context

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            store = MemoryStore(embedder)
            entries = await store.search(q, top_k=k)
            return {
                "query": q,
                "entries": [
                    {
                        "id": e.id,
                        "content": e.content,
                        "category": e.category,
                        "created": e.created,
                        "source": e.source,
                    }
                    for e in entries
                ],
            }
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/memory/import")
    async def import_memory_api():
        """Import memories from flat memory.md into vector store."""
        try:
            from adjutant.core.embeddings import get_embedding_provider
            from adjutant.core.memory import MemoryStore

            embedder = await get_embedding_provider(
                ollama_base_url=config.ollama_base_url,
            )
            store = MemoryStore(embedder)
            count = await store.import_from_file()
            return {"ok": True, "imported": count}
        except Exception as e:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": str(e)}, status_code=500)

    # ── Directives ─────────────────────────────────────────────

    @app.get("/api/directives")
    async def list_directives():
        """List all directives (built-in and user)."""
        from adjutant.prompts import load_directives
        directives = load_directives()
        return {
            "directives": [
                {
                    "trigger": d.trigger,
                    "body": d.body,
                    "source": str(d.source),
                    "is_user": ".adjutant" in str(d.source),
                    "filename": d.source.stem,
                }
                for d in directives
            ],
        }

    @app.post("/api/directives")
    async def create_directive(payload: DirectivePayload):
        """Create or update a user directive."""
        user_dir = Path.home() / ".adjutant" / "prompts" / "directives"
        user_dir.mkdir(parents=True, exist_ok=True)
        filename = payload.filename.replace("/", "_").replace("..", "_")
        if not filename.endswith(".md"):
            filename += ".md"
        path = user_dir / filename
        content = f"---\ntrigger: {payload.trigger}\n---\n\n{payload.body}\n"
        path.write_text(content, encoding="utf-8")
        # Clear directive cache
        from adjutant.prompts import load_directives
        load_directives.__wrapped__ if hasattr(load_directives, '__wrapped__') else None
        return {"ok": True, "path": str(path)}

    @app.delete("/api/directives/{filename}")
    async def delete_directive(filename: str):
        """Delete a user directive."""
        user_dir = Path.home() / ".adjutant" / "prompts" / "directives"
        path = user_dir / f"{filename}.md"
        if not path.is_file():
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Directive not found"}, status_code=404)
        if ".adjutant" not in str(path):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Cannot delete built-in directives"}, status_code=403)
        path.unlink()
        return {"ok": True}

    # ── SOP Management ─────────────────────────────────────────

    @app.get("/api/sops/detail/{sop_key}")
    async def get_sop_detail(sop_key: str):
        """Get full SOP details including v2 metadata."""
        store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
        sop = store.get_sop(sop_key)
        if not sop:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "SOP not found"}, status_code=404)
        return {
            "key": sop.key,
            "label": sop.label,
            "icon": sop.icon,
            "description": sop.description,
            "version": sop.version,
            "author": sop.author,
            "tags": sop.tags,
            "is_builtin": sop.is_builtin,
            "is_v2": sop.is_v2,
            "is_multistep": sop.is_multistep,
            "tools": sop.tools,
            "constraints": sop.constraints,
            "output": sop.output,
            "inputs": [
                {
                    "name": i.name,
                    "type": i.type,
                    "default": i.default,
                    "description": i.description,
                }
                for i in sop.inputs
            ],
            "steps": [
                {"name": s.name, "prompt_preview": s.prompt[:100]}
                for s in sop.steps
            ],
        }

    @app.post("/api/sops/create")
    async def create_sop_api(payload: dict):
        """Create a new user SOP template."""
        from adjutant.core.sop import SOPStore as Store
        key = payload.get("key", "")
        label = payload.get("label", key)
        description = payload.get("description", "")
        files = payload.get("files", [])
        body = payload.get("body", "")
        if not key:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "key is required"}, status_code=400)
        store = Store(config.sop_dirs_builtin, config.sop_dirs_user)
        path = store.save_sop(key, label, description, files, body)
        return {"ok": True, "path": str(path)}

    # ── Reminders ──────────────────────────────────────────

    from adjutant.core.reminders import ReminderScheduler, ReminderStore

    reminder_store = ReminderStore()

    async def _send_reminder(chat_id: int, text: str) -> None:
        """Send a reminder via Telegram bot. Raises if bot not available."""
        if bot_instance and bot_instance.running and bot_instance._app:
            await bot_instance._app.bot.send_message(chat_id=chat_id, text=text)
        else:
            raise RuntimeError("Bot not running")

    reminder_scheduler = ReminderScheduler(reminder_store, send_fn=_send_reminder)

    @app.on_event("startup")
    async def _start_scheduler():
        await reminder_scheduler.start()
        # Auto-start bot if token exists
        token = load_bot_token()
        if token:
            try:
                from adjutant.bot.telegram import AdjutantTelegramBot
                nonlocal bot_instance
                bot_instance = AdjutantTelegramBot(config, token)
                bot_instance.set_ai_handler(
                    dispatcher_factory=Dispatcher,
                    broadcast=broadcast,
                    ai_tool=config.ai_tool,
                    ai_model=config.ai_model or None,
                )
                bot_instance.set_scheduler(reminder_scheduler)
                await bot_instance.start_background()
                await reminder_scheduler.flush_queue()
                logger.info("Bot auto-started on server launch")
            except Exception as e:
                logger.warning("Bot auto-start failed: %s", e)
                bot_instance = None

    @app.get("/api/reminders")
    async def list_reminders():
        pending = reminder_scheduler.list_pending()
        return {
            "reminders": [
                {
                    "id": r.id,
                    "text": r.text,
                    "fire_at": r.fire_at.isoformat(),
                    "chat_ids": r.chat_ids,
                    "source": r.source,
                    "fired": r.fired,
                    "created_at": r.created_at.isoformat(),
                }
                for r in sorted(pending, key=lambda x: x.fire_at)
            ],
        }

    @app.post("/api/reminders")
    async def create_reminder(payload: ReminderPayload):
        from adjutant.bot.handlers import parse_reminder_time
        from datetime import datetime as dt, timezone as tz

        # Try ISO8601 first, then relative/short format
        fire_at = None
        try:
            fire_at = dt.fromisoformat(payload.fire_at)
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=tz.utc)
        except ValueError:
            fire_at = parse_reminder_time(payload.fire_at)

        if not fire_at:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                {"error": f"Cannot parse time: {payload.fire_at}"},
                status_code=400,
            )

        chat_ids = payload.chat_ids or config.bot.allowed_chat_ids
        if not chat_ids:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                {"error": "No chat_ids specified and no allowed_chat_ids configured"},
                status_code=400,
            )

        reminder = await reminder_scheduler.add(
            payload.text, fire_at, chat_ids=chat_ids, source="web",
        )
        return {"ok": True, "id": reminder.id, "fire_at": reminder.fire_at.isoformat()}

    @app.delete("/api/reminders/{reminder_id}")
    async def delete_reminder(reminder_id: str):
        if reminder_scheduler.cancel(reminder_id):
            return {"ok": True}
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Reminder not found"}, status_code=404)

    # ── Bot Management ─────────────────────────────────────

    bot_instance = None

    @app.get("/api/bot/status")
    async def bot_status():
        token = load_bot_token()
        has_token = bool(token)
        running = bot_instance is not None and bot_instance.running
        return {
            "has_token": has_token,
            "running": running,
            "platform": config.bot.platform,
        }

    @app.post("/api/bot/setup")
    async def bot_setup(payload: TokenPayload):
        token = payload.token.strip()
        if not token:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Token is required"}, status_code=400)
        save_bot_token(token)
        return {"ok": True, "message": "Token saved"}

    @app.post("/api/bot/start")
    async def bot_start():
        nonlocal bot_instance
        from fastapi.responses import JSONResponse

        # Stop existing instance first to avoid Conflict errors
        if bot_instance:
            try:
                await bot_instance.stop()
            except Exception:
                pass
            bot_instance = None

        token = load_bot_token()
        if not token:
            return JSONResponse({"error": "No bot token configured"}, status_code=400)

        try:
            from adjutant.bot.telegram import AdjutantTelegramBot
        except ImportError:
            return JSONResponse(
                {"error": "python-telegram-bot not installed. Run: pip install 'adjutant[bot]'"},
                status_code=400,
            )

        bot_instance = AdjutantTelegramBot(config, token)
        bot_instance.set_ai_handler(
            dispatcher_factory=Dispatcher,
            broadcast=broadcast,
            ai_tool=config.ai_tool,
            ai_model=config.ai_model or None,
        )
        bot_instance.set_scheduler(reminder_scheduler)
        try:
            await bot_instance.start_background()
            await reminder_scheduler.flush_queue()
        except Exception as e:
            bot_instance = None
            logger.exception("Bot start failed: %s", e)
            return JSONResponse({"error": f"Bot start failed: {e}"}, status_code=500)

        return {"ok": True, "message": "Bot started"}

    @app.post("/api/bot/stop")
    async def bot_stop():
        nonlocal bot_instance
        if bot_instance and bot_instance.running:
            await bot_instance.stop()
            bot_instance = None
            return {"ok": True, "message": "Bot stopped"}
        return {"ok": True, "message": "Bot not running"}

    @app.on_event("shutdown")
    async def _shutdown_bot():
        nonlocal bot_instance
        await reminder_scheduler.stop()
        if bot_instance and bot_instance.running:
            await bot_instance.stop()
            bot_instance = None

    # ── WebSocket chat ────────────────────────────────────

    @app.websocket("/ws")
    async def chat_ws(websocket: WebSocket):
        nonlocal shutdown_task

        await websocket.accept()
        conn_id = id(websocket)
        active_connections[conn_id] = websocket
        logger.info("WebSocket client connected (id=%s)", conn_id)

        if shutdown_task is not None and not shutdown_task.done():
            shutdown_task.cancel()
            shutdown_task = None

        session = Session(name="web-chat")
        dispatcher = Dispatcher(ollama_base_url=config.ollama_base_url)
        model = config.ai_model or None

        # Send init
        store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
        sops = [
            {
                "key": s.key, "label": s.label, "icon": s.icon,
                "description": s.description, "version": s.version,
                "is_v2": s.is_v2, "is_multistep": s.is_multistep,
                "has_inputs": bool(s.inputs),
                "tags": s.tags, "author": s.author,
            }
            for s in store.list_sops()
        ]
        from adjutant.core.file_ops import get_notebook_stats
        stats = get_notebook_stats(config.notebook_root, paths=config.paths)
        if not await _safe_send(websocket, {
            "type": "init",
            "sops": sops,
            "ai_tool": config.ai_tool,
            "stats": stats,
            "session_id": str(session.id),
        }):
            logger.warning("Client gone before init")
            active_connections.pop(conn_id, None)
            return

        connected = True

        async def _stream_ai(prompt: str) -> str:
            """Stream AI response to client, return collected text."""
            nonlocal connected
            parts: list[str] = []
            try:
                async for chunk in dispatcher.run(
                    config.ai_tool, prompt, config.notebook_root, model=model
                ):
                    parts.append(chunk)
                    if not await _safe_send(websocket, {
                        "type": "stream_chunk",
                        "data": chunk,
                    }):
                        logger.info("Client disconnected during stream")
                        connected = False
                        await dispatcher.cancel()
                        return "".join(parts)
            except Exception as e:
                logger.exception("Dispatcher error: %s", e)
                await _safe_send(websocket, {"type": "error", "data": str(e)})
            return "".join(parts)

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                logger.info("Received: type=%s", msg_type)

                if msg_type == "load_session":
                    session_id = data.get("session_id", "")
                    loaded = Session.load(session_id)
                    if loaded:
                        session = loaded
                        session.name = "web-chat (resumed)"
                        await _safe_send(websocket, {
                            "type": "session_loaded",
                            "id": str(session.id),
                            "messages": [
                                {"role": m.role, "content": m.content}
                                for m in session.messages
                            ],
                        })
                    else:
                        await _safe_send(websocket, {
                            "type": "error",
                            "data": f"Session not found: {session_id}",
                        })

                elif msg_type == "resume_session":
                    session_id = data.get("session_id", "")
                    loaded = Session.load(session_id)
                    if loaded:
                        session = loaded
                        session.name = "web-chat (resumed)"
                    # Always send back current session state
                    await _safe_send(websocket, {
                        "type": "session_resumed",
                        "id": str(session.id),
                        "messages": [
                            {"role": m.role, "content": m.content}
                            for m in session.messages
                        ],
                    })

                elif msg_type == "message":
                    text = data.get("text", "").strip()
                    image_paths = data.get("image_paths", [])
                    file_paths = data.get("file_paths", [])
                    if not text and not image_paths:
                        continue

                    prompt_text = text
                    if image_paths:
                        paths_str = "、".join(f"`{p}`" for p in image_paths)
                        prompt_text += (
                            f"\n\n指揮官貼了截圖，已存入筆記系統：{paths_str}\n"
                            "請將圖片連結（`![描述](路徑)`）寫入適當的 md 檔案"
                            "（例如今日的 daily note 或相關專案檔）。"
                        )

                    # Attach file context
                    if file_paths:
                        from adjutant.core.file_ops import read_file as _read_file
                        file_sections = []
                        for fp in file_paths:
                            try:
                                content = _read_file(
                                    config.notebook_root / fp, config.notebook_root
                                )
                                file_sections.append(f"### {fp}\n\n{content}")
                            except (FileNotFoundError, OSError):
                                pass
                        if file_sections:
                            prompt_text += "\n\n## 附加檔案\n\n" + "\n\n---\n\n".join(
                                file_sections
                            )

                    full_prompt = build_chat_prompt(prompt_text, session)
                    session.add_message("user", text)

                    await _safe_send(websocket, {"type": "stream_start"})
                    response = await _stream_ai(full_prompt)
                    session.add_message("adjutant", response)
                    if not connected:
                        break
                    await _safe_send(websocket, {"type": "stream_end"})
                    session.save()

                elif msg_type == "run_sop":
                    sop_key = data.get("key", "")
                    input_values = data.get("inputs", {})
                    sop = store.get_sop(sop_key)
                    if not sop:
                        await _safe_send(websocket, {
                            "type": "error",
                            "data": f"SOP not found: {sop_key}",
                        })
                        continue

                    # Check if SOP needs inputs that weren't provided
                    if sop.inputs and not input_values:
                        required = sop.get_required_inputs()
                        defaults = resolve_inputs(sop)
                        if required:
                            await _safe_send(websocket, {
                                "type": "sop_input_request",
                                "key": sop_key,
                                "label": sop.label,
                                "icon": sop.icon,
                                "inputs": [
                                    {
                                        "name": i.name,
                                        "type": i.type,
                                        "default": defaults.get(i.name, i.default),
                                        "description": i.description,
                                    }
                                    for i in sop.inputs
                                ],
                            })
                            continue

                    resolved = resolve_inputs(sop, input_values)
                    session.add_message("user", f"[SOP: {sop.label}]")

                    await _safe_send(websocket, {
                        "type": "sop_start",
                        "key": sop_key,
                        "label": sop.label,
                        "icon": sop.icon,
                    })

                    # Multi-step execution (v2)
                    if sop.is_multistep:
                        previous_output = None
                        for i, step in enumerate(sop.steps):
                            step_label = f"步驟 {i + 1}/{len(sop.steps)}: {step.name}"
                            await _safe_send(websocket, {
                                "type": "sop_step",
                                "step": i + 1,
                                "total": len(sop.steps),
                                "name": step.name,
                            })
                            prompt = build_step_prompt(
                                sop, step, config.notebook_root,
                                input_values=resolved,
                                previous_output=previous_output,
                            )
                            response = await _stream_ai(prompt)
                            if not connected:
                                break
                            previous_output = response

                        if not connected:
                            break
                        session.add_message("adjutant", previous_output or "")
                        await _safe_send(websocket, {"type": "stream_end"})
                        session.save()
                        response = previous_output or ""
                    else:
                        # Single-step execution
                        prompt = build_sop_prompt(
                            sop, config.notebook_root, input_values=resolved,
                        )
                        response = await _stream_ai(prompt)
                        session.add_message("adjutant", response)
                        if not connected:
                            break
                        await _safe_send(websocket, {"type": "stream_end"})
                        session.save()

                    # Offer file write with diff preview
                    if sop.output.startswith("file:"):
                        from datetime import datetime as dt
                        rel_path = sop.output[5:].replace(
                            "{today}", dt.now().strftime("%Y-%m-%d")
                        )
                        # Try to read existing file for diff
                        existing = ""
                        try:
                            from adjutant.core.file_ops import read_file
                            existing = read_file(
                                config.notebook_root / rel_path, config.notebook_root
                            )
                        except (FileNotFoundError, OSError):
                            pass
                        await _safe_send(websocket, {
                            "type": "sop_file_confirm",
                            "path": rel_path,
                            "content": response,
                            "existing": existing,
                        })

                elif msg_type == "sop_file_write":
                    from adjutant.core.file_ops import write_file
                    rel_path = data.get("path", "")
                    content = data.get("content", "")
                    try:
                        target = config.notebook_root / rel_path
                        write_file(target, content, config.notebook_root)
                        await _safe_send(websocket, {
                            "type": "file_written",
                            "path": rel_path,
                        })
                    except Exception as e:
                        await _safe_send(websocket, {
                            "type": "error",
                            "data": f"File write failed: {e}",
                        })

                elif msg_type == "cancel":
                    await dispatcher.cancel()
                    await _safe_send(websocket, {"type": "cancelled"})

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected (id=%s)", conn_id)
        except Exception:
            logger.exception("WebSocket error")
        finally:
            await dispatcher.cleanup()
            active_connections.pop(conn_id, None)

            if session.messages:
                session.save()

            if auto_shutdown and not active_connections:
                shutdown_task = asyncio.create_task(_schedule_shutdown())

    return app
