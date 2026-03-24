"""Retriever — semantic search over the notebook index."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adjutant.core.embeddings import EmbeddingProvider
from adjutant.core.index import INDEX_DIR, TABLE_NAME


@dataclass
class SearchResult:
    """A single search result with metadata."""

    text: str
    source: str
    heading: str
    score: float


async def retrieve(
    query: str,
    embedder: EmbeddingProvider,
    top_k: int = 5,
    index_dir: Path | None = None,
) -> list[SearchResult]:
    """Embed the query and search the LanceDB index for relevant chunks.

    Returns up to top_k results ranked by similarity.
    """
    import lancedb

    db_path = str(index_dir or INDEX_DIR)
    db = lancedb.connect(db_path)

    if TABLE_NAME not in db.table_names():
        return []

    # Embed the query
    vectors = await embedder.embed([query])
    if not vectors:
        return []
    query_vec = vectors[0]

    table = db.open_table(TABLE_NAME)
    results = (
        table.search(query_vec)
        .limit(top_k)
        .to_pandas()
    )

    search_results = []
    for _, row in results.iterrows():
        search_results.append(
            SearchResult(
                text=row["text"],
                source=row["source"],
                heading=row.get("heading", ""),
                score=float(row.get("_distance", 0.0)),
            )
        )

    return search_results


def format_rag_context(results: list[SearchResult]) -> str:
    """Format search results as a prompt section for injection into chat."""
    if not results:
        return ""

    parts = ["## 相關筆記\n"]
    for r in results:
        header = f"### {r.source}"
        if r.heading:
            header += f" > {r.heading}"
        parts.append(f"{header}\n\n{r.text}\n")

    return "\n".join(parts)
