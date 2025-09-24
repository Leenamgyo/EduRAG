from __future__ import annotations

import argparse
import os
from typing import Literal

from qdrant_client.http import models as qmodels

from miner.vector_db import VectorCollectionConfig, create_client, ensure_collection

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
    return parser


def main(args: list[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args=args)

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
