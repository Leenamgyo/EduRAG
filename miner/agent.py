"""Gemini agent workflow for Miner.

This module orchestrates a Gemini-powered agent that expands a user query,
collects supporting documents, chunks them, embeds the chunks, and stores the
vectors inside Qdrant for later retrieval.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from search import AgentChunkResult, SearchChunk, collect_agent_chunks
from vector_db import VectorCollectionConfig, create_client, ensure_collection


DEFAULT_EMBEDDING_MODEL = os.getenv(
    "MINER_AGENT_EMBEDDING_MODEL",
    "models/text-embedding-004",
)


class AgentConfigurationError(RuntimeError):
    """Raised when the agent cannot proceed due to configuration issues."""


@dataclass(slots=True)
class AgentRunSummary:
    """Summary of an agent ingestion run."""

    base_query: str
    related_queries: List[str]
    stored_chunks: int
    collection: str
    failures: List[str]

    def to_markdown(self) -> str:
        """Render the summary in Markdown format for CLI output."""

        related = (
            "\n".join(f"- {query}" for query in self.related_queries)
            if self.related_queries
            else "- (none)"
        )
        failures = (
            "\n".join(f"- {item}" for item in self.failures)
            if self.failures
            else "- (none)"
        )
        return (
            f"### Gemini Agent 결과\n"
            f"- 기준 질의: {self.base_query}\n"
            f"- 저장된 청크 수: {self.stored_chunks}\n"
            f"- 대상 컬렉션: {self.collection}\n"
            f"- 생성된 연관 질의:\n{related}\n"
            f"- 크롤링 실패:\n{failures}"
        )


def _build_embedding(model_name: str | None) -> GoogleGenerativeAIEmbeddings:
    chosen = model_name or DEFAULT_EMBEDDING_MODEL
    try:
        return GoogleGenerativeAIEmbeddings(model=chosen)
    except Exception as exc:  # pragma: no cover - depends on external services
        raise AgentConfigurationError(
            f"Failed to create Gemini embedding model '{chosen}': {exc}"
        ) from exc


def _prepare_collection(
    client: QdrantClient,
    collection: str,
    *,
    vector_size: int,
    distance: qmodels.Distance,
    on_disk: bool,
) -> None:
    if client.collection_exists(collection):
        info = client.get_collection(collection)
        existing_size = info.config.params.vectors.size  # type: ignore[attr-defined]
        if existing_size != vector_size:
            raise AgentConfigurationError(
                "Vector size mismatch between Qdrant collection and Gemini embeddings. "
                f"Collection expects {existing_size}, but embeddings produced {vector_size}."
            )
        return

    ensure_collection(
        client,
        VectorCollectionConfig(
            name=collection,
            vector_size=vector_size,
            distance=distance,
            on_disk=on_disk,
        ),
    )


def _chunk_payload(base_query: str, chunk: SearchChunk) -> dict[str, object]:
    return {
        "base_query": base_query,
        "search_query": chunk.query,
        "source_label": chunk.source_label,
        "url": chunk.url,
        "title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "content_length": len(chunk.content),
    }


def _upsert_chunks(
    client: QdrantClient,
    collection: str,
    chunks: Sequence[SearchChunk],
    vectors: Sequence[List[float]],
    *,
    base_query: str,
) -> int:
    points: List[qmodels.PointStruct] = []
    for chunk, vector in zip(chunks, vectors):
        payload = _chunk_payload(base_query, chunk)
        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=payload,
            )
        )

    if not points:
        return 0

    client.upsert(collection_name=collection, points=points)
    return len(points)


def run_agent(
    query: str,
    *,
    tavily_client: "TavilyClient | None" = None,
    related_limit: int = 5,
    crawl_limit: int = 5,
    results_per_query: int = 5,
    ai_model: str | None = None,
    chunk_size: int = 500,
    embedding_model: str | None = None,
    qdrant_host: str = "localhost",
    qdrant_port: int = 6333,
    qdrant_api_key: str | None = None,
    collection: str = "miner-documents",
    distance: qmodels.Distance = qmodels.Distance.COSINE,
    on_disk: bool = False,
) -> AgentRunSummary:
    """Execute the Gemini agent workflow and persist chunk vectors."""

    chunk_result: AgentChunkResult = collect_agent_chunks(
        query,
        client=tavily_client,
        related_limit=related_limit,
        crawl_limit=crawl_limit,
        results_per_query=results_per_query,
        ai_model=ai_model,
        chunk_size=chunk_size,
    )

    if not chunk_result.chunks:
        return AgentRunSummary(
            base_query=query,
            related_queries=chunk_result.related_queries,
            stored_chunks=0,
            collection=collection,
            failures=chunk_result.failures,
        )

    embedder = _build_embedding(embedding_model)
    texts = [chunk.content for chunk in chunk_result.chunks]

    try:
        vectors = embedder.embed_documents(texts)
    except Exception as exc:  # pragma: no cover - external service call
        raise AgentConfigurationError(
            f"Gemini embedding generation failed: {exc}"
        ) from exc

    if not vectors:
        return AgentRunSummary(
            base_query=query,
            related_queries=chunk_result.related_queries,
            stored_chunks=0,
            collection=collection,
            failures=["임베딩 생성 결과가 비어 있습니다."],
        )

    vector_size = len(vectors[0])

    qdrant_client = create_client(qdrant_host, qdrant_port, qdrant_api_key)
    _prepare_collection(
        qdrant_client,
        collection,
        vector_size=vector_size,
        distance=distance,
        on_disk=on_disk,
    )

    stored = _upsert_chunks(
        qdrant_client,
        collection,
        chunk_result.chunks,
        vectors,
        base_query=query,
    )

    return AgentRunSummary(
        base_query=query,
        related_queries=chunk_result.related_queries,
        stored_chunks=stored,
        collection=collection,
        failures=chunk_result.failures,
    )


__all__: Iterable[str] = ["run_agent", "AgentRunSummary", "AgentConfigurationError"]
