"""Command-line entry point for the Minor Search project."""

from __future__ import annotations

import argparse
import logging
import os
from typing import Iterable

from . import (
    AgentChunkResult,
    MinioSettings,
    create_minio_client,
    run_search,
    store_agent_chunks,
)


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
            "Runs focused searches, aggregates the results, and optionally "
            "stores agent-ready chunks in MinIO for Miner to consume."
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

    default_store = _env_flag("MINOR_SEARCH_STORE", True)
    parser.add_argument(
        "--store",
        dest="store",
        action="store_true",
        default=default_store,
        help="Store the resulting chunks in MinIO (default: enabled).",
    )
    parser.add_argument(
        "--no-store",
        dest="store",
        action="store_false",
        help="Skip uploading results to MinIO.",
    )
    parser.add_argument(
        "--object-name",
        help="Custom object name to use when uploading to MinIO.",
    )

    default_minio_secure = _env_flag("MINOR_SEARCH_MINIO_SECURE", False)
    parser.add_argument(
        "--minio-endpoint",
        default=os.getenv("MINOR_SEARCH_MINIO_ENDPOINT", "localhost:9000"),
        help="Endpoint for the MinIO deployment.",
    )
    parser.add_argument(
        "--minio-access-key",
        default=os.getenv("MINOR_SEARCH_MINIO_ACCESS_KEY", "minioadmin"),
        help="Access key for MinIO authentication.",
    )
    parser.add_argument(
        "--minio-secret-key",
        default=os.getenv("MINOR_SEARCH_MINIO_SECRET_KEY", "minioadmin"),
        help="Secret key for MinIO authentication.",
    )
    parser.add_argument(
        "--minio-bucket",
        default=os.getenv("MINOR_SEARCH_MINIO_BUCKET", "minor-search"),
        help="Bucket where search results are stored.",
    )
    parser.add_argument(
        "--minio-region",
        default=os.getenv("MINOR_SEARCH_MINIO_REGION"),
        help="Optional region for the MinIO bucket.",
    )
    parser.add_argument(
        "--minio-secure",
        dest="minio_secure",
        action="store_true",
        default=default_minio_secure,
        help="Use HTTPS for MinIO connections (default based on env).",
    )
    parser.add_argument(
        "--minio-insecure",
        dest="minio_secure",
        action="store_false",
        help="Force HTTP for MinIO connections.",
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

    if not parsed.store:
        return

    chunk_result = AgentChunkResult.from_run_result(search_result)
    settings = MinioSettings(
        endpoint=parsed.minio_endpoint,
        access_key=parsed.minio_access_key,
        secret_key=parsed.minio_secret_key,
        bucket=parsed.minio_bucket,
        secure=parsed.minio_secure,
        region=parsed.minio_region,
    )
    client = create_minio_client(settings)

    try:
        object_name = store_agent_chunks(
            client,
            settings,
            chunk_result,
            object_name=parsed.object_name,
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    print(f"\nMinIO 객체로 저장됨: s3://{settings.bucket}/{object_name}")


if __name__ == "__main__":
    main()
