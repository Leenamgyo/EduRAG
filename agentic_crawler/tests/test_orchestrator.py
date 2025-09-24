"""Tests for the agentic crawler orchestrator."""

from __future__ import annotations

from typing import List

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agentic_crawler.orchestrator import AgenticCrawler
from agentic_crawler.tools import (
    create_openalex_tool,
    create_semantic_scholar_tool,
    create_tavily_tool,
)
from agentic_crawler.tools.openalex_client import OpenAlexWork
from agentic_crawler.tools.semantic_scholar_client import SemanticScholarPaper
from agentic_crawler.tools.tavily_client import TavilyResult


class RecordingLLM(BaseChatModel):
    """A deterministic chat model used to capture prompts."""

    def __init__(self, response: str) -> None:
        super().__init__()
        self._response = response
        self.calls: List[List[BaseMessage]] = []

    @property
    def _llm_type(self) -> str:
        return "recording-llm"

    def _generate(self, messages: List[BaseMessage], stop=None, **kwargs) -> ChatResult:
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._response))])


class StubOpenAlexClient:
    def __init__(self) -> None:
        self.queries = []

    def search_works(self, query: str, per_page: int = 5):
        self.queries.append((query, per_page))
        return [
            OpenAlexWork(
                id="id",
                title="OpenAlex Paper",
                published_year=2024,
                doi=None,
                cited_by_count=1,
                authors=["Alice"],
                abstract="Abstract",
            )
        ]


class StubSemanticScholarClient:
    def __init__(self) -> None:
        self.queries = []

    def search_papers(self, query: str, limit: int = 5):
        self.queries.append((query, limit))
        return [
            SemanticScholarPaper(
                paper_id="id",
                title="Semantic Paper",
                abstract="Abstract",
                year=2023,
                authors=["Bob"],
                url="https://example.com",
            )
        ]


class StubTavilyClient:
    def __init__(self) -> None:
        self.queries = []

    def search(self, query: str, max_results: int = 5):
        self.queries.append((query, max_results))
        return [
            TavilyResult(
                title="Web Result",
                url="https://example.org",
                content="Snippet",
            )
        ]


def test_agentic_crawler_runs_with_stubbed_clients():
    openalex_client = StubOpenAlexClient()
    semantic_client = StubSemanticScholarClient()
    tavily_client = StubTavilyClient()

    openalex_tool = create_openalex_tool(openalex_client, per_page=1)
    semantic_tool = create_semantic_scholar_tool(semantic_client, limit=1)
    tavily_tool = create_tavily_tool(tavily_client, max_results=1)

    llm = RecordingLLM(response="final answer")
    crawler = AgenticCrawler(
        openalex_tool=openalex_tool,
        semantic_scholar_tool=semantic_tool,
        tavily_tool=tavily_tool,
        llm=llm,
    )

    result = crawler.run("graph rag")

    assert result == "final answer"
    assert openalex_client.queries == [("graph rag", 1)]
    assert semantic_client.queries == [("graph rag", 1)]
    assert tavily_client.queries == [("graph rag", 1)]
    assert llm.calls, "LLM should have been invoked"
    human_messages = [msg for msg in llm.calls[0] if msg.type == "human"]
    assert human_messages, "Prompt should include a human message"
    assert "graph rag" in human_messages[0].content


def test_agentic_crawler_requires_query():
    crawler = AgenticCrawler(
        openalex_tool=create_openalex_tool(StubOpenAlexClient()),
        semantic_scholar_tool=create_semantic_scholar_tool(StubSemanticScholarClient()),
        tavily_tool=create_tavily_tool(StubTavilyClient()),
        llm=RecordingLLM(response="answer"),
    )
    with pytest.raises(ValueError):
        crawler.run("")
