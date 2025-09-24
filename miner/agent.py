"""Gemini agent workflow for Miner.

This module orchestrates a Gemini-powered agent that expands a user query,
collects supporting documents, chunks them, embeds the chunks with one or more
Gemini embedding models, and stores the vectors inside Qdrant for later
retrieval.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .search import AgentChunkResult, SearchChunk, collect_agent_chunks
from .vector_db import create_client


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
    embedding_models: Dict[str, str]
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
        embedding_lines = (
            "\n".join(f"- {slot}: {model}" for slot, model in self.embedding_models.items())
            if self.embedding_models
            else "- (none)"
        )
        return (
            f"### Gemini Agent 결과\n"
            f"- 기준 질의: {self.base_query}\n"
            f"- 저장된 청크 수: {self.stored_chunks}\n"
            f"- 대상 컬렉션: {self.collection}\n"
            f"- 사용한 임베딩 모델:\n{embedding_lines}\n"
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


def _resolve_embedding_slots(
    primary_model: str | None,
    secondary_model: str | None,
) -> List[Tuple[str, str]]:
    slots: List[Tuple[str, str]] = []
    primary = primary_model or DEFAULT_EMBEDDING_MODEL
    slots.append(("primary", primary))

    if secondary_model:
        secondary_model = secondary_model.strip()
        if secondary_model and secondary_model not in {model for _, model in slots}:
            slots.append(("secondary", secondary_model))
    return slots


def _prepare_collection(
    client: QdrantClient,
    collection: str,
    *,
    vector_configs: Dict[str, qmodels.VectorParams],
) -> None:
    if client.collection_exists(collection):
        info = client.get_collection(collection)
        existing_vectors = info.config.params.vectors  # type: ignore[attr-defined]

        if isinstance(existing_vectors, qmodels.VectorParams):
            existing_map: Dict[str, qmodels.VectorParams] = {"primary": existing_vectors}
        else:
            existing_map = dict(existing_vectors or {})

        # If collection was created with an unnamed single vector, map it to primary
        if "primary" not in existing_map and len(existing_map) == 1:
            key, value = next(iter(existing_map.items()))
            existing_map = {"primary": value}

        for name, params in vector_configs.items():
            if name not in existing_map:
                raise AgentConfigurationError(
                    f"Existing collection '{collection}' does not contain vector slot '{name}'."
                )
            current = existing_map[name]
            if current.size != params.size:
                raise AgentConfigurationError(
                    "Vector size mismatch between Qdrant collection and Gemini embeddings. "
                    f"Slot '{name}' expects {current.size}, but embeddings produced {params.size}."
                )
            if current.distance != params.distance:
                raise AgentConfigurationError(
                    f"Distance mismatch for slot '{name}': collection is {current.distance}, "
                    f"but requested {params.distance}."
                )
        return

    client.create_collection(collection_name=collection, vectors_config=vector_configs)


def _chunk_payload(
    base_query: str,
    chunk: SearchChunk,
    *,
    embedding_models: Dict[str, str],
) -> Dict[str, object]:
    return {
        "doc_id": chunk.doc_id(),
        "base_query": base_query,
        "search_query": chunk.query,
        "source_label": chunk.source_label,
        "url": chunk.url,
        "title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "content": chunk.content,
        "content_length": len(chunk.content),
        "embedding_models": dict(embedding_models),
    }


def _upsert_chunks(
    client: QdrantClient,
    collection: str,
    chunks: Sequence[SearchChunk],
    vectors_map: Dict[str, Sequence[List[float]]],
    *,
    base_query: str,
    embedding_models: Dict[str, str],
) -> int:
    vector_slots = list(vectors_map.keys())
    points: List[qmodels.PointStruct] = []

    total = len(chunks)
    for index in range(total):
        chunk = chunks[index]
        vector_payload = {slot: vectors_map[slot][index] for slot in vector_slots}
        payload = _chunk_payload(
            base_query,
            chunk,
            embedding_models=embedding_models,
        )
        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector_payload,
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
    embedding_model_secondary: str | None = None,
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
            embedding_models={},
            failures=chunk_result.failures,
        )

    slots = _resolve_embedding_slots(embedding_model, embedding_model_secondary)
    embedding_models = {slot: name for slot, name in slots}
    embedder_map = {slot: _build_embedding(model_name) for slot, model_name in slots}

    texts = [chunk.content for chunk in chunk_result.chunks]

    vectors_map: Dict[str, Sequence[List[float]]] = {}
    for slot, embedder in embedder_map.items():
        try:
            vectors = embedder.embed_documents(texts)
        except Exception as exc:  # pragma: no cover - external service call
            raise AgentConfigurationError(
                f"Gemini embedding generation failed for slot '{slot}': {exc}"
            ) from exc
        if not vectors:
            raise AgentConfigurationError(
                f"Gemini embedding generation for slot '{slot}' returned no vectors."
            )
        vectors_map[slot] = vectors

    expected = len(chunk_result.chunks)
    for slot, vectors in vectors_map.items():
        if len(vectors) != expected:
            raise AgentConfigurationError(
                f"Embedding count mismatch for slot '{slot}': expected {expected}, got {len(vectors)}"
            )

    vector_configs = {
        slot: qmodels.VectorParams(size=len(vectors_map[slot][0]), distance=distance, on_disk=on_disk)
        for slot in vectors_map
    }

    qdrant_client = create_client(qdrant_host, qdrant_port, qdrant_api_key)
    _prepare_collection(
        qdrant_client,
        collection,
        vector_configs=vector_configs,
    )

    stored = _upsert_chunks(
        qdrant_client,
        collection,
        chunk_result.chunks,
        vectors_map,
        base_query=query,
        embedding_models=embedding_models,
    )

    return AgentRunSummary(
        base_query=query,
        related_queries=chunk_result.related_queries,
        stored_chunks=stored,
        collection=collection,
        embedding_models=embedding_models,
        failures=chunk_result.failures,
    )


__all__: Iterable[str] = ["run_agent", "AgentRunSummary", "AgentConfigurationError"]

