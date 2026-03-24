"""Vector memory store — contextual memory retrieval via LanceDB."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from adjutant.config import CONFIG_DIR, MEMORY_PATH, load_memory
from adjutant.core.embeddings import EmbeddingProvider
from adjutant.core.index import INDEX_DIR

MEMORY_TABLE = "memories"

CATEGORIES = ("fact", "preference", "instruction", "context")


@dataclass
class MemoryEntry:
    """A single memory entry."""

    id: str
    content: str
    category: str  # fact, preference, instruction, context
    created: str  # ISO datetime
    last_accessed: str  # ISO datetime
    access_count: int
    source: str  # "user", "ai-extracted", "imported"


class MemoryStore:
    """Vector-based memory store backed by LanceDB.

    Shares the same LanceDB database directory as the RAG index
    but uses a separate table ('memories').
    """

    def __init__(self, embedder: EmbeddingProvider, index_dir: Path | None = None) -> None:
        self.embedder = embedder
        self._db_path = str(index_dir or INDEX_DIR)
        self._db = None

    def _get_db(self):
        import lancedb

        Path(self._db_path).mkdir(parents=True, exist_ok=True)
        if self._db is None:
            self._db = lancedb.connect(self._db_path)
        return self._db

    def _table_exists(self) -> bool:
        db = self._get_db()
        return MEMORY_TABLE in db.table_names()

    async def _ensure_table(self):
        """Create the memories table if it doesn't exist."""
        import pyarrow as pa

        db = self._get_db()
        if MEMORY_TABLE not in db.table_names():
            dim = self.embedder.dimension()
            schema = pa.schema(
                [
                    pa.field("id", pa.utf8()),
                    pa.field("content", pa.utf8()),
                    pa.field("category", pa.utf8()),
                    pa.field("created", pa.utf8()),
                    pa.field("last_accessed", pa.utf8()),
                    pa.field("access_count", pa.int32()),
                    pa.field("source", pa.utf8()),
                    pa.field("vector", pa.list_(pa.float32(), dim)),
                ]
            )
            db.create_table(MEMORY_TABLE, schema=schema)

    async def add(
        self,
        content: str,
        category: str = "fact",
        source: str = "user",
    ) -> MemoryEntry:
        """Add a new memory entry."""
        await self._ensure_table()

        now = datetime.now().isoformat()
        entry = MemoryEntry(
            id=uuid.uuid4().hex[:12],
            content=content,
            category=category,
            created=now,
            last_accessed=now,
            access_count=0,
            source=source,
        )

        vectors = await self.embedder.embed([content])
        if not vectors:
            msg = "Failed to embed memory content"
            raise RuntimeError(msg)

        db = self._get_db()
        table = db.open_table(MEMORY_TABLE)
        table.add(
            [
                {
                    "id": entry.id,
                    "content": entry.content,
                    "category": entry.category,
                    "created": entry.created,
                    "last_accessed": entry.last_accessed,
                    "access_count": entry.access_count,
                    "source": entry.source,
                    "vector": vectors[0],
                }
            ]
        )

        return entry

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Retrieve memories most relevant to the query."""
        if not self._table_exists():
            return []

        vectors = await self.embedder.embed([query])
        if not vectors:
            return []

        db = self._get_db()
        table = db.open_table(MEMORY_TABLE)
        results = table.search(vectors[0]).limit(top_k).to_pandas()

        entries = []
        for _, row in results.iterrows():
            entries.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    category=row["category"],
                    created=row["created"],
                    last_accessed=row["last_accessed"],
                    access_count=int(row["access_count"]),
                    source=row["source"],
                )
            )
        return entries

    def list_all(self, category: str | None = None) -> list[MemoryEntry]:
        """List all memories, optionally filtered by category."""
        if not self._table_exists():
            return []

        db = self._get_db()
        table = db.open_table(MEMORY_TABLE)
        df = table.to_pandas()

        if category:
            df = df[df["category"] == category]

        entries = []
        for _, row in df.iterrows():
            entries.append(
                MemoryEntry(
                    id=row["id"],
                    content=row["content"],
                    category=row["category"],
                    created=row["created"],
                    last_accessed=row["last_accessed"],
                    access_count=int(row["access_count"]),
                    source=row["source"],
                )
            )
        return entries

    def forget(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if found and deleted."""
        if not self._table_exists():
            return False

        db = self._get_db()
        table = db.open_table(MEMORY_TABLE)
        df = table.to_pandas()
        before = len(df)
        df = df[df["id"] != memory_id]

        if len(df) == before:
            return False

        # Rebuild table without the deleted entry
        import pyarrow as pa

        dim = self.embedder.dimension()
        schema = pa.schema(
            [
                pa.field("id", pa.utf8()),
                pa.field("content", pa.utf8()),
                pa.field("category", pa.utf8()),
                pa.field("created", pa.utf8()),
                pa.field("last_accessed", pa.utf8()),
                pa.field("access_count", pa.int32()),
                pa.field("source", pa.utf8()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
            ]
        )

        rows = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "category": row["category"],
                    "created": row["created"],
                    "last_accessed": row["last_accessed"],
                    "access_count": int(row["access_count"]),
                    "source": row["source"],
                    "vector": row["vector"].tolist()
                    if hasattr(row["vector"], "tolist")
                    else list(row["vector"]),
                }
            )

        db.drop_table(MEMORY_TABLE)
        if rows:
            db.create_table(MEMORY_TABLE, data=rows, schema=schema)
        else:
            db.create_table(MEMORY_TABLE, schema=schema)

        return True

    async def import_from_file(self, path: Path | None = None) -> int:
        """Import memories from a plain-text memory.md file.

        Splits by non-empty lines or bullet points. Returns count of imported entries.
        """
        path = path or MEMORY_PATH
        if not path.is_file():
            return 0

        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return 0

        # Split into individual memory items
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip markdown bullet prefixes
            if line.startswith(("- ", "* ", "• ")):
                line = line[2:].strip()
            if line.startswith(("#",)):
                continue  # Skip headings
            if len(line) > 10:  # Skip trivially short lines
                lines.append(line)

        count = 0
        for line in lines:
            await self.add(content=line, category="fact", source="imported")
            count += 1

        return count

    def count(self) -> int:
        """Return the total number of memories."""
        if not self._table_exists():
            return 0
        db = self._get_db()
        table = db.open_table(MEMORY_TABLE)
        return table.count_rows()


def format_memory_context(entries: list[MemoryEntry]) -> str:
    """Format memory entries for prompt injection."""
    if not entries:
        return ""

    lines = ["## 副官記憶\n"]
    for e in entries:
        lines.append(f"- {e.content}")

    return "\n".join(lines)


async def get_memory_context(
    query: str,
    embedder: EmbeddingProvider,
    top_k: int = 5,
) -> str:
    """Convenience: retrieve relevant memories and format for prompt injection.

    Falls back to flat memory.md if the vector store is empty.
    """
    store = MemoryStore(embedder)

    if store.count() > 0:
        entries = await store.search(query, top_k=top_k)
        if entries:
            return format_memory_context(entries)

    # Fallback to flat file
    flat = load_memory()
    if flat:
        return f"## 副官記憶\n\n{flat}"

    return ""
