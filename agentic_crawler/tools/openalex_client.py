"""Client for querying the OpenAlex API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests


@dataclass
class OpenAlexWork:
    """Structured representation of an OpenAlex work entry."""

    id: Optional[str]
    title: Optional[str]
    published_year: Optional[int]
    doi: Optional[str]
    cited_by_count: int
    authors: List[str]
    abstract: Optional[str]


class OpenAlexClient:
    """Simple HTTP client that queries the OpenAlex works endpoint."""

    BASE_URL = "https://api.openalex.org"

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

    def search_works(self, query: str, per_page: int = 5) -> List[OpenAlexWork]:
        """Search for academic works by keyword."""

        if not query:
            raise ValueError("query must not be empty")
        if per_page <= 0:
            raise ValueError("per_page must be a positive integer")

        params = {"search": query, "per-page": per_page}
        response = self._session.get(
            f"{self._base_url}/works", params=params, timeout=self._timeout
        )
        response.raise_for_status()
        payload = response.json()
        return [self._parse_work(item) for item in payload.get("results", [])]

    def _parse_work(self, data: dict) -> OpenAlexWork:
        authors = [
            (entry.get("author") or {}).get("display_name")
            for entry in data.get("authorships", [])
            if entry.get("author")
        ]
        abstract = self._reconstruct_abstract(data.get("abstract_inverted_index"))
        return OpenAlexWork(
            id=data.get("id"),
            title=data.get("display_name"),
            published_year=data.get("publication_year"),
            doi=data.get("doi"),
            cited_by_count=int(data.get("cited_by_count", 0) or 0),
            authors=[name for name in authors if name],
            abstract=abstract,
        )

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[dict]) -> Optional[str]:
        if not isinstance(inverted_index, dict):
            return inverted_index

        tokens: List[tuple[int, str]] = []
        for token, positions in inverted_index.items():
            for position in positions:
                tokens.append((position, token))
        tokens.sort(key=lambda item: item[0])
        ordered_words = [token for _, token in tokens]
        if not ordered_words:
            return None
        return " ".join(ordered_words)


def format_openalex_results(results: Iterable[OpenAlexWork]) -> str:
    """Human friendly rendering for OpenAlex results."""

    rows = list(results)
    if not rows:
        return "No OpenAlex results found."

    lines = []
    for index, work in enumerate(rows, 1):
        authors = ", ".join(work.authors) if work.authors else "Unknown authors"
        year = work.published_year or "n.d."
        doi = f" DOI: {work.doi}" if work.doi else ""
        lines.append(
            f"{index}. {work.title or 'Untitled'} ({year}) by {authors} – cited {work.cited_by_count} times.{doi}"
        )
        if work.abstract:
            lines.append(f"   Abstract: {work.abstract[:280]}...")
    return "\n".join(lines)


__all__ = ["OpenAlexClient", "OpenAlexWork", "format_openalex_results"]
