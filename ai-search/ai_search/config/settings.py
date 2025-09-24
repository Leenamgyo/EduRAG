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
    )


settings = load_settings()
