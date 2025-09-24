from __future__ import annotations

import argparse
import os
from typing import Literal

from qdrant_client.http import models as qmodels

from agent import AgentConfigurationError, run_agent
from search import run_search
from vector_db import VectorCollectionConfig, create_client, ensure_collection

DistanceLiteral = Literal["cosine", "dot", "euclid"]


DISTANCE_MAP: dict[DistanceLiteral, qmodels.Distance] = {
    "cosine": qmodels.Distance.COSINE,
    "dot": qmodels.Distance.DOT,
    "euclid": qmodels.Distance.EUCLID,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Miner: Qdrant vector database bootstrapper. "
            "Ensures that a collection exists with the requested configuration."
        )
    )
    parser.add_argument(
        "--host",
        default=os.getenv("QDRANT_HOST", "localhost"),
        help="Host where the Qdrant service is reachable.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("QDRANT_PORT", "6333")),
        help="HTTP port exposed by the Qdrant service.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("QDRANT_API_KEY"),
        help="Optional API key if the Qdrant instance is secured.",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("MINER_COLLECTION", "miner-documents"),
        help="Name of the collection to ensure.",
    )
    parser.add_argument(
        "--vector-size",
        type=int,
        default=int(os.getenv("MINER_VECTOR_SIZE", "1536")),
        help="Dimensionality of the vectors that will be stored.",
    )
    parser.add_argument(
        "--distance",
        choices=list(DISTANCE_MAP),
        default=os.getenv("MINER_DISTANCE", "cosine"),
        help="Distance function used when comparing vectors.",
    )
    parser.add_argument(
        "--on-disk",
        action="store_true",
        help="Store vectors on disk instead of RAM for the target collection.",
    )
    parser.add_argument(
        "--mode",
        choices=["collection", "search", "agent"],
        default="collection",
        help=(
            "Operation mode: 'collection' ensures the Qdrant collection exists, "
            "'search' executes a Tavily web search plan, and 'agent' runs the "
            "Gemini-powered ingestion agent."
        ),
    )
    parser.add_argument(
        "--search-query",
        help="Query string used when running in search or agent mode.",
    )
    parser.add_argument(
        "--search-related-limit",
        type=int,
        default=int(os.getenv("MINER_SEARCH_RELATED_LIMIT", "5")),
        help="Maximum number of AI-discovered related queries to follow up.",
    )
    parser.add_argument(
        "--search-crawl-limit",
        type=int,
        default=int(os.getenv("MINER_SEARCH_CRAWL_LIMIT", "5")),
        help="Maximum number of result URLs to crawl for content extraction.",
    )
    parser.add_argument(
        "--search-results-per-query",
        type=int,
        default=int(os.getenv("MINER_SEARCH_RESULTS_PER_QUERY", "5")),
        help="Maximum number of top results to keep for each search query.",
    )
    parser.add_argument(
        "--search-ai-model",
        default=os.getenv("MINER_SEARCH_AI_MODEL"),
        help="Gemini model identifier used for related query expansion.",
    )
    parser.add_argument(
        "--search-chunk-size",
        type=int,
        default=int(os.getenv("MINER_SEARCH_CHUNK_SIZE", "500")),
        help="Character count for each content chunk generated during crawling.",
    )
    parser.add_argument(
        "--agent-embedding-model",
        default=os.getenv("MINER_AGENT_EMBEDDING_MODEL", "models/text-embedding-004"),
        help="Gemini embedding model used when storing chunks in Qdrant.",
    )
    return parser


def main(args: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args=args)

    if parsed.mode == "search":
        if not parsed.search_query:
            parser.error("--search-query is required when --mode=search")
        if parsed.search_related_limit < 0:
            parser.error("--search-related-limit must be non-negative")
        if parsed.search_crawl_limit < 0:
            parser.error("--search-crawl-limit must be non-negative")
        if parsed.search_results_per_query <= 0:
            parser.error("--search-results-per-query must be greater than zero")
        if parsed.search_chunk_size <= 0:
            parser.error("--search-chunk-size must be greater than zero")
        try:
            results = run_search(
                parsed.search_query,
                related_limit=parsed.search_related_limit,
                crawl_limit=parsed.search_crawl_limit,
                results_per_query=parsed.search_results_per_query,
                ai_model=parsed.search_ai_model,
                chunk_size=parsed.search_chunk_size,
            )
        except ValueError as exc:
            parser.error(str(exc))
        print(results)
        return

    if parsed.mode == "agent":
        if not parsed.search_query:
            parser.error("--search-query is required when --mode=agent")
        if parsed.search_related_limit < 0:
            parser.error("--search-related-limit must be non-negative")
        if parsed.search_crawl_limit < 0:
            parser.error("--search-crawl-limit must be non-negative")
        if parsed.search_results_per_query <= 0:
            parser.error("--search-results-per-query must be greater than zero")
        if parsed.search_chunk_size <= 0:
            parser.error("--search-chunk-size must be greater than zero")
        try:
            summary = run_agent(
                parsed.search_query,
                related_limit=parsed.search_related_limit,
                crawl_limit=parsed.search_crawl_limit,
                results_per_query=parsed.search_results_per_query,
                ai_model=parsed.search_ai_model,
                chunk_size=parsed.search_chunk_size,
                embedding_model=parsed.agent_embedding_model,
                qdrant_host=parsed.host,
                qdrant_port=parsed.port,
                qdrant_api_key=parsed.api_key,
                collection=parsed.collection,
                distance=DISTANCE_MAP[parsed.distance],
                on_disk=parsed.on_disk,
            )
        except (ValueError, AgentConfigurationError) as exc:
            parser.error(str(exc))
        print(summary.to_markdown())
        return

    client = create_client(parsed.host, parsed.port, parsed.api_key)

    config = VectorCollectionConfig(
        name=parsed.collection,
        vector_size=parsed.vector_size,
        distance=DISTANCE_MAP[parsed.distance],
        on_disk=parsed.on_disk,
    )

    created = ensure_collection(client, config)

    if created:
        print(
            f"Collection '{config.name}' created with size {config.vector_size} "
            f"and distance {parsed.distance}."
        )
    else:
        print(
            f"Collection '{config.name}' already exists. No action was necessary."
        )


if __name__ == "__main__":
    main()
