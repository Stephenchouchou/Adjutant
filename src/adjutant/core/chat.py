"""Adjutant chat — persona-aware conversational interface with memory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from adjutant.config import load_memory, load_persona
from adjutant.core.dispatcher import Dispatcher
from adjutant.models.session import Message, Session
from adjutant.prompts import load_default_persona, match_directives

# Keep backward compatibility — code that imports these names still works
DEFAULT_PERSONA = load_default_persona()
ADJUTANT_PERSONA = DEFAULT_PERSONA


def get_persona() -> str:
    """Get persona: user-customized (~/.adjutant/persona.md) or built-in default."""
    custom = load_persona()
    return custom if custom else load_default_persona()


def build_chat_prompt(
    user_prompt: str,
    session: Session,
    file_context: str | None = None,
) -> str:
    """Build a full prompt including persona, memory, history, and optional file context."""
    parts: list[str] = [get_persona()]

    # Inject persistent memory
    memory = load_memory()
    if memory:
        parts.append(f"\n## 副官記憶\n\n{memory}\n")

    # Add conversation history (last 20 messages to keep prompt manageable)
    recent = session.messages[-20:]
    if recent:
        parts.append("\n## 先前對話紀錄\n")
        for msg in recent:
            role_label = "User" if msg.role == "user" else "Adjutant"
            content = msg.content
            if len(content) > 3000:
                content = content[:3000] + "\n... (truncated)"
            parts.append(f"[{role_label}]: {content}\n")

    # Add file context if provided
    if file_context:
        parts.append(f"\n## 參考檔案內容\n\n{file_context}\n")

    # Directive triggers — scan user prompt for registered keywords
    for directive in match_directives(user_prompt):
        parts.append(f"\n{directive.body}\n")

    parts.append(f"\n## 當前請求\n\n[User]: {user_prompt}")

    return "\n".join(parts)


async def chat_stream(
    dispatcher: Dispatcher,
    prompt: str,
    work_dir: Path,
    ai_tool: str = "claude",
    model: str | None = None,
) -> AsyncIterator[str]:
    """Stream a chat response from the AI."""
    async for chunk in dispatcher.run(ai_tool, prompt, work_dir, model=model):
        yield chunk


async def chat_once(
    dispatcher: Dispatcher,
    prompt: str,
    work_dir: Path,
    ai_tool: str = "claude",
    model: str | None = None,
    timeout: float = 120,
) -> str:
    """Run a single chat and collect the full response."""
    parts: list[str] = []
    try:
        async def _collect():
            async for chunk in dispatcher.run(ai_tool, prompt, work_dir, model=model):
                parts.append(chunk)
        await asyncio.wait_for(_collect(), timeout=timeout)
    except asyncio.TimeoutError:
        if parts:
            return "".join(parts) + "\n\n(timeout)"
        return "(response timed out)"
    return "".join(parts)
