"""Utility helpers for interacting with the Qdrant vector database."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


@dataclass
class VectorCollectionConfig:
    """Configuration for a collection to be created in Qdrant."""

    name: str
    vector_size: int
    distance: qmodels.Distance = qmodels.Distance.COSINE
    on_disk: bool = False

    def to_vector_params(self) -> qmodels.VectorParams:
        """Convert the configuration to ``VectorParams`` understood by Qdrant."""

        return qmodels.VectorParams(
            size=self.vector_size,
            distance=self.distance,
            on_disk=self.on_disk,
        )


def create_client(host: str, port: int, api_key: Optional[str] = None) -> QdrantClient:
    """Create a ``QdrantClient`` from the provided connection information."""

    return QdrantClient(host=host, port=port, api_key=api_key)


def ensure_collection(client: QdrantClient, config: VectorCollectionConfig) -> bool:
    """Ensure that a collection exists, creating it if necessary.

    Args:
        client: The Qdrant client to use for operations.
        config: Desired collection configuration.

    Returns:
        ``True`` if a collection was created, ``False`` if it already existed.
    """

    if client.collection_exists(config.name):
        return False

    client.create_collection(
        collection_name=config.name,
        vectors_config=config.to_vector_params(),
    )
    return True
