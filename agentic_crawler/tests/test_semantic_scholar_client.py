"""Tests for the Semantic Scholar client."""

from __future__ import annotations

import pytest

from agentic_crawler.tools.semantic_scholar_client import (
    SemanticScholarClient,
    SemanticScholarPaper,
    format_semantic_scholar_results,
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


def test_search_papers_parses_payload():
    payload = {
        "data": [
            {
                "paperId": "abc",
                "title": "Semantic Study",
                "abstract": "Study on semantics.",
                "year": 2023,
                "url": "https://example.com",
                "authors": [{"name": "Alice"}, {"name": "Bob"}],
            }
        ]
    }
    session = DummySession(payload)
    client = SemanticScholarClient(session=session)

    results = client.search_papers("retrieval", limit=2)

    assert len(results) == 1
    paper = results[0]
    assert paper.title == "Semantic Study"
    assert paper.authors == ["Alice", "Bob"]
    assert session.last_request["params"]["limit"] == 2


def test_search_papers_requires_query():
    client = SemanticScholarClient(session=DummySession({}))
    with pytest.raises(ValueError):
        client.search_papers("", limit=1)


def test_format_semantic_scholar_results_handles_empty():
    assert (
        format_semantic_scholar_results([]) == "No Semantic Scholar results found."
    )


def test_format_semantic_scholar_results_renders_lines():
    paper = SemanticScholarPaper(
        paper_id="id",
        title="Title",
        abstract="Abstract",
        year=2021,
        authors=["Alice"],
        url="https://example.com",
    )
    rendered = format_semantic_scholar_results([paper])
    assert "Title" in rendered
    assert "https://example.com" in rendered
