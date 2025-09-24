from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from google.api_core import exceptions as google_exceptions
from langchain.agents import AgentExecutor
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ai_search.agents.builder import build_agent
from ai_search.core.plan_parser import extract_plan_steps, extract_search_queries
from ai_search.storage.report_manager import save_report
from ai_search.tools import DEFAULT_TOOLCHAIN, SEARCH_TOOL_PAIRS


class AnalysisError(RuntimeError):
    """Raised when an analysis request cannot be completed."""


@dataclass
class ToolSearchResult:
    """Container for a single tool's search output."""

    tool: str
    content: str


@dataclass
class SearchResult:
    """Represents aggregated search results for a single query."""

    query: str
    results: List[ToolSearchResult] = field(default_factory=list)


@dataclass
class StepResult:
    """Stores the outcome of an individual analysis step."""

    step: str
    prompt: str
    output: str


@dataclass
class AnalysisResult:
    """High level container returned after executing an analysis."""

    question: str
    analysis_plan: str
    search_results: List[SearchResult]
    step_results: List[StepResult]
    final_answer: str
    report_id: Optional[str]
    chat_history: List[BaseMessage]

    def to_dict(self) -> dict:
        """Convert the result into a JSON-serialisable dictionary."""

        return {
            "question": self.question,
            "analysis_plan": self.analysis_plan,
            "search_results": [
                {
                    "query": search.query,
                    "results": [
                        {"tool": result.tool, "content": result.content}
                        for result in search.results
                    ],
                }
                for search in self.search_results
            ],
            "step_results": [
                {
                    "step": step.step,
                    "prompt": step.prompt,
                    "output": step.output,
                }
                for step in self.step_results
            ],
            "final_answer": self.final_answer,
            "report_id": self.report_id,
        }


def _initialise_agent(toolchain: Sequence) -> tuple:
    """Create the planner chain and the agent executor."""

    planner, agent = build_agent(toolchain)
    executor = AgentExecutor(
        agent=agent,
        tools=list(toolchain),
        verbose=True,
        handle_parsing_errors=True,
    )
    return planner, executor


def _invoke_with_backoff(
    func,
    *args,
    attempt_label: str = "작업",
    max_attempts: int = 5,
    initial_delay: int = 2,
    **kwargs,
):
    """Retry Gemini calls on transient overload errors with exponential backoff."""

    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except (
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
        ) as exc:
            if attempt == max_attempts:
                raise AnalysisError(
                    f"{attempt_label} 수행 중 서비스 과부하가 지속되어 요청을 마칠 수 없습니다."
                ) from exc
            time.sleep(delay)
            delay = min(delay * 2, 30)
        except google_exceptions.GoogleAPIError as exc:
            message = getattr(exc, "message", str(exc))
            raise AnalysisError(f"Gemini API 호출 중 오류가 발생했습니다: {message}") from exc
    raise AnalysisError(f"{attempt_label} 수행에 반복적으로 실패했습니다.")


class AnalysisEngine:
    """Coordinator that orchestrates planning, search and reporting."""

    def __init__(self, toolchain: Sequence | None = None):
        self._toolchain = list(toolchain or DEFAULT_TOOLCHAIN)
        self._planner, self._agent_executor = _initialise_agent(self._toolchain)
        self._chat_history: List[BaseMessage] = []

    @property
    def chat_history(self) -> List[BaseMessage]:
        """Return the accumulated chat history."""

        return list(self._chat_history)

    def reset(self) -> None:
        """Clear the internal chat history."""

        self._chat_history.clear()

    def run(
        self,
        question: str,
        *,
        report_format: str = "md",
        persist_report: bool = True,
    ) -> AnalysisResult:
        """Execute the full analysis workflow for the supplied question."""

        cleaned_question = question.strip()
        if not cleaned_question:
            raise ValueError("질문을 입력해 주세요.")

        analysis_plan = _invoke_with_backoff(
            self._planner.invoke,
            {
                "input": cleaned_question,
                "chat_history": self._chat_history,
            },
            attempt_label="분석 계획",
        )

        plan_steps = extract_plan_steps(analysis_plan)
        search_queries = extract_search_queries(analysis_plan)

        search_results: List[SearchResult] = []
        search_sections: List[str] = []

        if search_queries:
            for query in search_queries:
                tool_outputs: List[ToolSearchResult] = []
                section_lines: List[str] = []
                for label, tool in SEARCH_TOOL_PAIRS:
                    try:
                        references = tool.invoke({"query": query})
                    except Exception as exc:  # noqa: BLE001 - surface tool failure directly
                        references = f"검색 실패: {exc}"
                    tool_outputs.append(ToolSearchResult(tool=label, content=references))
                    section_lines.append(f"#### {label}\n{references}")

                search_results.append(SearchResult(query=query, results=tool_outputs))
                search_sections.append(
                    f"### 검색: {query}\n\n" + "\n\n".join(section_lines)
                )

        if search_sections:
            self._chat_history.append(
                AIMessage(content="[참고 검색]\n" + "\n\n".join(search_sections))
            )

        step_results: List[StepResult] = []
        for step in plan_steps:
            step_prompt = (
                "[세부 분석 요청]\n"
                f"{step}\n\n"
                "위 지침을 토대로 상세한 분석 결과를 bullet 형식으로 정리해 주세요. "
                "필요하다면 Part 1~IX 구획, 표, 코드 등을 적극적으로 활용하세요."
            )

            step_result = _invoke_with_backoff(
                self._agent_executor.invoke,
                {
                    "input": step_prompt,
                    "chat_history": self._chat_history,
                    "analysis_plan": analysis_plan,
                },
                attempt_label=f"세부 분석 ({step})",
            )

            step_output = step_result["output"]
            self._chat_history.append(HumanMessage(content=step_prompt))
            self._chat_history.append(AIMessage(content=step_output))
            step_results.append(StepResult(step=step, prompt=step_prompt, output=step_output))

        final_result = _invoke_with_backoff(
            self._agent_executor.invoke,
            {
                "input": cleaned_question,
                "chat_history": self._chat_history,
                "analysis_plan": analysis_plan,
            },
            attempt_label="최종 보고서",
        )

        final_answer = final_result["output"]
        self._chat_history.append(HumanMessage(content=cleaned_question))
        self._chat_history.append(AIMessage(content=final_answer))

        report_id = None
        if persist_report:
            report_id = save_report(
                cleaned_question,
                final_answer,
                report_format=report_format,
            )

        return AnalysisResult(
            question=cleaned_question,
            analysis_plan=analysis_plan,
            search_results=search_results,
            step_results=step_results,
            final_answer=final_answer,
            report_id=report_id,
            chat_history=self.chat_history,
        )


__all__ = [
    "AnalysisEngine",
    "AnalysisError",
    "AnalysisResult",
    "SearchResult",
    "StepResult",
    "ToolSearchResult",
]

