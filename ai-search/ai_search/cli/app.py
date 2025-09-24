from __future__ import annotations

import argparse
import time
from collections.abc import Sequence
from typing import List

from google.api_core import exceptions as google_exceptions
from langchain.agents import AgentExecutor
from langchain.globals import set_debug, set_verbose
from langchain_core.messages import AIMessage, HumanMessage

from ai_search.agents.builder import build_agent
from ai_search.config.settings import settings  # noqa: F401 - ensure env is loaded
from ai_search.core.plan_parser import extract_plan_steps, extract_search_queries
from ai_search.storage.report_manager import save_report
from ai_search.tools import DEFAULT_TOOLCHAIN, SEARCH_TOOL_PAIRS


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
    attempt_label="��û",
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
                    f"Gemini �� �����Ϸ� {attempt_label} �۾��� �ݺ� �����߽��ϴ�. ��� �� �ٽ� �õ��ϰų� `GEMINI_MODEL`�� �����ϼ���."
                ) from exc
            wait_seconds = delay
            print(
                f"[���] Gemini �� �����Ϸ� {attempt_label}��(��) ��õ��մϴ�. {wait_seconds}�� ��� �� ��õ� ({attempt}/{max_attempts - 1})"
            )
            time.sleep(wait_seconds)
            delay = min(delay * 2, 30)
        except google_exceptions.GoogleAPIError as exc:
            message = getattr(exc, "message", str(exc))
            raise RuntimeError(f"Gemini API ȣ�⿡ �����߽��ϴ�: {message}") from exc
    raise RuntimeError(f"{attempt_label} �۾��� �Ϸ����� ���߽��ϴ�.")

def run_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI �м��� �ܼ� ��ũ�÷�")
    parser.add_argument(
        "--report-format",
        choices=["md", "txt"],
        default="md",
        help="���� ���� ����",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="LangChain ����� ��带 Ȱ��ȭ�մϴ�.",
    )
    args = parser.parse_args(argv)

    if args.debug:
        set_debug(True)
        set_verbose(True)
        print("[����� ���] LangChain debug �αװ� Ȱ��ȭ�Ǿ����ϴ�.")

    tools = list(DEFAULT_TOOLCHAIN)
    planner, agent_executor = _initialise_agent(tools)

    chat_history: List[AIMessage | HumanMessage] = []
    print("�ȳ��ϼ���! AI �м��� ��ũ�÷ΰ� �غ�Ǿ����ϴ�. 'exit'�� �Է��ϸ� �����մϴ�.")

    while True:
        question = input("����: ").strip()
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
            attempt_label="�м� ��ȹ ����",
        )

        plan_steps = extract_plan_steps(analysis_plan)

        print("\n[�м� ��ȹ �ʾ�]\n")
        print(analysis_plan)

        search_summaries: List[str] = []
        search_queries = extract_search_queries(analysis_plan)
        if search_queries:
            print("\n[�˻� ����]\n")
            for query in search_queries:
                print(f"- {query}")
                section_lines = []
                for label, tool in SEARCH_TOOL_PAIRS:
                    try:
                        references = tool.invoke({"query": query})
                    except Exception as exc:  # noqa: BLE001 - display tool failure directly
                        references = f"�˻� ����: {exc}"
                    print(f"  [{label}]")
                    print(references)
                    section_lines.append(f"#### {label}\n{references}")
                search_summaries.append(
                    f"### �˻� ���: {query}\n\n" + "\n\n".join(section_lines)
                )

        if search_summaries:
            chat_history.append(
                AIMessage(content="[�ܺ� �˻� ���]\n" + "\n\n".join(search_summaries))
            )

        if plan_steps:
            print("\n[�ܰ躰 ���� �м�]\n")
            for step in plan_steps:
                step_prompt = (
                    "[�ܰ躰 ���� ��û]\n"
                    f"{step}\n\n"
                    "�� �ܰ��� ������ �޼��ϱ� ���� �ʿ��� �߰� ���� ��Ʈ�� bullet �߽����� �����ϼ���. "
                    "���� ����(Part 1~IX)�� �ۼ����� ����, �ٰ�, ���� ������, Ȱ���� ���� ���̵� ��ü������ �����ϼ���."
                )
                print(f"- {step}")
                step_result = _invoke_with_backoff(
                    agent_executor.invoke,
                    {
                        "input": step_prompt,
                        "chat_history": chat_history,
                        "analysis_plan": analysis_plan,
                    },
                    attempt_label=f"�ܰ躰 �м� ({step})",
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
            attempt_label="���� ����Ʈ ����",
        )

        content = result["output"]

        chat_history.append(HumanMessage(content=question))
        chat_history.append(AIMessage(content=content))
        save_report(question, content, report_format=args.report_format)

        print("\n[���� �м� ����Ʈ]\n")
        print(content)


if __name__ == "__main__":
    run_cli()
