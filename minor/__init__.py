"""Minor package exposing utilities for embedding and vector storage."""

from .agent import AgentConfigurationError, AgentRunSummary, run_agent
from .docmodel import DocModel, build_docmodels
from .vector_db import VectorCollectionConfig, create_client, ensure_collection

__all__ = [
    "VectorCollectionConfig",
    "create_client",
    "ensure_collection",
    "DocModel",
    "build_docmodels",
    "run_agent",
    "AgentRunSummary",
    "AgentConfigurationError",
]


