"""Miner package exposing utilities for bootstrapping the vector database."""

from .vector_db import VectorCollectionConfig, create_client, ensure_collection

__all__ = ["VectorCollectionConfig", "create_client", "ensure_collection"]
