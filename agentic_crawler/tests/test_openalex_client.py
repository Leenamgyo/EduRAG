"""Tests for the OpenAlex client."""

from __future__ import annotations

import pytest

from agentic_crawler.tools.openalex_client import (
    OpenAlexClient,
    OpenAlexWork,
    format_openalex_results,
)


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - no-op
        return None

    def json(self):
        return self._payload


class DummySession:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    def get(self, url, params=None, timeout=None):
        self.last_request = {"url": url, "params": params, "timeout": timeout}
        return DummyResponse(self.payload)


def test_search_works_parses_results():
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Sample Paper",
                "publication_year": 2024,
                "doi": "10.1234/example",
                "cited_by_count": 10,
                "authorships": [
                    {"author": {"display_name": "Alice"}},
                    {"author": {"display_name": "Bob"}},
                ],
                "abstract_inverted_index": {"hello": [0], "world": [1]},
            }
        ]
    }
    session = DummySession(payload)
    client = OpenAlexClient(session=session, timeout=5)

    results = client.search_works("langchain", per_page=3)

    assert len(results) == 1
    work = results[0]
    assert work.title == "Sample Paper"
    assert work.authors == ["Alice", "Bob"]
    assert work.abstract == "hello world"
    assert session.last_request["params"] == {"search": "langchain", "per-page": 3}


def test_search_works_requires_query():
    client = OpenAlexClient(session=DummySession({}))
    with pytest.raises(ValueError):
        client.search_works("", per_page=1)


def test_format_openalex_results_handles_empty():
    assert format_openalex_results([]) == "No OpenAlex results found."


def test_format_openalex_results_renders_lines():
    work = OpenAlexWork(
        id="id",
        title="Test",
        published_year=2020,
        doi=None,
        cited_by_count=5,
        authors=["Alice"],
        abstract="Sample abstract",
    )
    rendered = format_openalex_results([work])
    assert "Test" in rendered
    assert "Sample abstract" in rendered
