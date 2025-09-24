"""Command-line entry point for the Minor Search project."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Iterable

from . import run_search


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Minor Search: Tavily + Gemini powered research orchestrator. "
            "Runs focused searches and aggregates the results with agent-ready "
            "chunks for downstream pipelines."
        )
    )
    parser.add_argument("query", help="Seed query string that drives the search plan.")
    parser.add_argument(
        "--related-limit",
        type=int,
        default=int(os.getenv("MINOR_SEARCH_RELATED_LIMIT", "5")),
        help="Number of related queries to request from Gemini.",
    )
    parser.add_argument(
        "--crawl-limit",
        type=int,
        default=int(os.getenv("MINOR_SEARCH_CRAWL_LIMIT", "5")),
        help="Maximum number of URLs to crawl for detailed content extraction.",
    )
    parser.add_argument(
        "--results-per-query",
        type=int,
        default=int(os.getenv("MINOR_SEARCH_RESULTS_PER_QUERY", "5")),
        help="Number of Tavily results to keep per query.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.getenv("MINOR_SEARCH_CHUNK_SIZE", "500")),
        help="Character count for each extracted chunk.",
    )
    parser.add_argument(
        "--ai-model",
        default=os.getenv("MINOR_SEARCH_AI_MODEL"),
        help="Optional Gemini model identifier used for related query generation.",
    )
    parser.add_argument(
        "--ai-prompt",
        default=os.getenv("MINOR_SEARCH_AI_PROMPT"),
        help="Override prompt template for Gemini related query generation.",
    )

    default_debug = _env_flag("MINOR_SEARCH_DEBUG", True)
    parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=default_debug,
        help="Enable verbose debug logging (default: enabled).",
    )
    parser.add_argument(
        "--no-debug",
        dest="debug",
        action="store_false",
        help="Disable debug logging.",
    )

    return parser


def main(args: Iterable[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args=args)

    _configure_logging(parsed.debug)

    if parsed.related_limit < 0:
        parser.error("--related-limit must be non-negative")
    if parsed.crawl_limit < 0:
        parser.error("--crawl-limit must be non-negative")
    if parsed.results_per_query <= 0:
        parser.error("--results-per-query must be greater than zero")
    if parsed.chunk_size <= 0:
        parser.error("--chunk-size must be greater than zero")

    try:
        search_result = run_search(
            parsed.query,
            related_limit=parsed.related_limit,
            crawl_limit=parsed.crawl_limit,
            results_per_query=parsed.results_per_query,
            ai_model=parsed.ai_model,
            ai_prompt=parsed.ai_prompt,
            chunk_size=parsed.chunk_size,
        )
    except ValueError as exc:
        parser.error(str(exc))

    print(search_result.to_markdown())
    if search_result.run_id:
        print(f"\n실행 로그 ID: {search_result.run_id}")


if __name__ == "__main__":
    main()
