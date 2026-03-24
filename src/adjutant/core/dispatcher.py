"""AI dispatcher — routes requests to the appropriate backend.

Supports subprocess-based CLI tools (claude, gemini, codex) and HTTP backends (ollama).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from adjutant.core.backends.subprocess_backend import AI_BINARIES, SubprocessBackend

# Lazy-loaded to avoid hard dependency on httpx at import time
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class AINotFoundError(Exception):
    """Raised when the requested AI backend is not available."""


class Dispatcher:
    """Route AI requests to the appropriate backend with streaming output."""

    def __init__(self, ollama_base_url: str = DEFAULT_OLLAMA_URL) -> None:
        self._ollama_base_url = ollama_base_url
        self._active_backend: Any = None

    def _get_backend(self, ai_tool: str, work_dir: Path):
        if ai_tool == "ollama":
            from adjutant.core.backends.ollama import OllamaBackend

            backend = OllamaBackend(self._ollama_base_url)
        elif ai_tool in AI_BINARIES:
            backend = SubprocessBackend(ai_tool, work_dir)
        else:
            msg = f"Unknown AI tool: {ai_tool}"
            raise ValueError(msg)
        self._active_backend = backend
        return backend

    async def cancel(self) -> None:
        """Cancel the current streaming response."""
        if self._active_backend:
            await self._active_backend.cancel()

    async def cleanup(self) -> None:
        """Terminate and clean up all active backends."""
        await self.cancel()
        if hasattr(self._active_backend, "close"):
            await self._active_backend.close()
        self._active_backend = None

    @staticmethod
    def check_available(ai_tool: str) -> bool:
        """Check if an AI tool is available (sync check for subprocess tools)."""
        import shutil

        if ai_tool == "ollama":
            # For ollama, a sync availability check isn't meaningful.
            # Use async check_available() on the backend instead.
            return True
        binary = AI_BINARIES.get(ai_tool)
        if not binary:
            return False
        return shutil.which(binary) is not None

    async def run(
        self, ai_tool: str, prompt: str, work_dir: Path, model: str | None = None
    ) -> AsyncIterator[str]:
        """Route to the appropriate backend and stream the response."""
        backend = self._get_backend(ai_tool, work_dir)

        if not await backend.check_available():
            if ai_tool == "ollama":
                raise AINotFoundError(
                    f"Cannot connect to Ollama at {self._ollama_base_url}. Is it running?"
                )
            binary = AI_BINARIES.get(ai_tool, ai_tool)
            raise AINotFoundError(f"'{binary}' not found in PATH. Install it first.")

        async for chunk in backend.run(prompt, model=model):
            yield chunk
