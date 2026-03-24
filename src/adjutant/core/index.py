"""Notebook index — markdown chunking, embedding, and LanceDB storage."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from adjutant.config import CONFIG_DIR
from adjutant.core.embeddings import EmbeddingProvider

INDEX_DIR = CONFIG_DIR / "index"
META_PATH = INDEX_DIR / "_meta.json"
TABLE_NAME = "notebook_chunks"

# Chunking parameters
MAX_CHUNK_CHARS = 2000  # ~500 tokens
MIN_CHUNK_CHARS = 50


@dataclass
class Chunk:
    """A chunk of text from a notebook markdown file."""

    text: str
    source: str  # relative path from notebook_root
    heading: str  # nearest heading above
    chunk_idx: int
    modified: str  # ISO datetime


@dataclass
class IndexMeta:
    """Tracks file modification times for incremental indexing."""

    file_mtimes: dict[str, float] = field(default_factory=dict)
    last_built: str = ""
    chunk_count: int = 0
    file_count: int = 0

    def save(self) -> None:
        META_PATH.parent.mkdir(parents=True, exist_ok=True)
        META_PATH.write_text(
            json.dumps(
                {
                    "file_mtimes": self.file_mtimes,
                    "last_built": self.last_built,
                    "chunk_count": self.chunk_count,
                    "file_count": self.file_count,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls) -> IndexMeta:
        if not META_PATH.is_file():
            return cls()
        try:
            data = json.loads(META_PATH.read_text(encoding="utf-8"))
            return cls(
                file_mtimes=data.get("file_mtimes", {}),
                last_built=data.get("last_built", ""),
                chunk_count=data.get("chunk_count", 0),
                file_count=data.get("file_count", 0),
            )
        except (json.JSONDecodeError, OSError):
            return cls()


# ---------------------------------------------------------------------------
# Markdown chunker
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)


def chunk_markdown(text: str, source: str, modified: str) -> list[Chunk]:
    """Split markdown into chunks by headings, respecting MAX_CHUNK_CHARS."""
    sections: list[tuple[str, str]] = []  # (heading, body)

    # Find all headings and their positions
    headings = list(_HEADING_RE.finditer(text))

    if not headings:
        # No headings — treat entire file as one section
        sections.append(("", text.strip()))
    else:
        # Text before first heading
        pre = text[: headings[0].start()].strip()
        if pre:
            sections.append(("", pre))

        for i, match in enumerate(headings):
            heading = match.group(2).strip()
            start = match.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((heading, body))

    # Split oversized sections into sub-chunks
    chunks: list[Chunk] = []
    idx = 0
    for heading, body in sections:
        if len(body) <= MAX_CHUNK_CHARS:
            if len(body) >= MIN_CHUNK_CHARS:
                chunks.append(
                    Chunk(
                        text=body,
                        source=source,
                        heading=heading,
                        chunk_idx=idx,
                        modified=modified,
                    )
                )
                idx += 1
        else:
            # Split by paragraphs, then accumulate
            paragraphs = re.split(r"\n\s*\n", body)
            buffer = ""
            for para in paragraphs:
                if len(buffer) + len(para) + 2 > MAX_CHUNK_CHARS and buffer:
                    chunks.append(
                        Chunk(
                            text=buffer.strip(),
                            source=source,
                            heading=heading,
                            chunk_idx=idx,
                            modified=modified,
                        )
                    )
                    idx += 1
                    buffer = para
                else:
                    buffer = f"{buffer}\n\n{para}" if buffer else para

            if buffer.strip() and len(buffer.strip()) >= MIN_CHUNK_CHARS:
                chunks.append(
                    Chunk(
                        text=buffer.strip(),
                        source=source,
                        heading=heading,
                        chunk_idx=idx,
                        modified=modified,
                    )
                )
                idx += 1

    return chunks


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------


def _scan_md_files(notebook_root: Path) -> list[Path]:
    """Find all .md files under notebook_root (skip hidden dirs)."""
    files = []
    for path in sorted(notebook_root.rglob("*.md")):
        # Skip hidden directories and files
        parts = path.relative_to(notebook_root).parts
        if any(p.startswith(".") for p in parts):
            continue
        files.append(path)
    return files


def _get_lancedb(index_dir: Path | None = None):
    """Get a LanceDB connection."""
    import lancedb

    db_path = str(index_dir or INDEX_DIR)
    Path(db_path).mkdir(parents=True, exist_ok=True)
    return lancedb.connect(db_path)


async def build_index(
    notebook_root: Path,
    embedder: EmbeddingProvider,
    *,
    incremental: bool = True,
) -> IndexMeta:
    """Build or update the notebook vector index.

    Args:
        notebook_root: Root directory to scan for .md files.
        embedder: Embedding provider to vectorize chunks.
        incremental: If True, only re-index changed files.

    Returns:
        Updated IndexMeta with stats.
    """
    import pyarrow as pa

    meta = IndexMeta.load() if incremental else IndexMeta()
    md_files = _scan_md_files(notebook_root)

    # Determine which files need (re-)indexing
    to_index: list[Path] = []
    current_mtimes: dict[str, float] = {}

    for path in md_files:
        rel = str(path.relative_to(notebook_root))
        mtime = path.stat().st_mtime
        current_mtimes[rel] = mtime

        if not incremental:
            to_index.append(path)
        elif rel not in meta.file_mtimes or meta.file_mtimes[rel] < mtime:
            to_index.append(path)

    # Detect deleted files
    deleted = set(meta.file_mtimes.keys()) - set(current_mtimes.keys())

    if not to_index and not deleted:
        # Nothing changed
        return meta

    # Chunk changed files
    all_chunks: list[Chunk] = []
    for path in to_index:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = str(path.relative_to(notebook_root))
        modified = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        chunks = chunk_markdown(text, source=rel, modified=modified)
        all_chunks.append(chunks) if False else all_chunks.extend(chunks)

    # Embed all new chunks
    vectors: list[list[float]] = []
    if all_chunks:
        batch_size = 64
        for i in range(0, len(all_chunks), batch_size):
            batch_texts = [c.text for c in all_chunks[i : i + batch_size]]
            batch_vectors = await embedder.embed(batch_texts)
            vectors.extend(batch_vectors)

    # Build LanceDB table
    db = _get_lancedb()
    dim = embedder.dimension()

    # Sources that need to be replaced (changed or deleted)
    sources_to_remove = {str(p.relative_to(notebook_root)) for p in to_index} | deleted

    schema = pa.schema(
        [
            pa.field("text", pa.utf8()),
            pa.field("source", pa.utf8()),
            pa.field("heading", pa.utf8()),
            pa.field("chunk_idx", pa.int32()),
            pa.field("modified", pa.utf8()),
            pa.field("vector", pa.list_(pa.float32(), dim)),
        ]
    )

    # Load existing data (if incremental)
    existing_rows = []
    if incremental and TABLE_NAME in db.table_names():
        table = db.open_table(TABLE_NAME)
        df = table.to_pandas()
        for _, row in df.iterrows():
            if row["source"] not in sources_to_remove:
                existing_rows.append(
                    {
                        "text": row["text"],
                        "source": row["source"],
                        "heading": row["heading"],
                        "chunk_idx": int(row["chunk_idx"]),
                        "modified": row["modified"],
                        "vector": row["vector"].tolist()
                        if hasattr(row["vector"], "tolist")
                        else list(row["vector"]),
                    }
                )

    # Merge existing + new
    new_rows = []
    for chunk, vec in zip(all_chunks, vectors):
        new_rows.append(
            {
                "text": chunk.text,
                "source": chunk.source,
                "heading": chunk.heading,
                "chunk_idx": chunk.chunk_idx,
                "modified": chunk.modified,
                "vector": vec,
            }
        )

    all_rows = existing_rows + new_rows

    if all_rows:
        # Drop and recreate table with merged data
        if TABLE_NAME in db.table_names():
            db.drop_table(TABLE_NAME)
        db.create_table(TABLE_NAME, data=all_rows, schema=schema)

    # Update metadata
    meta.file_mtimes = current_mtimes
    meta.last_built = datetime.now().isoformat()
    meta.chunk_count = len(all_rows)
    meta.file_count = len(md_files)
    meta.save()

    return meta


def get_index_status() -> IndexMeta:
    """Get the current index metadata (without modifying anything)."""
    return IndexMeta.load()
