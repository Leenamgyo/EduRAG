"""Client for Semantic Scholar Graph API queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests


@dataclass
class SemanticScholarPaper:
    """Structured representation of a Semantic Scholar paper."""

    paper_id: Optional[str]
    title: Optional[str]
    abstract: Optional[str]
    year: Optional[int]
    authors: List[str]
    url: Optional[str]


class SemanticScholarClient:
    """HTTP client for the Semantic Scholar Graph API search endpoint."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(
        self,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 10.0,
        base_url: Optional[str] = None,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout
        self._base_url = (base_url or self.BASE_URL).rstrip("/")

    def search_papers(self, query: str, limit: int = 5) -> List[SemanticScholarPaper]:
        """Search for papers that match the provided keyword."""

        if not query:
            raise ValueError("query must not be empty")
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        params = {
            "query": query,
            "limit": limit,
            "fields": "title,abstract,year,authors,url,paperId",
        }
        response = self._session.get(self._base_url, params=params, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        return [self._parse_paper(item) for item in payload.get("data", [])]

    @staticmethod
    def _parse_paper(item: dict) -> SemanticScholarPaper:
        authors = [entry.get("name") for entry in item.get("authors", []) if entry.get("name")]
        return SemanticScholarPaper(
            paper_id=item.get("paperId"),
            title=item.get("title"),
            abstract=item.get("abstract"),
            year=item.get("year"),
            authors=authors,
            url=item.get("url"),
        )


def format_semantic_scholar_results(results: Iterable[SemanticScholarPaper]) -> str:
    """Human readable summary of Semantic Scholar results."""

    rows = list(results)
    if not rows:
        return "No Semantic Scholar results found."

    lines = []
    for index, paper in enumerate(rows, 1):
        authors = ", ".join(paper.authors) if paper.authors else "Unknown authors"
        year = paper.year or "n.d."
        url = f" ({paper.url})" if paper.url else ""
        lines.append(f"{index}. {paper.title or 'Untitled'} ({year}) by {authors}{url}")
        if paper.abstract:
            lines.append(f"   Abstract: {paper.abstract[:280]}...")
    return "\n".join(lines)


__all__ = ["SemanticScholarClient", "SemanticScholarPaper", "format_semantic_scholar_results"]
