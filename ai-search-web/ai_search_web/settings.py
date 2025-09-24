from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the ai-search web frontend."""

    es_host: Optional[str]
    es_username: Optional[str]
    es_password: Optional[str]
    es_index: str
    api_base_url: Optional[str]
    page_size: int


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_settings() -> Settings:
    return Settings(
        es_host=os.getenv("ES_HOST"),
        es_username=os.getenv("ES_USERNAME", None),
        es_password=os.getenv("ES_PASSWORD", None),
        es_index=os.getenv("ES_INDEX", "ai-search-reports"),
        api_base_url=os.getenv("AI_SEARCH_API"),
        page_size=_env_int("ES_PAGE_SIZE", 200),
    )


settings = load_settings()
