"""AI CLI dispatcher — streaming subprocess execution.

Simplified from CrossVal's dispatcher for single-AI mode.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path


class AINotFoundError(Exception):
    """Raised when the requested AI CLI tool is not installed."""


AI_BINARIES = {
    "claude": "claude",
    "gemini": "gemini",
    "codex": "codex",
}


class Dispatcher:
    """Run AI CLI subprocess with streaming output."""

    def __init__(self) -> None:
        self._active_procs: list[asyncio.subprocess.Process] = []
        self._cancelled = False

    async def cancel(self) -> None:
        """Cancel the current streaming response."""
        self._cancelled = True
        for proc in list(self._active_procs):
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except (TimeoutError, ProcessLookupError):
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
        self._active_procs.clear()

    async def cleanup(self) -> None:
        """Terminate and wait for all active subprocesses."""
        await self.cancel()

    @staticmethod
    def build_command(
        ai_tool: str, prompt: str, work_dir: Path, model: str | None = None
    ) -> list[str]:
        """Build the command list for the given AI tool."""
        if ai_tool == "codex":
            cmd = ["codex", "-C", str(work_dir)]
            if model:
                cmd.extend(["-m", model])
            cmd.extend(["exec", prompt])
            return cmd
        elif ai_tool == "claude":
            cmd = ["claude", "-p", "--dangerously-skip-permissions"]
            if model:
                cmd.extend(["--model", model])
            cmd.append(prompt)
            return cmd
        elif ai_tool == "gemini":
            cmd = ["gemini", "-p", prompt]
            if model:
                cmd.extend(["--model", model])
            return cmd
        else:
            msg = f"Unknown AI tool: {ai_tool}"
            raise ValueError(msg)

    @staticmethod
    def get_cwd(ai_tool: str, work_dir: Path) -> Path | None:
        """Return the cwd to use when spawning the subprocess."""
        if ai_tool == "codex":
            return None
        return work_dir

    @staticmethod
    def check_available(ai_tool: str) -> bool:
        """Check if the AI CLI binary is installed."""
        binary = AI_BINARIES.get(ai_tool)
        if not binary:
            return False
        return shutil.which(binary) is not None

    async def run(
        self, ai_tool: str, prompt: str, work_dir: Path, model: str | None = None
    ) -> AsyncIterator[str]:
        """Launch AI CLI subprocess and yield stdout lines as they arrive."""
        self._cancelled = False

        if not self.check_available(ai_tool):
            binary = AI_BINARIES.get(ai_tool, ai_tool)
            raise AINotFoundError(f"'{binary}' not found in PATH. Install it first.")

        cmd = self.build_command(ai_tool, prompt, work_dir, model=model)
        cwd = self.get_cwd(ai_tool, work_dir)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        self._active_procs.append(proc)

        assert proc.stdout is not None  # noqa: S101

        try:
            assert proc.stderr is not None  # noqa: S101
            stderr_task = asyncio.create_task(proc.stderr.read())

            async for raw_line in proc.stdout:
                if self._cancelled:
                    break
                line = raw_line.decode("utf-8", errors="replace")
                yield line

            stderr_data = await stderr_task
            await proc.wait()

            if not self._cancelled and proc.returncode and proc.returncode != 0:
                err_text = stderr_data.decode("utf-8", errors="replace").strip()
                if err_text:
                    yield f"\n[Error from {ai_tool}]: {err_text}\n"
        finally:
            if proc in self._active_procs:
                self._active_procs.remove(proc)

