"""AI backend abstraction — protocol for subprocess and HTTP-based AI providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable


@runtime_checkable
class AIBackend(Protocol):
    """Protocol for AI backends (subprocess CLI tools, HTTP APIs, etc.)."""

    async def check_available(self) -> bool:
        """Return True if the backend is reachable / installed."""
        ...

    async def run(self, prompt: str, model: str | None = None) -> AsyncIterator[str]:
        """Stream a response from the AI. Yields text chunks."""
        ...

    async def cancel(self) -> None:
        """Cancel the current streaming response."""
        ...
