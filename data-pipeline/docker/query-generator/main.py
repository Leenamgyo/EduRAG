"""Query generator container for the Gemini-based pipeline."""

from __future__ import annotations

import json
import os
from typing import Iterable, List


def normalize_topics(topics: Iterable[str]) -> List[str]:
    """Normalize topic names by stripping whitespace and dropping empties."""

    return [topic.strip() for topic in topics if topic and topic.strip()]


def build_queries(topics: Iterable[str]) -> List[str]:
    """Create deterministic placeholder queries for the Gemini model."""

    normalized = normalize_topics(topics)
    return [f"{topic} education research insights" for topic in normalized]


def main() -> None:
    topics = normalize_topics(os.getenv("SEED_TOPICS", "").split(","))
    model = os.getenv("GEMINI_MODEL", "gemini-pro")
    queries = build_queries(topics)
    payload = {"model": model, "queries": queries}
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
