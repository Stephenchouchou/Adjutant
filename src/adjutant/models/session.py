"""Session and message models for Adjutant chat."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from adjutant.config import SESSIONS_DIR


class Message(BaseModel):
    """A single message in the conversation."""

    role: str = Field(description="'user' or 'adjutant'")
    content: str = Field(default="")
    timestamp: datetime = Field(default_factory=datetime.now)


class Session(BaseModel):
    """An adjutant chat session."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    messages: list[Message] = Field(default_factory=list)
    status: str = Field(default="active")

    def add_message(self, role: str, content: str) -> Message:
        """Add a message to the session."""
        msg = Message(role=role, content=content)
        self.messages.append(msg)
        return msg

    def save(self) -> Path:
        """Persist session to ~/.adjutant/sessions/."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = SESSIONS_DIR / f"{self.id}.json"
        path.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path

    @classmethod
    def load(cls, session_id: str) -> Session | None:
        """Load a session by ID."""
        path = SESSIONS_DIR / f"{session_id}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    @classmethod
    def list_sessions(cls) -> list[Session]:
        """List all saved sessions, newest first."""
        if not SESSIONS_DIR.is_dir():
            return []
        sessions = []
        for path in SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(cls.model_validate(data))
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    @classmethod
    def recent_sessions(cls, minutes: int = 30) -> list[Session]:
        """Return sessions created within the last N minutes, newest first."""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [s for s in cls.list_sessions() if s.created_at >= cutoff]
