"""Ollama HTTP backend — streams responses from a local Ollama server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator


DEFAULT_OLLAMA_URL = "http://localhost:11434"


def _import_httpx():
    """Lazy import httpx — only needed when ollama backend is actually used."""
    try:
        import httpx
        return httpx
    except ImportError as e:
        msg = "httpx is required for Ollama support. Install with: pip install httpx"
        raise ImportError(msg) from e


class OllamaBackend:
    """HTTP streaming backend for Ollama's /api/generate endpoint."""

    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = None  # httpx.AsyncClient, created lazily
        self._cancelled = False

    def _get_client(self):
        httpx = _import_httpx()
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=300)
        return self._client

    async def check_available(self) -> bool:
        """Check if the Ollama server is reachable."""
        httpx = _import_httpx()
        try:
            client = self._get_client()
            resp = await client.get("/api/tags", timeout=5)
            return resp.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            return False

    async def list_models(self) -> list[str]:
        """Query Ollama for installed models."""
        httpx = _import_httpx()
        try:
            client = self._get_client()
            resp = await client.get("/api/tags", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except (httpx.HTTPError, KeyError, TypeError):
            return []

    async def run(self, prompt: str, model: str | None = None) -> AsyncIterator[str]:
        """Stream a response from Ollama's generate API."""
        httpx = _import_httpx()
        self._cancelled = False
        client = self._get_client()

        payload = {
            "model": model or "llama3.1",
            "prompt": prompt,
            "stream": True,
        }

        try:
            async with client.stream("POST", "/api/generate", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if self._cancelled:
                        break
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
        except httpx.HTTPStatusError as e:
            yield f"\n[Error from ollama]: HTTP {e.response.status_code} — {e.response.text}\n"
        except httpx.ConnectError:
            yield "\n[Error from ollama]: Cannot connect to Ollama server. Is it running?\n"

    async def cancel(self) -> None:
        self._cancelled = True
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def close(self) -> None:
        """Clean up the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
