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

from adjutant.config import AdjutantConfig, load_config, load_bot_token, save_bot_token
from adjutant.core.chat import build_chat_prompt
from adjutant.core.dispatcher import Dispatcher
from adjutant.core.sop import SOPStore, build_sop_prompt
from adjutant.models.session import Session


class ImageUpload(PydanticBaseModel):
    data: str  # base64-encoded image
    filename: str = ""


class TokenPayload(PydanticBaseModel):
    token: str

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
            rel_path = save_attachment(raw, config.notebook_root, ext)
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
        return get_notebook_stats(config.notebook_root)

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
        try:
            await bot_instance.start_background()
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
        dispatcher = Dispatcher()
        model = config.ai_model or None

        # Send init
        store = SOPStore(config.sop_dirs_builtin, config.sop_dirs_user)
        sops = [
            {"key": s.key, "label": s.label, "icon": s.icon, "description": s.description}
            for s in store.list_sops()
        ]
        from adjutant.core.file_ops import get_notebook_stats
        stats = get_notebook_stats(config.notebook_root)
        if not await _safe_send(websocket, {
            "type": "init",
            "sops": sops,
            "ai_tool": config.ai_tool,
            "stats": stats,
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

                if msg_type == "message":
                    text = data.get("text", "").strip()
                    image_paths = data.get("image_paths", [])
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

                    full_prompt = build_chat_prompt(prompt_text, session)
                    session.add_message("user", text)

                    await _safe_send(websocket, {"type": "stream_start"})
                    response = await _stream_ai(full_prompt)
                    session.add_message("adjutant", response)
                    if not connected:
                        break
                    await _safe_send(websocket, {"type": "stream_end"})

                elif msg_type == "run_sop":
                    sop_key = data.get("key", "")
                    sop = store.get_sop(sop_key)
                    if not sop:
                        await _safe_send(websocket, {
                            "type": "error",
                            "data": f"SOP not found: {sop_key}",
                        })
                        continue

                    prompt = build_sop_prompt(sop, config.notebook_root)
                    session.add_message("user", f"[SOP: {sop.label}]")

                    await _safe_send(websocket, {
                        "type": "sop_start",
                        "key": sop_key,
                        "label": sop.label,
                        "icon": sop.icon,
                    })

                    response = await _stream_ai(prompt)
                    session.add_message("adjutant", response)
                    if not connected:
                        break
                    await _safe_send(websocket, {"type": "stream_end"})

                    # Offer file write if SOP output is file:
                    if sop.output.startswith("file:"):
                        from datetime import datetime as dt
                        rel_path = sop.output[5:].replace(
                            "{today}", dt.now().strftime("%Y-%m-%d")
                        )
                        await _safe_send(websocket, {
                            "type": "sop_file_confirm",
                            "path": rel_path,
                            "content": response,
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
