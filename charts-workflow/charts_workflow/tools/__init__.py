from __future__ import annotations

from collections.abc import Sequence

from .tavily_tool import tavily_web_search
from .semantic_scholar import semantic_scholar_search
from .crossref_tool import crossref_search
from .openalex_tool import openalex_search

DEFAULT_TOOLCHAIN: Sequence = (
    tavily_web_search,
    semantic_scholar_search,
    crossref_search,
    openalex_search,
)

SEARCH_TOOL_PAIRS = (
    ("Tavily", tavily_web_search),
    ("Semantic Scholar", semantic_scholar_search),
    ("CrossRef", crossref_search),
    ("OpenAlex", openalex_search),
)

__all__ = [
    "DEFAULT_TOOLCHAIN",
    "SEARCH_TOOL_PAIRS",
    "tavily_web_search",
    "semantic_scholar_search",
    "crossref_search",
    "openalex_search",
]
