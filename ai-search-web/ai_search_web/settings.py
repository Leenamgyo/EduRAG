from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Configuration values for the ai-search web UI."""

    reports_dir: Path
    google_api_key: Optional[str]
    openai_api_key: Optional[str]
    tavily_api_key: Optional[str]


def _default_reports_dir() -> Path:
    candidate = os.getenv("REPORTS_DIR") or os.path.join("..", "ai-search", "reports")
    return Path(candidate).resolve()


def load_settings() -> Settings:
    return Settings(
        reports_dir=_default_reports_dir(),
        google_api_key=os.getenv("GOOGLE_API_KEY") or os.getenv("GENAI_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
    )


settings = load_settings()
