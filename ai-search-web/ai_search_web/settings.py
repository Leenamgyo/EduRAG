from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Configuration values for the ai-search web UI."""

    google_api_key: Optional[str]
    openai_api_key: Optional[str]
    tavily_api_key: Optional[str]
    es_host: Optional[str]
    es_username: Optional[str]
    es_password: Optional[str]
    es_index: str


def load_settings() -> Settings:
    return Settings(
        google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        es_host=os.getenv("ES_HOST"),
        es_username=os.getenv("ES_USERNAME"),
        es_password=os.getenv("ES_PASSWORD"),
        es_index=os.getenv("ES_INDEX", "ai-search-reports"),
    )


settings = load_settings()
