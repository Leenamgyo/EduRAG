"""LangChain tool adapters for the agentic crawler."""

from __future__ import annotations

from typing import Callable, Optional

from langchain_core.tools import StructuredTool

from .openalex_client import OpenAlexClient, format_openalex_results
from .semantic_scholar_client import (
    SemanticScholarClient,
    format_semantic_scholar_results,
)
from .tavily_client import TavilySearchClient, format_tavily_results

__all__ = [
    "create_openalex_tool",
    "create_semantic_scholar_tool",
    "create_tavily_tool",
]


def _wrap_tool(fn: Callable[..., str], *, name: str, description: str) -> StructuredTool:
    tool = StructuredTool.from_function(fn, name=name, description=description)
    return tool


def create_openalex_tool(
    client: Optional[OpenAlexClient] = None,
    *,
    per_page: int = 5,
) -> StructuredTool:
    """Create a LangChain tool for OpenAlex search."""

    api_client = client or OpenAlexClient()

    def _run(query: str) -> str:
        results = api_client.search_works(query, per_page=per_page)
        return format_openalex_results(results)

    return _wrap_tool(
        _run,
        name="openalex_search",
        description="Search academic literature via OpenAlex.",
    )


def create_semantic_scholar_tool(
    client: Optional[SemanticScholarClient] = None,
    *,
    limit: int = 5,
) -> StructuredTool:
    """Create a LangChain tool for Semantic Scholar search."""

    api_client = client or SemanticScholarClient()

    def _run(query: str) -> str:
        results = api_client.search_papers(query, limit=limit)
        return format_semantic_scholar_results(results)

    return _wrap_tool(
        _run,
        name="semantic_scholar_search",
        description="Search scholarly papers using Semantic Scholar.",
    )


def create_tavily_tool(
    client: Optional[TavilySearchClient] = None,
    *,
    max_results: int = 5,
) -> StructuredTool:
    """Create a LangChain tool for Tavily web search."""

    api_client = client or TavilySearchClient()

    def _run(query: str) -> str:
        results = api_client.search(query, max_results=max_results)
        return format_tavily_results(results)

    return _wrap_tool(
        _run,
        name="tavily_search",
        description="Perform a web search via Tavily for complementary context.",
    )
