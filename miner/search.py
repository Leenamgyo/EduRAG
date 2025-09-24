"""Search utilities for discovering new data sources.

This module adapts the multi-lingual web search strategy from the
``ai-search`` project so that Miner can quickly discover candidate
documents for ingestion.  The main entry point is :func:`run_search`
which executes a small search plan using the Tavily web search API and
returns the aggregated findings in Markdown format.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, List, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from tavily import TavilyClient

try:  # Optional dependency – the module still works without translation.
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


def run_search(query: str, *, client: "TavilyClient | None" = None) -> str:
    """Execute the Tavily search plan and return aggregated Markdown output."""

    api_key = os.getenv("TAVILY_API_KEY")
    client = _resolve_client(api_key, client)

    sections: List[str] = []
    seen_urls: set[str] = set()

    for request in build_search_plan(query):
        try:
            response = client.search(query=request.query, **request.options)
            items = response.get("results", [])
        except Exception as exc:  # pragma: no cover - depends on external API.
            sections.append(f"### [{request.label}] 검색 실패\n- 오류: {exc}")
            continue

        if not items:
            sections.append(
                f"### [{request.label}] 검색 결과 없음\n- 사용 쿼리: {request.query}"
            )
            continue

        lines: List[str] = []
        for item in items:
            title = item.get("title") or "제목 없음"
            url = item.get("url") or "URL 없음"
            snippet = item.get("content") or item.get("snippet") or "요약 없음"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            lines.append(
                f"- **{title}**\n  - URL: {url}\n  - 요약: {snippet}"
            )

        body = "\n".join(lines) if lines else "- 신규 정보 없음"
        sections.append(
            f"### [{request.label}] 검색 결과\n- 사용 쿼리: {request.query}\n{body}"
        )

    return "\n\n".join(sections)


__all__: Iterable[str] = ["SearchRequest", "build_search_plan", "run_search"]

