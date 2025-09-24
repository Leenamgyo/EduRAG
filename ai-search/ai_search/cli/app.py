from __future__ import annotations

import argparse

from langchain.globals import set_debug, set_verbose

from ai_search.config.settings import settings  # noqa: F401 - ensure env is loaded
from ai_search.core.analysis_engine import AnalysisEngine, AnalysisError


def run_cli(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AI 논문 분석 도우미 CLI")
    parser.add_argument(
        "--report-format",
        choices=["md", "txt"],
        default="md",
        help="결과 보고서를 저장할 형식",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="LangChain 디버그 출력을 활성화합니다.",
    )
    args = parser.parse_args(argv)

    if args.debug:
        set_debug(True)
        set_verbose(True)
        print("[안내] LangChain debug 모드가 활성화되었습니다.")

    engine = AnalysisEngine()

    print("안녕하세요! AI 논문 분석 CLI입니다. 'exit' 을 입력하면 종료합니다.")

    while True:
        question = input(": ").strip()
        if question.lower() == "exit":
            break
        if not question:
            continue

        try:
            result = engine.run(
                question,
                report_format=args.report_format,
                persist_report=True,
            )
        except ValueError as exc:
            print(f"[경고] {exc}")
            continue
        except AnalysisError as exc:
            print(f"[오류] {exc}")
            continue

        print("\n[분석 계획 초안]\n")
        print(result.analysis_plan)

        if result.search_results:
            print("\n[검색 결과]\n")
            for search in result.search_results:
                print(f"- {search.query}")
                for tool_output in search.results:
                    print(f"  [{tool_output.tool}]")
                    print(tool_output.content)

        if result.step_results:
            print("\n[세부 단계 분석]\n")
            for step in result.step_results:
                print(f"- {step.step}")
                print(step.output)
                print()

        print("\n[최종 보고서]\n")
        print(result.final_answer)


if __name__ == "__main__":
    run_cli()
