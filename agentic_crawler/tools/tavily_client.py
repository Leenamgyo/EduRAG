"""Client wrapper around Tavily search API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

try:
    from tavily import TavilyClient as _TavilyClient
except Exception:  # pragma: no cover - dependency might be optional during tests
    _TavilyClient = None  # type: ignore[assignment]


@dataclass
class TavilyResult:
    """Representation of a single Tavily search result."""

    title: Optional[str]
    url: Optional[str]
    content: Optional[str]


class TavilySearchClient:
    """Lightweight wrapper that delegates to the Tavily SDK."""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        client: Optional[object] = None,
    ) -> None:
        if client is not None:
            self._client = client
        else:
            if _TavilyClient is None:
                raise ImportError(
                    "tavily package is required unless a client instance is provided"
                )
            self._client = _TavilyClient(api_key=api_key)

    def search(self, query: str, max_results: int = 5) -> List[TavilyResult]:
        """Perform a web search through Tavily."""

        if not query:
            raise ValueError("query must not be empty")
        if max_results <= 0:
            raise ValueError("max_results must be a positive integer")

        response = self._client.search(query=query, max_results=max_results)
        raw_results = response.get("results", []) if isinstance(response, dict) else []
        results = []
        for item in raw_results:
            results.append(
                TavilyResult(
                    title=item.get("title"),
                    url=item.get("url"),
                    content=item.get("content"),
                )
            )
        return results


def format_tavily_results(results: Iterable[TavilyResult]) -> str:
    """Human friendly text summary of Tavily search hits."""

    rows = list(results)
    if not rows:
        return "No Tavily search results found."

    lines = []
    for index, item in enumerate(rows, 1):
        url = f" ({item.url})" if item.url else ""
        lines.append(f"{index}. {item.title or 'Untitled'}{url}")
        if item.content:
            lines.append(f"   Snippet: {item.content[:280]}...")
    return "\n".join(lines)


__all__ = ["TavilySearchClient", "TavilyResult", "format_tavily_results"]
