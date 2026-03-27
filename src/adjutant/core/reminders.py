"""Reminder system — model, persistent store, and asyncio scheduler."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from adjutant.config import REMINDERS_PATH

logger = logging.getLogger(__name__)

SendFn = Callable[[int, str], Awaitable[None]]


class Reminder(BaseModel):
    """A single scheduled reminder."""

    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    text: str
    fire_at: datetime
    chat_ids: list[int] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(default="web")
    fired: bool = False


class ReminderStore:
    """JSON-file backed persistence for reminders."""

    def __init__(self, path: Path = REMINDERS_PATH):
        self._path = path
        self._reminders: list[Reminder] = []
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            self._reminders = []
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._reminders = [Reminder.model_validate(r) for r in data]
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to load reminders: %s", e)
            self._reminders = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                [r.model_dump(mode="json") for r in self._reminders],
                indent=2,
                ensure_ascii=False,
                default=str,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, self._path)

    def add(
        self,
        text: str,
        fire_at: datetime,
        chat_ids: list[int],
        source: str = "web",
    ) -> Reminder:
        r = Reminder(text=text, fire_at=fire_at, chat_ids=chat_ids, source=source)
        self._reminders.append(r)
        self._save()
        return r

    def remove(self, reminder_id: str) -> bool:
        before = len(self._reminders)
        self._reminders = [r for r in self._reminders if r.id != reminder_id]
        if len(self._reminders) < before:
            self._save()
            return True
        return False

    def mark_fired(self, reminder_id: str) -> None:
        for r in self._reminders:
            if r.id == reminder_id:
                r.fired = True
                break
        self._save()

    def list_pending(self) -> list[Reminder]:
        return [r for r in self._reminders if not r.fired]

    def list_all(self) -> list[Reminder]:
        return list(self._reminders)

    def cleanup_old(self, keep_days: int = 7) -> int:
        """Remove fired reminders older than keep_days."""
        now = datetime.now(timezone.utc)
        before = len(self._reminders)
        self._reminders = [
            r
            for r in self._reminders
            if not r.fired
            or (now - r.fire_at).days < keep_days
        ]
        removed = before - len(self._reminders)
        if removed:
            self._save()
        return removed


class ReminderScheduler:
    """Asyncio-based scheduler that fires reminders and calls send_fn."""

    def __init__(self, store: ReminderStore, send_fn: SendFn):
        self._store = store
        self._send_fn = send_fn
        self._tasks: dict[str, asyncio.Task] = {}
        self._queue: list[Reminder] = []
        self._running = False

    async def start(self) -> None:
        """Load pending reminders and schedule them."""
        self._running = True
        self._store.cleanup_old()
        now = datetime.now(timezone.utc)
        for r in self._store.list_pending():
            fire_at = _ensure_utc(r.fire_at)
            if fire_at <= now:
                self._queue.append(r)
            else:
                self._schedule(r)
        logger.info(
            "Reminder scheduler started: %d scheduled, %d queued",
            len(self._tasks),
            len(self._queue),
        )

    def _schedule(self, reminder: Reminder) -> None:
        task = asyncio.create_task(self._wait_and_fire(reminder))
        self._tasks[reminder.id] = task

    async def _wait_and_fire(self, reminder: Reminder) -> None:
        now = datetime.now(timezone.utc)
        fire_at = _ensure_utc(reminder.fire_at)
        delay = max(0, (fire_at - now).total_seconds())
        await asyncio.sleep(delay)
        await self._fire(reminder)

    async def _fire(self, reminder: Reminder) -> None:
        self._tasks.pop(reminder.id, None)
        msg = f"\u23f0 {reminder.text}"
        success = False
        for chat_id in reminder.chat_ids:
            try:
                await self._send_fn(chat_id, msg)
                success = True
            except Exception as e:
                logger.warning("Failed to send reminder %s to %s: %s", reminder.id, chat_id, e)
        if success:
            self._store.mark_fired(reminder.id)
        else:
            self._queue.append(reminder)
            logger.info("Reminder %s queued (bot offline)", reminder.id)

    async def add(
        self,
        text: str,
        fire_at: datetime,
        chat_ids: list[int],
        source: str = "web",
    ) -> Reminder:
        reminder = self._store.add(text, fire_at, chat_ids, source)
        now = datetime.now(timezone.utc)
        fire_at_utc = _ensure_utc(fire_at)
        if fire_at_utc <= now:
            await self._fire(reminder)
        else:
            self._schedule(reminder)
        return reminder

    def cancel(self, reminder_id: str) -> bool:
        task = self._tasks.pop(reminder_id, None)
        if task:
            task.cancel()
        # Also remove from queue
        self._queue = [r for r in self._queue if r.id != reminder_id]
        return self._store.remove(reminder_id)

    async def flush_queue(self) -> int:
        """Send all queued reminders. Call when bot comes online."""
        sent = 0
        remaining = []
        for reminder in self._queue:
            try:
                for chat_id in reminder.chat_ids:
                    await self._send_fn(chat_id, f"\u23f0 {reminder.text}")
                self._store.mark_fired(reminder.id)
                sent += 1
            except Exception:
                remaining.append(reminder)
        self._queue = remaining
        if sent:
            logger.info("Flushed %d queued reminders", sent)
        return sent

    def list_pending(self) -> list[Reminder]:
        return self._store.list_pending()

    def list_all(self) -> list[Reminder]:
        return self._store.list_all()

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()


def _ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is UTC-aware."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
