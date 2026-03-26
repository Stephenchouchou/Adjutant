"""Adjutant chat — persona-aware conversational interface with memory."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path

logger = logging.getLogger(__name__)

# Pattern matching transient API errors worth retrying
_TRANSIENT_ERROR_RE = re.compile(
    r"\[Error from \w+\]:.*(?:500|502|503|529|overloaded|internal server error)",
    re.IGNORECASE,
)

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
    rag_context: str | None = None,
    memory_context: str | None = None,
) -> str:
    """Build a full prompt including persona, memory, RAG, history, and optional file context.

    Args:
        memory_context: Pre-fetched memory text (from vector store or flat file).
            If None, falls back to loading flat memory.md directly.
    """
    parts: list[str] = [get_persona()]

    # Inject memory — prefer pre-fetched vector memory, fallback to flat file
    if memory_context:
        parts.append(f"\n{memory_context}\n")
    else:
        memory = load_memory()
        if memory:
            parts.append(f"\n## 副官記憶\n\n{memory}\n")

    # Inject RAG context (semantically relevant notebook chunks)
    if rag_context:
        parts.append(f"\n{rag_context}\n")

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
    retries: int = 3,
) -> str:
    """Run a single chat and collect the full response.

    Retries automatically on transient API errors (500, 502, 503, overloaded).
    """
    last_result = ""
    for attempt in range(1, retries + 1):
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

        last_result = "".join(parts)

        if _TRANSIENT_ERROR_RE.search(last_result):
            if attempt < retries:
                delay = 2 ** attempt
                logger.warning(
                    "Transient API error (attempt %d/%d), retrying in %ds...",
                    attempt, retries, delay,
                )
                await asyncio.sleep(delay)
                continue
            logger.error("Transient API error persisted after %d attempts.", retries)

        return last_result

    return last_result
