"""Search utilities for discovering new data sources.

This module extends the original Tavily-powered search helpers so that Miner
can operate as an "AI crawler".  Given a seed query the crawler now discovers
related queries, performs focused searches, and extracts the contents of the
most relevant results.  The aggregated findings are returned in Markdown format
so that downstream tooling can ingest the output easily.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence, TYPE_CHECKING

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
        for key in ("label", "query", "title", "question", "text", "name"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                items.append(candidate)
        for element in value.values():
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


def _clean_snippet(text: str, *, limit: int = 320) -> str:
    """Normalize whitespace and truncate long snippets."""

    snippet = re.sub(r"\s+", " ", text).strip()
    if not snippet:
        return "요약 없음"
    if len(snippet) > limit:
        return snippet[: limit - 3] + "..."
    return snippet


def _run_single_search(
    client: "TavilyClient",
    request: SearchRequest,
    *,
    results_per_query: int,
    seen_urls: set[str],
) -> tuple[str, List[str]]:
    """Execute a search request and return Markdown plus new URLs."""

    options = dict(request.options)
    options.setdefault("max_results", results_per_query)
    try:
        response = client.search(query=request.query, **options)
    except Exception as exc:  # pragma: no cover - depends on external API.
        return (f"### [{request.label}] 검색 실패\n- 오류: {exc}", [])

    items = response.get("results", [])
    if not items:
        return (
            f"### [{request.label}] 검색 결과 없음\n- 사용 쿼리: {request.query}",
            [],
        )

    new_urls: List[str] = []
    lines: List[str] = []
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
        if len(lines) >= results_per_query:
            break

    body = "\n".join(lines) if lines else "- 신규 정보 없음"
    section = f"### [{request.label}] 검색 결과\n- 사용 쿼리: {request.query}\n{body}"
    return section, new_urls


def _summarize_crawled_content(
    client: "TavilyClient",
    urls: Sequence[str],
) -> List[str]:
    """Fetch and summarize page content for the selected URLs."""

    if not urls:
        return []

    try:
        response = client.extract(
            urls=list(urls),
            extract_depth="advanced",
            format="markdown",
            timeout=90,
        )
    except Exception as exc:  # pragma: no cover - depends on external API.
        return [f"- URL 크롤링 실패\n  - 오류: {exc}"]

    summaries: List[str] = []

    for item in response.get("results", []):
        url = item.get("url") or "URL 없음"
        title = item.get("title") or "제목 없음"
        content = item.get("content") or ""
        snippet = _clean_snippet(content, limit=560)
        summaries.append(
            f"- **{title}**\n  - URL: {url}\n  - 내용 요약: {snippet}"
        )

    for failed in response.get("failed_results", []):
        url = failed.get("url") or "URL 없음"
        error = failed.get("error") or "알 수 없는 오류"
        summaries.append(f"- URL: {url}\n  - 오류: {error}")

    return summaries


def run_search(
    query: str,
    *,
    client: "TavilyClient | None" = None,
    related_limit: int = 5,
    crawl_limit: int = 5,
    results_per_query: int = 5,
) -> str:
    """Execute the Tavily search plan and return aggregated Markdown output."""

    api_key = os.getenv("TAVILY_API_KEY")
    client = _resolve_client(api_key, client)

    sections: List[str] = []
    seen_urls: set[str] = set()
    urls_for_crawl: List[str] = []

    for request in build_search_plan(query):
        section, new_urls = _run_single_search(
            client,
            request,
            results_per_query=results_per_query,
            seen_urls=seen_urls,
        )
        sections.append(section)
        for url in new_urls:
            if len(urls_for_crawl) >= crawl_limit:
                break
            if url not in urls_for_crawl:
                urls_for_crawl.append(url)

    related_queries = (
        discover_related_queries(query, client, limit=related_limit)
        if related_limit > 0
        else []
    )

    if related_queries:
        related_lines = [f"{idx + 1}. {item}" for idx, item in enumerate(related_queries)]
        sections.append(
            "### AI 연관 검색어\n" + "\n".join(related_lines)
        )

        for idx, related_query in enumerate(related_queries, start=1):
            request = SearchRequest(
                label=f"AI-{idx}",
                query=related_query,
                options={"search_depth": "advanced"},
            )
            section, new_urls = _run_single_search(
                client,
                request,
                results_per_query=results_per_query,
                seen_urls=seen_urls,
            )
            sections.append(section)
            for url in new_urls:
                if len(urls_for_crawl) >= crawl_limit:
                    break
                if url not in urls_for_crawl:
                    urls_for_crawl.append(url)

    crawl_sections = _summarize_crawled_content(client, urls_for_crawl[:crawl_limit])
    if crawl_sections:
        sections.append("### 크롤링된 문서 요약" + "\n" + "\n".join(crawl_sections))

    return "\n\n".join(sections)


__all__: Iterable[str] = [
    "SearchRequest",
    "build_search_plan",
    "discover_related_queries",
    "run_search",
]
