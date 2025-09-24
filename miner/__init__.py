"""Miner package exposing utilities for bootstrapping the vector database."""

from .search import SearchRequest, build_search_plan, run_search
from .vector_db import VectorCollectionConfig, create_client, ensure_collection

__all__ = [
    "VectorCollectionConfig",
    "create_client",
    "ensure_collection",
    "SearchRequest",
    "build_search_plan",
    "run_search",
]
