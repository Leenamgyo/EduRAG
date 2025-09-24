from __future__ import annotations

import argparse
import logging
import os
from typing import Literal

from qdrant_client.http import models as qmodels

from agent import AgentConfigurationError, run_agent
from minor_search import MinioSettings, create_minio_client, load_agent_chunks
from vector_db import VectorCollectionConfig, create_client, ensure_collection

DistanceLiteral = Literal["cosine", "dot", "euclid"]


DISTANCE_MAP: dict[DistanceLiteral, qmodels.Distance] = {
    "cosine": qmodels.Distance.COSINE,
    "dot": qmodels.Distance.DOT,
    "euclid": qmodels.Distance.EUCLID,
}


def _env_flag(name: str, *, default: bool) -> bool:
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
            "Miner: Qdrant vector database bootstrapper and embedding worker. "
            "Ensures that a collection exists with the requested configuration "
            "and ingests Minor Search results from MinIO."
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
        choices=["collection", "agent"],
        default="collection",
        help=(
            "Operation mode: 'collection' ensures the Qdrant collection exists, "
            "'agent' consumes Minor Search results from MinIO and stores embeddings."
        ),
    )
    parser.add_argument(
        "--agent-embedding-model",
        default=os.getenv("MINER_AGENT_EMBEDDING_MODEL", "models/text-embedding-004"),
        help="Primary Gemini embedding model used when storing chunks in Qdrant.",
    )
    parser.add_argument(
        "--agent-embedding-model-secondary",
        default=os.getenv("MINER_AGENT_EMBEDDING_MODEL_SECONDARY"),
        help="Optional secondary Gemini embedding model stored alongside the primary vectors.",
    )
    default_debug = _env_flag("MINER_DEBUG", default=True)
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
        help="Disable debug logging even if MINER_DEBUG is set.",
    )

    default_minio_secure = _env_flag("MINOR_SEARCH_MINIO_SECURE", default=False)
    parser.add_argument(
        "--minio-endpoint",
        default=os.getenv("MINOR_SEARCH_MINIO_ENDPOINT", "localhost:9000"),
        help="Endpoint for the MinIO server hosting search results.",
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
        help="Bucket containing stored Minor Search results.",
    )
    parser.add_argument(
        "--minio-region",
        default=os.getenv("MINOR_SEARCH_MINIO_REGION"),
        help="Optional MinIO/S3 region name.",
    )
    parser.add_argument(
        "--minio-secure",
        dest="minio_secure",
        action="store_true",
        default=default_minio_secure,
        help="Use HTTPS when connecting to MinIO (default based on env).",
    )
    parser.add_argument(
        "--minio-insecure",
        dest="minio_secure",
        action="store_false",
        help="Force HTTP when connecting to MinIO.",
    )
    parser.add_argument(
        "--search-object",
        help="MinIO object key containing a stored Minor Search chunk result.",
    )

    return parser


def main(args: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args=args)

    _configure_logging(parsed.debug)

    if parsed.mode == "agent":
        if not parsed.search_object:
            parser.error("--search-object is required when --mode=agent")

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
            chunk_result = load_agent_chunks(client, settings, parsed.search_object)
        except RuntimeError as exc:
            parser.error(str(exc))

        try:
            summary = run_agent(
                chunk_result,
                embedding_model=parsed.agent_embedding_model,
                embedding_model_secondary=parsed.agent_embedding_model_secondary,
                qdrant_host=parsed.host,
                qdrant_port=parsed.port,
                qdrant_api_key=parsed.api_key,
                collection=parsed.collection,
                distance=DISTANCE_MAP[parsed.distance],
                on_disk=parsed.on_disk,
            )
        except AgentConfigurationError as exc:
            parser.error(str(exc))
        print(summary.to_markdown())
        if summary.run_id:
            print(f"\n실행 로그 ID: {summary.run_id}")
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
