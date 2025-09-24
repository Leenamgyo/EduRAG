"""Search utilities for discovering new data sources.

This module extends the original Tavily-powered search helpers so that Miner
can operate as an "AI crawler". Given a seed query the crawler now discovers
related queries, performs focused searches, and extracts the contents of the
most relevant results. The aggregated findings are returned in Markdown format
so that downstream tooling can ingest the output easily.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple, TYPE_CHECKING

from uuid import UUID, uuid4
from urllib.parse import urlparse


from miner_core import log_search_run

from .gemini import generate_related_queries as gemini_generate

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tavily import TavilyClient

try:  # Optional dependency - the module still works without translation.
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover - translation is optional at runtime.
    GoogleTranslator = None  # type: ignore[assignment]


@dataclass(slots=True)
class SearchRequest:
    """Single Tavily search request within a larger search plan."""

    label: str
    query: str
    options: dict[str, object]


@dataclass(slots=True)
class SearchHit:
    """Single Tavily search hit captured for downstream processing."""

    request_label: str
    query: str
    title: str
    url: str
    snippet: str
    raw_snippet: str


@dataclass(slots=True)
class SearchChunk:
    """Chunk of crawled content produced from a Tavily result."""

    query: str
    source_label: str
    url: str
    title: str
    chunk_index: int
    content: str

    def doc_id(self) -> str:
        return f"{self.url}#chunk-{self.chunk_index}"

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "source_label": self.source_label,
            "url": self.url,
            "title": self.title,
            "chunk_index": self.chunk_index,
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SearchChunk":
        return cls(
            query=str(data["query"]),
            source_label=str(data.get("source_label", "")),
            url=str(data.get("url", "")),
            title=str(data.get("title", "")),
            chunk_index=int(data.get("chunk_index", 0)),
            content=str(data.get("content", "")),
        )


_BLOCKED_CRAWL_DOMAINS: tuple[str, ...] = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)


def _is_crawlable_url(url: str) -> bool:
    """Return True when the URL should be crawled for content extraction."""

    try:
        host = urlparse(url).netloc.lower()
    except Exception:  # pragma: no cover - defensive, depends on stdlib internals.
        return False

    if not host:
        return False

    return not any(
        host == blocked or host.endswith("." + blocked)
        for blocked in _BLOCKED_CRAWL_DOMAINS
    )


@dataclass(slots=True)
class SearchRunResult:
    """Aggregated output returned by :func:`run_search`."""

    base_query: str
    sections: List[str]
    markdown: str
    related_queries: List[str]
    chunks: List[SearchChunk]
    failures: List[str]
    run_id: UUID | None = None

    def to_markdown(self) -> str:
        return self.markdown

    def __str__(self) -> str:  # pragma: no cover - convenience for CLI printing
        return self.markdown

    def to_dict(self) -> dict[str, object]:
        return {
            "base_query": self.base_query,
            "sections": list(self.sections),
            "markdown": self.markdown,
            "related_queries": list(self.related_queries),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "failures": list(self.failures),
            "run_id": str(self.run_id) if self.run_id else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SearchRunResult":
        run_id_value = data.get("run_id")
        run_id = UUID(str(run_id_value)) if run_id_value else None
        return cls(
            base_query=str(data.get("base_query", "")),
            sections=list(data.get("sections", [])),
            markdown=str(data.get("markdown", "")),
            related_queries=list(data.get("related_queries", [])),
            chunks=[SearchChunk.from_dict(item) for item in data.get("chunks", [])],
            failures=list(data.get("failures", [])),
            run_id=run_id,
        )


@dataclass(slots=True)
class AgentChunkResult:
    """Structured output for agent-oriented crawling."""

    base_query: str
    related_queries: List[str]
    chunks: List[SearchChunk]
    failures: List[str]
    object_id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, object]:
        return {
            "base_query": self.base_query,
            "related_queries": list(self.related_queries),
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "failures": list(self.failures),
            "object_id": str(self.object_id),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "AgentChunkResult":
        object_id_raw = data.get("object_id")
        object_id = UUID(str(object_id_raw)) if object_id_raw else uuid4()
        return cls(
            base_query=str(data.get("base_query", "")),
            related_queries=list(data.get("related_queries", [])),
            chunks=[SearchChunk.from_dict(item) for item in data.get("chunks", [])],
            failures=list(data.get("failures", [])),
            object_id=object_id,
        )

    def default_object_name(self) -> str:
        safe_query = re.sub(r"[^a-zA-Z0-9_-]+", "-", self.base_query).strip("-") or "search"
        return f"search-results/{safe_query}-{self.object_id}.json"

    @classmethod
    def from_run_result(cls, result: SearchRunResult) -> "AgentChunkResult":
        object_id = result.run_id or uuid4()
        return cls(
            base_query=result.base_query,
            related_queries=result.related_queries,
            chunks=result.chunks,
            failures=result.failures,
            object_id=object_id,
        )


def _translate_query(query: str) -> str | None:
    """Translate the query into English when possible."""

    if GoogleTranslator is None:
        return None

    try:
        translated = GoogleTranslator(source="auto", target="en").translate(query)
    except Exception:  # pragma: no cover - network failures are handled gracefully.
        return None

    if isinstance(translated, str):
        trimmed = translated.strip()
        return trimmed or None
    return None


def build_search_plan(query: str) -> List[SearchRequest]:
    """Create a list of focused web searches for the given query."""

    plan: List[SearchRequest] = []
    plan.append(
        SearchRequest(
            label="KO",
            query=query,
            options={
                "language": "ko",
                "include_domains": ["moe.go.kr", "kedi.re.kr", "ac.kr", "go.kr"],
            },
        )
    )

    english_query = _translate_query(query) or query

    plan.append(
        SearchRequest(
            label="EN",
            query=english_query,
            options={
                "language": "en",
                "include_domains": [
                    "oecd.org",
                    "unesco.org",
                    "worldbank.org",
                    "eric.ed.gov",
                    "ed.gov",
                    "brookings.edu",
                ],
            },
        )
    )

    plan.append(
        SearchRequest(
            label="GLOBAL",
            query=english_query,
            options={"language": "en", "search_depth": "advanced"},
        )
    )

    return plan


def _resolve_client(api_key: str | None, client: "TavilyClient | None") -> "TavilyClient":
    """Return a Tavily client instance, importing lazily when necessary."""

    if client is not None:
        return client
    if not api_key:
        raise ValueError("TAVILY_API_KEY environment variable is not set.")

    try:  # Local import keeps the dependency optional until actually needed.
        from tavily import TavilyClient as _TavilyClient  # type: ignore
    except Exception as exc:  # pragma: no cover - import depends on optional dep.
        raise RuntimeError(
            "tavily-python package is required to run Miner search mode."
        ) from exc

    return _TavilyClient(api_key=api_key)


def _collect_strings(value: object) -> List[str]:
    """Extract string leaves from nested Tavily metadata structures."""

    items: List[str] = []
    if isinstance(value, str):
        items.append(value)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for element in value:
            items.extend(_collect_strings(element))
    elif isinstance(value, dict):
        mapping = value
        for key in ("label", "query", "title", "question", "text", "name"):
            candidate = mapping.get(key)
            if isinstance(candidate, str):
                items.append(candidate)
        for element in mapping.values():
            if isinstance(element, (list, tuple, dict)):
                items.extend(_collect_strings(element))
    return items


def discover_related_queries(
    query: str,
    client: "TavilyClient",
    *,
    limit: int,
) -> List[str]:
    """Generate a list of AI-discovered related search queries."""

    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            include_answer="advanced",
            auto_parameters=True,
            max_results=8,
        )
    except Exception:
        return []

    candidates: List[str] = []
    for key in (
        "follow_up_questions",
        "related_questions",
        "related_queries",
        "query_suggestions",
        "suggested_queries",
    ):
        candidates.extend(_collect_strings(response.get(key)))

    candidates.extend(_collect_strings(response.get("query_graph")))

    if not candidates:
        titles = [item.get("title") for item in response.get("results", [])]
        candidates.extend(_collect_strings(titles))

    normalized: List[str] = []
    seen = set()
    base = query.strip().lower()
    for candidate in candidates:
        cleaned = " ".join(candidate.split())
        if not cleaned:
            continue
        lower = cleaned.lower()
        if lower == base or lower in seen:
            continue
        seen.add(lower)
        normalized.append(cleaned)
        if len(normalized) >= limit:
            break

    return normalized


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _clean_snippet(text: str, *, limit: int | None = 320) -> str:
    """Normalize whitespace and truncate long snippets."""

    snippet = _normalize_text(text)
    if not snippet:
        return "요약 없음"
    if limit is not None and len(snippet) > limit:
        return snippet[: limit - 3] + "..."
    return snippet


def _chunk_text(text: str, *, chunk_size: int) -> List[str]:
    """Split text into fixed-width chunks after normalization."""

    normalized = _normalize_text(text)
    if not normalized or chunk_size <= 0:
        return []

    chunk_size = max(1, chunk_size)
    return [
        normalized[index : index + chunk_size]
        for index in range(0, len(normalized), chunk_size)
    ]


def _run_single_search(
    client: "TavilyClient",
    request: SearchRequest,
    *,
    results_per_query: int,
    seen_urls: set[str],
) -> tuple[str, List[str], List[str], List[SearchHit]]:
    """Execute a search request and return Markdown plus new URLs and context."""

    options = dict(request.options)
    options.setdefault("max_results", results_per_query)
    try:
        response = client.search(query=request.query, **options)
    except Exception as exc:  # pragma: no cover - depends on external API.
        return (f"### [{request.label}] 검색 실패\n- 오류: {exc}", [], [], [])

    items = response.get("results", [])
    if not items:
        return (
            f"### [{request.label}] 검색 결과 없음\n- 사용 쿼리: {request.query}",
            [],
            [],
            [],
        )

    new_urls: List[str] = []
    lines: List[str] = []
    contexts: List[str] = []
    hits: List[SearchHit] = []

    for item in items:
        url = item.get("url") or "URL 없음"
        title = item.get("title") or "제목 없음"
        snippet_source = item.get("content") or item.get("snippet") or ""
        snippet = _clean_snippet(snippet_source)
        if url != "URL 없음" and url in seen_urls:
            continue
        if url != "URL 없음":
            seen_urls.add(url)
            new_urls.append(url)
        lines.append(
            f"- **{title}**\n  - URL: {url}\n  - 요약: {snippet}"
        )
        context_line = _normalize_text(f"{title} :: {snippet_source}")
        if context_line:
            contexts.append(context_line[:400])
        hits.append(
            SearchHit(
                request_label=request.label,
                query=request.query,
                title=title,
                url=url,
                snippet=snippet,
                raw_snippet=snippet_source,
            )
        )
        if len(lines) >= results_per_query:
            break

    body = "\n".join(lines) if lines else "- 신규 정보 없음"
    section = f"### [{request.label}] 검색 결과\n- 사용 쿼리: {request.query}\n{body}"
    return section, new_urls, contexts, hits


def _collect_crawled_chunks(
    client: "TavilyClient",
    urls: Sequence[str],
    url_metadata: dict[str, dict[str, str]],
    *,
    chunk_size: int,
) -> Tuple[List[SearchChunk], List[str]]:
    """Fetch page content for URLs and return structured chunks."""

    if not urls:
        return [], []

    try:
        response = client.extract(
            urls=list(urls),
            extract_depth="advanced",
            format="markdown",
            timeout=90,
        )
    except Exception as exc:  # pragma: no cover - depends on external API.
        return [], [f"크롤링 요청 실패: {exc}"]

    chunks: List[SearchChunk] = []
    failures: List[str] = []

    for item in response.get("results", []):
        url = item.get("url") or "URL 없음"
        meta = url_metadata.get(url, {})
        title = item.get("title") or meta.get("title") or "제목 없음"
        content = item.get("content") or ""
        chunk_texts = _chunk_text(content, chunk_size=chunk_size)
        if chunk_texts:
            for idx, chunk_text in enumerate(chunk_texts, start=1):
                chunks.append(
                    SearchChunk(
                        query=meta.get("query", ""),
                        source_label=meta.get("label", ""),
                        url=url,
                        title=title,
                        chunk_index=idx,
                        content=chunk_text,
                    )
                )
        else:
            fallback = _clean_snippet(content)
            chunks.append(
                SearchChunk(
                    query=meta.get("query", ""),
                    source_label=meta.get("label", ""),
                    url=url,
                    title=title,
                    chunk_index=1,
                    content=fallback,
                )
            )

    for failed in response.get("failed_results", []):
        url = failed.get("url") or "URL 없음"
        error = failed.get("error") or "알 수 없는 오류"
        failures.append(f"{url}: {error}")

    return chunks, failures


def _render_crawled_sections(
    chunks: Sequence[SearchChunk],
    failures: Sequence[str],
) -> List[str]:
    """Render crawled chunks and failures into Markdown sections."""

    if not chunks and not failures:
        return []

    grouped: dict[str, List[SearchChunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.url].append(chunk)

    sections: List[str] = []
    for url, chunk_list in grouped.items():
        title = chunk_list[0].title
        header = f"- **{title}**\n  - URL: {url}"
        body_lines = [
            f"  - 청크 {chunk.chunk_index}: {chunk.content}"
            for chunk in chunk_list
        ]
        sections.append("\n".join(["### 크롤링된 문서 청크", header, *body_lines]))

    if failures:
        failure_lines = "\n".join(f"- {item}" for item in failures)
        sections.append("### 크롤링 실패 목록\n" + failure_lines)

    return sections


def _merge_related_queries(
    query: str,
    primary: Sequence[str],
    fallback: Sequence[str],
    *,
    limit: int,
) -> List[str]:
    base = query.strip().lower()
    selections: List[str] = []
    seen: set[str] = {base}

    for candidate in list(primary) + list(fallback):
        normalized = _normalize_text(candidate)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        selections.append(normalized)
        if len(selections) >= limit:
            break

    return selections


def run_search(
    query: str,
    *,
    client: "TavilyClient | None" = None,
    related_limit: int = 5,
    crawl_limit: int = 5,
    results_per_query: int = 5,
    ai_model: str | None = None,
    ai_prompt: str | None = None,
    chunk_size: int = 500,
) -> SearchRunResult:
    """Execute the Tavily search plan and return aggregated output."""

    api_key = os.getenv("TAVILY_API_KEY")
    client = _resolve_client(api_key, client)

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if ai_model is None:
        ai_model = (
            os.getenv("MINOR_SEARCH_AI_MODEL")
            or os.getenv("MINOR_SEARCH_GEMINI_MODEL")
            or os.getenv("MINER_SEARCH_AI_MODEL")
            or os.getenv("MINER_GEMINI_MODEL")
        )

    sections: List[str] = []
    seen_urls: set[str] = set()
    urls_for_crawl: List[str] = []
    url_metadata: dict[str, dict[str, str]] = {}
    context_samples: List[str] = []
    collected_chunks: List[SearchChunk] = []
    crawl_failures: List[str] = []

    for request in build_search_plan(query):
        section, new_urls, contexts, hits = _run_single_search(
            client,
            request,
            results_per_query=results_per_query,
            seen_urls=seen_urls,
        )
        sections.append(section)
        context_samples.extend(contexts)
        for hit in hits:
            if (
                hit.url == "URL 없음"
                or hit.url in url_metadata
                or not _is_crawlable_url(hit.url)
            ):
                continue
            url_metadata[hit.url] = {
                "query": hit.query,
                "label": request.label,
                "title": hit.title,
            }
        for url in new_urls:
            if len(urls_for_crawl) >= crawl_limit:
                break
            if not _is_crawlable_url(url):
                continue
            if url not in urls_for_crawl:
                urls_for_crawl.append(url)

    related_queries: List[str] = []
    if related_limit > 0:
        gemini_queries = gemini_generate(
            query,
            limit=related_limit,
            model=ai_model,
            context_samples=context_samples[: 3 * related_limit],
            prompt_template=ai_prompt,
        )
        fallback_queries = discover_related_queries(query, client, limit=related_limit)
        related_queries = _merge_related_queries(
            query,
            gemini_queries,
            fallback_queries,
            limit=related_limit,
        )

    if related_queries:
        related_lines = [f"{idx + 1}. {item}" for idx, item in enumerate(related_queries)]
        sections.append("### Gemini 연관 검색어\n" + "\n".join(related_lines))

        for idx, related_query in enumerate(related_queries, start=1):
            request = SearchRequest(
                label=f"AI-{idx}",
                query=related_query,
                options={"search_depth": "advanced"},
            )
            section, new_urls, contexts, hits = _run_single_search(
                client,
                request,
                results_per_query=results_per_query,
                seen_urls=seen_urls,
            )
            sections.append(section)
            context_samples.extend(contexts)
            for hit in hits:
                if (
                    hit.url == "URL 없음"
                    or hit.url in url_metadata
                    or not _is_crawlable_url(hit.url)
                ):
                    continue
                url_metadata[hit.url] = {
                    "query": hit.query,
                    "label": request.label,
                    "title": hit.title,
                }
            for url in new_urls:
                if len(urls_for_crawl) >= crawl_limit:
                    break
                if not _is_crawlable_url(url):
                    continue
                if url not in urls_for_crawl:
                    urls_for_crawl.append(url)

    chunks, failures = _collect_crawled_chunks(
        client,
        urls_for_crawl[:crawl_limit],
        url_metadata,
        chunk_size=chunk_size,
    )
    collected_chunks.extend(chunks)
    crawl_failures.extend(failures)

    crawl_sections = _render_crawled_sections(chunks, failures)
    if crawl_sections:
        sections.extend(crawl_sections)

    markdown = "\n\n".join(sections)

    result = SearchRunResult(
        base_query=query,
        sections=sections,
        markdown=markdown,
        related_queries=related_queries,
        chunks=collected_chunks,
        failures=crawl_failures,
    )

    run_id = log_search_run(
        base_query=result.base_query,
        markdown=result.markdown,
        related_queries=result.related_queries,
        chunks=result.chunks,
        failures=result.failures,
    )
    result.run_id = run_id

    return result


def collect_agent_chunks(
    query: str,
    *,
    client: "TavilyClient | None" = None,
    related_limit: int = 5,
    crawl_limit: int = 5,
    results_per_query: int = 5,
    ai_model: str | None = None,
    ai_prompt: str | None = None,
    chunk_size: int = 500,
) -> AgentChunkResult:
    """Gather chunked documents suitable for agent ingestion pipelines."""

    api_key = os.getenv("TAVILY_API_KEY")
    tavily_client = _resolve_client(api_key, client)

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    if ai_model is None:
        ai_model = (
            os.getenv("MINOR_SEARCH_AI_MODEL")
            or os.getenv("MINOR_SEARCH_GEMINI_MODEL")
            or os.getenv("MINER_SEARCH_AI_MODEL")
            or os.getenv("MINER_GEMINI_MODEL")
        )

    seen_urls: set[str] = set()
    urls_for_crawl: List[str] = []
    url_metadata: dict[str, dict[str, str]] = {}
    context_samples: List[str] = []

    for request in build_search_plan(query):
        _, new_urls, contexts, hits = _run_single_search(
            tavily_client,
            request,
            results_per_query=results_per_query,
            seen_urls=seen_urls,
        )
        context_samples.extend(contexts)
        for hit in hits:
            if (
                hit.url == "URL 없음"
                or hit.url in url_metadata
                or not _is_crawlable_url(hit.url)
            ):
                continue
            url_metadata[hit.url] = {
                "query": hit.query,
                "label": request.label,
                "title": hit.title,
            }
        for url in new_urls:
            if len(urls_for_crawl) >= crawl_limit:
                break
            if not _is_crawlable_url(url):
                continue
            if url not in urls_for_crawl:
                urls_for_crawl.append(url)

    related_queries: List[str] = []
    if related_limit > 0:
        gemini_queries = gemini_generate(
            query,
            limit=related_limit,
            model=ai_model,
            context_samples=context_samples[: 3 * related_limit],
            prompt_template=ai_prompt,
        )
        fallback_queries = discover_related_queries(query, tavily_client, limit=related_limit)
        related_queries = _merge_related_queries(
            query,
            gemini_queries,
            fallback_queries,
            limit=related_limit,
        )

        for idx, related_query in enumerate(related_queries, start=1):
            search_request = SearchRequest(
                label=f"AI-{idx}",
                query=related_query,
                options={"search_depth": "advanced"},
            )
            _, new_urls, _, hits = _run_single_search(
                tavily_client,
                search_request,
                results_per_query=results_per_query,
                seen_urls=seen_urls,
            )
            for hit in hits:
                if (
                    hit.url == "URL 없음"
                    or hit.url in url_metadata
                    or not _is_crawlable_url(hit.url)
                ):
                    continue
                url_metadata[hit.url] = {
                    "query": hit.query,
                    "label": search_request.label,
                    "title": hit.title,
                }
            for url in new_urls:
                if len(urls_for_crawl) >= crawl_limit:
                    break
                if not _is_crawlable_url(url):
                    continue
                if url not in urls_for_crawl:
                    urls_for_crawl.append(url)

    chunks, failures = _collect_crawled_chunks(
        tavily_client,
        urls_for_crawl[:crawl_limit],
        url_metadata,
        chunk_size=chunk_size,
    )

    return AgentChunkResult(
        base_query=query,
        related_queries=related_queries,
        chunks=chunks,
        failures=failures,
    )


__all__: Iterable[str] = [
    "SearchRequest",
    "SearchHit",
    "SearchChunk",
    "SearchRunResult",
    "AgentChunkResult",
    "build_search_plan",
    "discover_related_queries",
    "run_search",
    "collect_agent_chunks",
]



