from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Container for environment-driven settings."""

    google_api_key: Optional[str]
    openai_api_key: Optional[str]
    tavily_api_key: Optional[str]
    model_name: str
    reports_dir: Path
    es_host: Optional[str]
    es_username: Optional[str]
    es_password: Optional[str]
    es_index: str
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: Optional[str]
    qdrant_collection: str
    qdrant_top_k: int
    qdrant_score_threshold: Optional[float]
    embedding_model: str


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)


def _float_env(name: str) -> Optional[float]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    return float(raw)


def load_settings() -> Settings:
    """Load settings from the current environment."""
    return Settings(
        google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        model_name=(
            os.getenv("GEMINI_MODEL")
            or os.getenv("MODEL")
            or "gemini-2.0-flash-thinking-exp"
        ),
        reports_dir=Path(os.getenv("REPORTS_DIR", "reports")).resolve(),
        es_host=os.getenv("ES_HOST"),
        es_username=os.getenv("ES_USERNAME"),
        es_password=os.getenv("ES_PASSWORD"),
        es_index=os.getenv("ES_INDEX", "ai-search-reports"),
        qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
        qdrant_port=_int_env("QDRANT_PORT", 6333),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "miner-documents"),
        qdrant_top_k=_int_env("QDRANT_TOP_K", 5),
        qdrant_score_threshold=_float_env("QDRANT_SCORE_THRESHOLD"),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-large"),
    )


settings = load_settings()
