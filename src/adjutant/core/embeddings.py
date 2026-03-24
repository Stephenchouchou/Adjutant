"""Embedding provider abstraction — Ollama or local sentence-transformers."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol for text embedding providers."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per text."""
        ...

    def dimension(self) -> int:
        """Return the embedding vector dimension."""
        ...


class OllamaEmbedder:
    """Embedding via Ollama's /api/embed endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dim: int | None = None

    def dimension(self) -> int:
        # nomic-embed-text = 768, mxbai-embed-large = 1024
        if self._dim is not None:
            return self._dim
        defaults = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "all-minilm": 384,
        }
        return defaults.get(self.model, 768)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient(base_url=self.base_url, timeout=120) as client:
            resp = await client.post(
                "/api/embed",
                json={"model": self.model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and self._dim is None:
                self._dim = len(embeddings[0])
            return embeddings


class LocalEmbedder:
    """Embedding via sentence-transformers (local, no server needed)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                msg = (
                    "sentence-transformers is required for local embeddings. "
                    "Install with: pip install sentence-transformers"
                )
                raise ImportError(msg) from e
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def dimension(self) -> int:
        defaults = {
            "all-MiniLM-L6-v2": 384,
            "all-mpnet-base-v2": 768,
        }
        if self.model_name in defaults:
            return defaults[self.model_name]
        model = self._get_model()
        return model.get_sentence_embedding_dimension()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        model = self._get_model()
        # sentence-transformers is sync; run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(None, model.encode, texts)
        return [v.tolist() for v in vectors]


async def _ollama_embed_available(base_url: str, model: str) -> bool:
    """Check if Ollama has the embedding model available."""
    try:
        import httpx

        async with httpx.AsyncClient(base_url=base_url, timeout=5) as client:
            resp = await client.post(
                "/api/embed",
                json={"model": model, "input": ["test"]},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def get_embedding_provider(
    ollama_base_url: str = "http://localhost:11434",
    ollama_model: str = "nomic-embed-text",
) -> OllamaEmbedder | LocalEmbedder:
    """Get the best available embedding provider.

    Prefers Ollama (keeps everything local and fast) and falls back to
    sentence-transformers if Ollama is unavailable.
    """
    if await _ollama_embed_available(ollama_base_url, ollama_model):
        return OllamaEmbedder(base_url=ollama_base_url, model=ollama_model)
    return LocalEmbedder()
