"""Tests for the Tavily client."""

from __future__ import annotations

import pytest

from agentic_crawler.tools.tavily_client import (
    TavilyResult,
    TavilySearchClient,
    format_tavily_results,
)


class DummyTavily:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


def test_search_returns_results():
    payload = {
        "results": [
            {"title": "Doc", "url": "https://example.com", "content": "Snippet"}
        ]
    }
    client = TavilySearchClient(client=DummyTavily(payload))

    results = client.search("langchain", max_results=2)

    assert len(results) == 1
    assert results[0].title == "Doc"


def test_search_requires_query():
    client = TavilySearchClient(client=DummyTavily({"results": []}))
    with pytest.raises(ValueError):
        client.search("", max_results=1)


def test_format_tavily_results_handles_empty():
    assert format_tavily_results([]) == "No Tavily search results found."


def test_format_tavily_results_renders_lines():
    result = TavilyResult(title="Doc", url="https://example.com", content="Snippet")
    rendered = format_tavily_results([result])
    assert "Doc" in rendered
    assert "https://example.com" in rendered
