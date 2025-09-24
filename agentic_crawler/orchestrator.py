"""Main orchestrator for the agentic crawler."""

from __future__ import annotations

from typing import Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough
from langchain_core.tools import StructuredTool

try:  # pragma: no cover - optional during tests
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - handled gracefully at runtime
    ChatGoogleGenerativeAI = None  # type: ignore[assignment]

from .tools import (
    create_openalex_tool,
    create_semantic_scholar_tool,
    create_tavily_tool,
)


class AgenticCrawler:
    """LangChain-based orchestrator that coordinates multiple research tools."""

    def __init__(
        self,
        *,
        openalex_tool: Optional[StructuredTool] = None,
        semantic_scholar_tool: Optional[StructuredTool] = None,
        tavily_tool: Optional[StructuredTool] = None,
        llm: Optional[object] = None,
        max_results: int = 5,
        verbose: bool = False,
    ) -> None:
        self._max_results = max_results
        self._openalex_tool = openalex_tool or create_openalex_tool(per_page=max_results)
        self._semantic_tool = (
            semantic_scholar_tool or create_semantic_scholar_tool(limit=max_results)
        )
        self._tavily_tool = tavily_tool or create_tavily_tool(max_results=max_results)

        if llm is not None:
            self._llm = llm
        else:
            if ChatGoogleGenerativeAI is None:
                raise ImportError(
                    "langchain_google_genai is required when no llm instance is provided"
                )
            self._llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=0.2,
            )

        self._prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a meticulous research assistant. Use the provided context to craft a concise research brief with citations when possible.",
                ),
                (
                    "human",
                    """User question: {input}\n\nOpenAlex findings:\n{openalex_summary}\n\nSemantic Scholar findings:\n{semantic_scholar_summary}\n\nTavily findings:\n{tavily_summary}\n\nGenerate a synthesized answer in Korean and list concrete references if available.""",
                ),
            ]
        )

        gather = RunnableParallel(
            input=RunnablePassthrough(),
            openalex_summary=RunnableLambda(self._run_openalex_tool),
            semantic_scholar_summary=RunnableLambda(self._run_semantic_tool),
            tavily_summary=RunnableLambda(self._run_tavily_tool),
        )

        agent = create_tool_calling_agent(
            self._llm,
            [self._openalex_tool, self._semantic_tool, self._tavily_tool],
            self._prompt,
        )
        self._executor = AgentExecutor(
            agent=agent,
            tools=[self._openalex_tool, self._semantic_tool, self._tavily_tool],
            verbose=verbose,
        )
        self._gather = gather

    def _run_openalex_tool(self, query: str) -> str:
        return self._openalex_tool.invoke({"query": query})

    def _run_semantic_tool(self, query: str) -> str:
        return self._semantic_tool.invoke({"query": query})

    def _run_tavily_tool(self, query: str) -> str:
        return self._tavily_tool.invoke({"query": query})

    def run(self, query: str) -> str:
        """Execute the full research workflow and return the synthesized answer."""

        if not query:
            raise ValueError("query must not be empty")

        gathered = self._gather.invoke(query)
        result = self._executor.invoke(gathered)
        output = result.get("output") if isinstance(result, dict) else result
        if hasattr(output, "content"):
            return output.content  # type: ignore[return-value]
        return str(output)


__all__ = ["AgenticCrawler"]
