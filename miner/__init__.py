"""Miner package exposing utilities for bootstrapping the vector database."""

from .agent import AgentConfigurationError, AgentRunSummary, run_agent
from .gemini import generate_related_queries
from .docmodel import DocModel, build_docmodels
from .search import (
    AgentChunkResult,
    SearchChunk,
    SearchHit,
    SearchRequest,
    build_search_plan,
    collect_agent_chunks,
    run_search,
)
from .vector_db import VectorCollectionConfig, create_client, ensure_collection

__all__ = [
    "VectorCollectionConfig",
    "create_client",
    "ensure_collection",
    "SearchRequest",
    "SearchHit",
    "SearchChunk",
    "AgentChunkResult",
    "DocModel",
    "build_docmodels",
    "build_search_plan",
    "collect_agent_chunks",
    "run_search",
    "generate_related_queries",
    "run_agent",
    "AgentRunSummary",
    "AgentConfigurationError",
]


