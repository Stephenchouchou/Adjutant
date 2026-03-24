"""Subprocess-based AI backend — runs CLI tools (claude, gemini, codex) as subprocesses."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path


AI_BINARIES = {
    "claude": "claude",
    "gemini": "gemini",
    "codex": "codex",
}


class SubprocessBackend:
    """Run an AI CLI tool as a subprocess with streaming output."""

    def __init__(self, ai_tool: str, work_dir: Path) -> None:
        self.ai_tool = ai_tool
        self.work_dir = work_dir
        self._active_procs: list[asyncio.subprocess.Process] = []
        self._cancelled = False

    async def check_available(self) -> bool:
        binary = AI_BINARIES.get(self.ai_tool)
        if not binary:
            return False
        return shutil.which(binary) is not None

    def _build_command(self, prompt: str, model: str | None = None) -> list[str]:
        """Build the command list for the given AI tool."""
        if self.ai_tool == "codex":
            cmd = ["codex", "-C", str(self.work_dir)]
            if model:
                cmd.extend(["-m", model])
            cmd.extend(["exec", prompt])
            return cmd
        elif self.ai_tool == "claude":
            cmd = ["claude", "-p", "--dangerously-skip-permissions"]
            if model:
                cmd.extend(["--model", model])
            cmd.append(prompt)
            return cmd
        elif self.ai_tool == "gemini":
            cmd = ["gemini", "-p", prompt]
            if model:
                cmd.extend(["--model", model])
            return cmd
        else:
            msg = f"Unknown AI tool: {self.ai_tool}"
            raise ValueError(msg)

    def _get_cwd(self) -> Path | None:
        if self.ai_tool == "codex":
            return None
        return self.work_dir

    async def run(self, prompt: str, model: str | None = None) -> AsyncIterator[str]:
        """Launch AI CLI subprocess and yield stdout chunks as they arrive."""
        self._cancelled = False

        cmd = self._build_command(prompt, model=model)
        cwd = self._get_cwd()

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
                    yield f"\n[Error from {self.ai_tool}]: {err_text}\n"
        finally:
            if proc in self._active_procs:
                self._active_procs.remove(proc)

    async def cancel(self) -> None:
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
