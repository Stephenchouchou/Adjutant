"""Adjutant Telegram Bot — long-polling adapter with AI routing.

Translates Telegram Update events into AI chat or inbox capture.
Supports both standalone (adjutant bot) and embedded (adjutant web) modes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from adjutant.bot.handlers import (
    handle_document_capture,
    handle_image_capture,
    handle_list_inbox,
    handle_list_tasks,
    handle_sticker_capture,
    handle_text_capture,
)
from adjutant.config import AdjutantConfig

logger = logging.getLogger(__name__)


class AdjutantTelegramBot:
    """Telegram bot with AI-routed message handling."""

    def __init__(self, config: AdjutantConfig, token: str) -> None:
        self.config = config
        self.token = token
        self.notebook_root = config.notebook_root
        self.allowed_ids: set[int] = set(config.bot.allowed_chat_ids)
        self._app: Application | None = None
        self._running = False

        # AI handler (injected via set_ai_handler)
        self._dispatcher: Any = None
        self._session: Any = None
        self._broadcast: Callable[..., Coroutine] | None = None
        self._ai_tool: str = "claude"
        self._ai_model: str | None = None

    @property
    def running(self) -> bool:
        return self._running

    def set_ai_handler(
        self,
        dispatcher_factory: type,
        broadcast: Callable[..., Coroutine],
        ai_tool: str,
        ai_model: str | None,
    ) -> None:
        """Inject AI resources for smart message routing."""
        from adjutant.models.session import Session

        self._dispatcher = dispatcher_factory()
        self._broadcast = broadcast
        self._ai_tool = ai_tool
        self._ai_model = ai_model
        self._session = Session(name="telegram")

    def _check_auth(self, update: Update) -> bool:
        """Check if the chat is authorized. Log ID if allowlist is empty."""
        chat_id = update.effective_chat.id if update.effective_chat else 0
        if not self.allowed_ids:
            logger.info(
                "No allowed_chat_ids configured. Incoming chat_id=%s — "
                "add this to [bot] allowed_chat_ids in config to authorize.",
                chat_id,
            )
            return True
        if chat_id not in self.allowed_ids:
            logger.warning("Unauthorized chat_id=%s rejected.", chat_id)
            return False
        return True

    async def _cmd_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        await update.message.reply_text(
            "ADJUTANT ONLINE\n\n"
            "Send me any message — I'll answer questions or capture notes.\n"
            "Send a photo to save it to assets/.\n\n"
            "Commands:\n"
            "/inbox — List unchecked inbox items\n"
            "/tasks — List open tasks"
        )

    async def _cmd_inbox(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        reply = handle_list_inbox(self.notebook_root, paths=self.config.paths)
        await update.message.reply_text(reply)

    async def _cmd_tasks(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        reply = handle_list_tasks(self.notebook_root, paths=self.config.paths)
        await update.message.reply_text(reply)

    async def _on_text(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        text = update.message.text.strip()
        if not text:
            return

        # Broadcast user message to Web UI
        if self._broadcast:
            await self._broadcast({
                "type": "bot_message",
                "role": "user",
                "source": "telegram",
                "text": text,
            })

        # No AI handler → fallback to capture
        if not self._dispatcher or not self._session:
            reply = handle_text_capture(text, self.notebook_root, inbox=self.config.paths.inbox)
            await update.message.reply_text(reply)
            return

        try:
            from adjutant.core.chat import build_chat_prompt, chat_once

            prompt = build_chat_prompt(text, self._session)
            self._session.add_message("user", text)

            response = await chat_once(
                self._dispatcher, prompt, self.notebook_root,
                ai_tool=self._ai_tool, model=self._ai_model,
                timeout=300,
            )

            self._session.add_message("adjutant", response)

            # Send to Telegram (split if > 4000 chars)
            for i in range(0, max(len(response), 1), 4000):
                chunk = response[i:i + 4000]
                if chunk:
                    await update.message.reply_text(chunk)

            # Broadcast AI response to Web UI
            if self._broadcast:
                await self._broadcast({
                    "type": "bot_message",
                    "role": "adjutant",
                    "source": "telegram",
                    "text": response,
                })

            # Periodic session save
            if len(self._session.messages) % 10 == 0:
                self._session.save()

        except Exception as e:
            logger.exception("AI routing failed: %s", e)
            # Fallback: capture to inbox
            reply = handle_text_capture(text, self.notebook_root, inbox=self.config.paths.inbox)
            await update.message.reply_text(f"{reply}\n\n(AI unavailable: {e})")
            if self._broadcast:
                await self._broadcast({
                    "type": "bot_message",
                    "role": "system",
                    "source": "telegram",
                    "text": f"[Fallback] Captured to inbox: {text}",
                })

    async def _on_photo(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        data = await file.download_as_bytearray()
        caption = update.message.caption or None
        reply = handle_image_capture(
            bytes(data), ".jpg", caption, self.notebook_root,
            inbox=self.config.paths.inbox, assets_dir=self.config.paths.assets_dir,
        )
        await update.message.reply_text(reply)

        # Broadcast to Web UI
        if self._broadcast:
            await self._broadcast({
                "type": "bot_message",
                "role": "system",
                "source": "telegram",
                "text": reply,
            })

    async def _on_document(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        doc = update.message.document
        file = await context.bot.get_file(doc.file_id)
        data = await file.download_as_bytearray()
        filename = doc.file_name or "file.bin"
        caption = update.message.caption or None
        reply = handle_document_capture(
            bytes(data), filename, caption, self.notebook_root,
            inbox=self.config.paths.inbox, assets_dir=self.config.paths.assets_dir,
        )
        await update.message.reply_text(reply)

        if self._broadcast:
            await self._broadcast({
                "type": "bot_message",
                "role": "system",
                "source": "telegram",
                "text": reply,
            })

    async def _on_sticker(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self._check_auth(update):
            return
        sticker = update.message.sticker
        file = await context.bot.get_file(sticker.file_id)
        data = await file.download_as_bytearray()
        emoji = sticker.emoji
        reply = handle_sticker_capture(
            bytes(data), emoji, self.notebook_root,
            inbox=self.config.paths.inbox, assets_dir=self.config.paths.assets_dir,
        )
        await update.message.reply_text(reply)

        if self._broadcast:
            await self._broadcast({
                "type": "bot_message",
                "role": "system",
                "source": "telegram",
                "text": reply,
            })

    def _build_app(self) -> Application:
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("inbox", self._cmd_inbox))
        app.add_handler(CommandHandler("tasks", self._cmd_tasks))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )
        app.add_handler(MessageHandler(filters.PHOTO, self._on_photo))
        app.add_handler(MessageHandler(filters.Document.ALL, self._on_document))
        app.add_handler(MessageHandler(filters.Sticker.ALL, self._on_sticker))
        return app

    async def run(self) -> None:
        """Start long-polling loop. Blocks until stopped (standalone mode)."""
        self._app = self._build_app()
        self._running = True
        logger.info("Adjutant Telegram Bot starting polling...")
        try:
            async with self._app:
                await self._app.start()
                await self._app.updater.start_polling()
                while self._running:
                    await asyncio.sleep(1)
                await self._app.updater.stop()
                await self._app.stop()
        finally:
            self._running = False
            self._app = None

    async def start_background(self) -> None:
        """Start bot in background (embedded in web server). Non-blocking."""
        self._app = self._build_app()
        self._running = True
        logger.info("Adjutant Telegram Bot starting (background)...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        if self._app and self._running:
            logger.info("Adjutant Telegram Bot stopping...")
            self._running = False
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None

        # Save session and cleanup dispatcher
        if self._session and self._session.messages:
            self._session.save()
        if self._dispatcher:
            await self._dispatcher.cleanup()
            self._dispatcher = None
