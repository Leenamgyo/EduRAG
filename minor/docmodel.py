"""DocModel helpers for Minor agent outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, TYPE_CHECKING

from langchain.schema import Document

if TYPE_CHECKING:  # pragma: no cover - import only for type hints
    from minor_search import SearchChunk


@dataclass(slots=True)
class DocModel:
    """Serializable representation of a chunked document."""

    doc_id: str
    page_content: str
    metadata: Dict[str, object]

    @classmethod
    def from_chunk(cls, chunk: "SearchChunk", *, base_query: str) -> "DocModel":
        metadata: Dict[str, object] = {
            "doc_id": chunk.doc_id(),
            "base_query": base_query,
            "search_query": chunk.query,
            "source_label": chunk.source_label,
            "url": chunk.url,
            "title": chunk.title,
            "chunk_index": chunk.chunk_index,
            "content_length": len(chunk.content),
        }
        return cls(doc_id=chunk.doc_id(), page_content=chunk.content, metadata=metadata)

    def to_document(self) -> Document:
        """Convert into a LangChain Document instance."""

        return Document(page_content=self.page_content, metadata=self.metadata)


def build_docmodels(chunks: Iterable["SearchChunk"], *, base_query: str) -> List[DocModel]:
    """Build DocModel instances from search chunks."""

    return [DocModel.from_chunk(chunk, base_query=base_query) for chunk in chunks]


__all__ = ["DocModel", "build_docmodels"]
