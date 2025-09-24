from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from typing import List

from google.api_core import exceptions as google_exceptions
from langchain.agents import AgentExecutor
from langchain.globals import set_debug, set_verbose
from langchain_core.messages import AIMessage, HumanMessage

from charts_workflow.agents.builder import build_agent
from charts_workflow.config.settings import settings  # noqa: F401 - ensure env is loaded
from charts_workflow.core.plan_parser import extract_plan_steps, extract_search_queries
from charts_workflow.storage.report_manager import save_report
from charts_workflow.tools import DEFAULT_TOOLCHAIN, SEARCH_TOOL_PAIRS


def _initialise_agent(toolchain: Sequence) -> tuple:
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
    attempt_label="요청",
    max_attempts=5,
    initial_delay=2,
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
                raise RuntimeError(
                    f"Gemini 모델 과부하로 {attempt_label} 작업이 반복 실패했습니다. 잠시 후 다시 시도하거나 `GEMINI_MODEL`을 변경하세요."
                ) from exc
            wait_seconds = delay
            print(
                f"[경고] Gemini 모델 과부하로 {attempt_label}을(를) 재시도합니다. {wait_seconds}초 대기 후 재시도 ({attempt}/{max_attempts - 1})"
            )
            time.sleep(wait_seconds)
            delay = min(delay * 2, 30)
        except google_exceptions.GoogleAPIError as exc:
            message = getattr(exc, "message", str(exc))
            raise RuntimeError(f"Gemini API 호출에 실패했습니다: {message}") from exc
    raise RuntimeError(f"{attempt_label} 작업을 완료하지 못했습니다.")

def run_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI 분석가 콘솔 워크플로")
    parser.add_argument(
        "--report-format",
        choices=["md", "txt"],
        default="md",
        help="보고서 저장 형식",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="LangChain 디버그 모드를 활성화합니다.",
    )
    args = parser.parse_args(argv)

    if args.debug:
        set_debug(True)
        set_verbose(True)
        print("[디버그 모드] LangChain debug 로그가 활성화되었습니다.")

    tools = list(DEFAULT_TOOLCHAIN)
    planner, agent_executor = _initialise_agent(tools)

    chat_history: List[AIMessage | HumanMessage] = []
    print("안녕하세요! AI 분석가 워크플로가 준비되었습니다. 'exit'을 입력하면 종료합니다.")

    while True:
        question = input("질문: ").strip()
        if question.lower() == "exit":
            break
        if not question:
            continue

        analysis_plan = _invoke_with_backoff(
            planner.invoke,
            {
                "input": question,
                "chat_history": chat_history,
            },
            attempt_label="분석 계획 생성",
        )

        plan_steps = extract_plan_steps(analysis_plan)

        print("\n[분석 계획 초안]\n")
        print(analysis_plan)

        search_summaries: List[str] = []
        search_queries = extract_search_queries(analysis_plan)
        if search_queries:
            print("\n[검색 실행]\n")
            for query in search_queries:
                print(f"- {query}")
                section_lines = []
                for label, tool in SEARCH_TOOL_PAIRS:
                    try:
                        references = tool.invoke({"query": query})
                    except Exception as exc:  # noqa: BLE001 - display tool failure directly
                        references = f"검색 실패: {exc}"
                    print(f"  [{label}]")
                    print(references)
                    section_lines.append(f"#### {label}\n{references}")
                search_summaries.append(
                    f"### 검색 결과: {query}\n\n" + "\n\n".join(section_lines)
                )

        if search_summaries:
            chat_history.append(
                AIMessage(content="[외부 검색 결과]\n" + "\n\n".join(search_summaries))
            )

        if plan_steps:
            print("\n[단계별 사전 분석]\n")
            for step in plan_steps:
                step_prompt = (
                    "[단계별 조사 요청]\n"
                    f"{step}\n\n"
                    "위 단계의 목적을 달성하기 위해 필요한 추가 조사 노트를 bullet 중심으로 정리하세요. "
                    "최종 보고서(Part 1~IX)는 작성하지 말고, 근거, 참고 데이터, 활용할 도구 아이디어를 구체적으로 제안하세요."
                )
                print(f"- {step}")
                step_result = _invoke_with_backoff(
                    agent_executor.invoke,
                    {
                        "input": step_prompt,
                        "chat_history": chat_history,
                        "analysis_plan": analysis_plan,
                    },
                    attempt_label=f"단계별 분석 ({step})",
                )
                step_content = step_result["output"]
                chat_history.append(HumanMessage(content=step_prompt))
                chat_history.append(AIMessage(content=step_content))
                print(step_content)
                print()

        result = _invoke_with_backoff(
            agent_executor.invoke,
            {
                "input": question,
                "chat_history": chat_history,
                "analysis_plan": analysis_plan,
            },
            attempt_label="최종 리포트 생성",
        )

        content = result["output"]

        chat_history.append(HumanMessage(content=question))
        chat_history.append(AIMessage(content=content))
        save_report(question, content, report_format=args.report_format)

        print("\n[최종 분석 리포트]\n")
        print(content)


if __name__ == "__main__":
    run_cli()
