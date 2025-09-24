"""Qdrant-backed retrieval tool used for RAG style lookups."""
from __future__ import annotations

from functools import lru_cache
from textwrap import shorten
from typing import Any, Iterable

from langchain_core.tools import tool
from openai import OpenAI
from qdrant_client import QdrantClient

from ai_search.config.settings import settings


class QdrantToolError(RuntimeError):
    """Raised when the Qdrant retrieval tool cannot be initialised."""


def _normalise_snippet(text: str, *, width: int = 360) -> str:
    cleaned = " ".join(text.split())
    return shorten(cleaned, width=width, placeholder="…")


def _pick_first(payload: dict[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@lru_cache(maxsize=1)
def _qdrant_client() -> QdrantClient:
    if not settings.qdrant_host:
        raise QdrantToolError("Qdrant 호스트 정보가 설정되지 않았습니다.")
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key,
    )


@lru_cache(maxsize=1)
def _embedding_client() -> OpenAI:
    if not settings.openai_api_key:
        raise QdrantToolError("OPENAI_API_KEY 환경 변수를 설정해 주세요.")
    return OpenAI(api_key=settings.openai_api_key)


def _embed_query(query: str) -> list[float]:
    client = _embedding_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=[query],
    )
    if not response.data:
        raise QdrantToolError("임베딩 생성에 실패했습니다.")
    return list(response.data[0].embedding)


def _format_result(payload: dict[str, Any], score: float | None, index: int) -> str:
    title = _pick_first(
        payload,
        [
            "title",
            "document_title",
            "headline",
            "source_title",
        ],
    ) or f"문서 {index}"

    url = _pick_first(payload, ["url", "source", "link", "source_url"])

    body = _pick_first(
        payload,
        [
            "content",
            "text",
            "chunk",
            "body",
            "summary",
        ],
    )
    snippet = _normalise_snippet(body) if body else "본문 미제공"

    meta_lines = []
    if score is not None:
        meta_lines.append(f"유사도 점수: {score:.3f}")
    if url:
        meta_lines.append(f"출처: {url}")

    meta_section = "\n".join(f"- {line}" for line in meta_lines) if meta_lines else "- 추가 메타데이터 없음"

    return (
        f"#### {index}. {title}\n"
        f"{meta_section}\n"
        f"- 내용 발췌: {snippet}"
    )


@tool
def qdrant_rag_search(query: str) -> str:
    """Qdrant에 저장된 문서 벡터를 검색해 상위 문서를 요약합니다."""

    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("검색어를 입력해 주세요.")

    try:
        vector = _embed_query(cleaned_query)
    except Exception as exc:  # noqa: BLE001 - expose embedding failure
        raise QdrantToolError(f"임베딩 생성 실패: {exc}") from exc

    client = _qdrant_client()

    search_kwargs: dict[str, Any] = {
        "collection_name": settings.qdrant_collection,
        "query_vector": vector,
        "limit": max(settings.qdrant_top_k, 1),
        "with_payload": True,
    }
    if settings.qdrant_score_threshold is not None:
        search_kwargs["score_threshold"] = settings.qdrant_score_threshold

    try:
        hits = client.search(**search_kwargs)
    except Exception as exc:  # noqa: BLE001 - surface search failure
        raise QdrantToolError(f"Qdrant 검색 실패: {exc}") from exc

    if not hits:
        return (
            "### Qdrant RAG 검색 결과\n"
            "- 상위 문서를 찾지 못했습니다. 쿼리나 컬렉션 구성을 확인해 주세요."
        )

    sections = [
        "### Qdrant RAG 검색 결과",
        f"- 사용 컬렉션: {settings.qdrant_collection}",
        f"- 검색 쿼리: {cleaned_query}",
    ]

    for index, point in enumerate(hits, start=1):
        payload = dict(point.payload or {})
        section = _format_result(payload, getattr(point, "score", None), index)
        sections.append(section)

    return "\n\n".join(sections)


__all__ = ["qdrant_rag_search"]

