"""Functional tests for the Minor search orchestration helpers."""

from __future__ import annotations

import importlib
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

import pytest

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

stub_package = ModuleType("minor_search")
stub_package.__path__ = [str(PACKAGE_DIR)]
sys.modules.setdefault("minor_search", stub_package)

minor_stub = ModuleType("minor")
minor_stub.__path__ = []
sys.modules.setdefault("minor", minor_stub)

logbook_stub = ModuleType("minor.logbook")
def _placeholder_log_search_run(**_: Any) -> UUID:
    return uuid4()

logbook_stub.log_search_run = _placeholder_log_search_run
sys.modules.setdefault("minor.logbook", logbook_stub)
minor_stub.logbook = logbook_stub

search_module = importlib.import_module("minor_search.search")


class FakeTavilyClient:
    """Simple Tavily client double that records issued queries."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def search(self, query: str, **options: Any) -> dict[str, Any]:
        call_index = len(self.calls)
        self.calls.append((query, dict(options)))
        return {
            "results": [
                {
                    "url": f"https://example.com/{call_index}",
                    "title": f"Result {call_index}",
                    "content": f"Snippet for {query}",
                }
            ]
        }


@pytest.fixture()
def fake_run_id() -> UUID:
    """Provide a deterministic UUID for logbook interactions."""

    return uuid4()


def test_run_search_aggregates_sections_and_related_queries(monkeypatch, fake_run_id):
    """`run_search` should orchestrate Gemini, Tavily, and crawling steps."""

    fake_client = FakeTavilyClient()

    captured_collect: dict[str, Any] = {}

    def fake_collect(client: Any, urls: list[str], metadata: dict[str, dict[str, str]], *, chunk_size: int):
        assert client is fake_client
        captured_collect["urls"] = list(urls)
        captured_collect["metadata"] = {key: dict(value) for key, value in metadata.items()}
        captured_collect["chunk_size"] = chunk_size
        first_url = urls[0]
        meta = metadata[first_url]
        chunk = search_module.SearchChunk(
            query=meta.get("query", ""),
            source_label=meta.get("label", ""),
            url=first_url,
            title=meta.get("title", ""),
            chunk_index=1,
            content="crawled text",
        )
        return [chunk], ["crawl failure detected"]

    monkeypatch.setattr(search_module, "_collect_crawled_chunks", fake_collect)

    captured_gemini: dict[str, Any] = {}

    def fake_gemini(query: str, *, limit: int, model: str | None, context_samples: list[str], prompt_template: str | None):
        captured_gemini.update(
            {
                "query": query,
                "limit": limit,
                "model": model,
                "context_samples": list(context_samples),
                "prompt_template": prompt_template,
            }
        )
        return ["Gemini Primary", "Shared Topic"]

    monkeypatch.setattr(search_module, "gemini_generate", fake_gemini)

    captured_discover: dict[str, Any] = {}

    def fake_discover(query: str, client: Any, *, limit: int):
        captured_discover.update({"query": query, "client": client, "limit": limit})
        return ["Shared Topic", "Fallback Only"]

    monkeypatch.setattr(search_module, "discover_related_queries", fake_discover)

    def fake_log_search_run(**payload: Any) -> UUID:
        captured_discover["log_payload"] = payload
        return fake_run_id

    monkeypatch.setattr(search_module, "log_search_run", fake_log_search_run)

    result = search_module.run_search(
        "기초 학력 격차",
        client=fake_client,
        related_limit=3,
        crawl_limit=1,
        results_per_query=1,
        ai_model="custom-gemini",
        chunk_size=200,
    )

    assert isinstance(result, search_module.SearchRunResult)
    assert result.base_query == "기초 학력 격차"
    assert result.related_queries == ["Gemini Primary", "Shared Topic", "Fallback Only"]
    assert any(section.startswith("### 검색 플랜 요약") for section in result.sections)
    assert any("Gemini 연관 검색어" in section for section in result.sections)
    assert result.chunks and result.chunks[0].content == "crawled text"
    assert result.failures == ["crawl failure detected"]
    assert result.run_id == fake_run_id
    assert result.markdown == "\n\n".join(result.sections)

    assert captured_collect["urls"] == ["https://example.com/0"]
    assert captured_collect["chunk_size"] == 200
    assert "https://example.com/0" in captured_collect["metadata"]

    assert captured_gemini["query"] == "기초 학력 격차"
    assert captured_gemini["limit"] == 3
    assert captured_gemini["model"] == "custom-gemini"
    assert captured_gemini["prompt_template"] is None
    assert captured_gemini["context_samples"]

    assert captured_discover["client"] is fake_client
    assert captured_discover["limit"] == 3
    assert captured_discover["log_payload"]["base_query"] == "기초 학력 격차"

    call_counts = Counter(query for query, _ in fake_client.calls)
    assert call_counts["기초 학력 격차"] >= 1
    assert sum(call_counts.values()) == 6  # 3 base searches + 3 related follow-ups


def test_collect_agent_chunks_builds_agent_result(monkeypatch):
    """`collect_agent_chunks` should return an AgentChunkResult with crawl data."""

    fake_client = FakeTavilyClient()

    def fake_collect(client: Any, urls: list[str], metadata: dict[str, dict[str, str]], *, chunk_size: int):
        assert client is fake_client
        first_url = urls[0]
        meta = metadata[first_url]
        chunk = search_module.SearchChunk(
            query=meta.get("query", ""),
            source_label=meta.get("label", ""),
            url=first_url,
            title=meta.get("title", ""),
            chunk_index=1,
            content="agent chunk",
        )
        return [chunk], []

    monkeypatch.setattr(search_module, "_collect_crawled_chunks", fake_collect)
    monkeypatch.setattr(search_module, "gemini_generate", lambda *args, **kwargs: ["Gemini Agent"])
    monkeypatch.setattr(search_module, "discover_related_queries", lambda *args, **kwargs: [])

    result = search_module.collect_agent_chunks(
        "기초 학력",
        client=fake_client,
        related_limit=1,
        crawl_limit=1,
        results_per_query=1,
        chunk_size=200,
    )

    assert isinstance(result, search_module.AgentChunkResult)
    assert result.base_query == "기초 학력"
    assert result.related_queries == ["Gemini Agent"]
    assert result.failures == []
    assert result.chunks and result.chunks[0].content == "agent chunk"
    assert isinstance(result.object_id, UUID)
