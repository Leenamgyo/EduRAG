"""Gemini helper utilities for Miner search workflows."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable, List, Sequence

try:  # Optional dependency – configured only when available.
    import google.generativeai as genai
except Exception:  # pragma: no cover - optional at runtime.
    genai = None  # type: ignore[assignment]


DEFAULT_MODEL = "gemini-1.5-flash"


class GeminiUnavailableError(RuntimeError):
    """Raised when Gemini is requested but dependencies or keys are missing."""


@lru_cache(maxsize=1)
def _configure_client(api_key: str | None) -> None:
    if genai is None:  # pragma: no cover - depends on optional dependency.
        raise GeminiUnavailableError(
            "google-generativeai package is required for Gemini features."
        )

    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise GeminiUnavailableError("GEMINI_API_KEY environment variable is not set.")

    genai.configure(api_key=key)


def _coerce_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw in text.splitlines():
        cleaned = raw.strip(" -\t")
        if cleaned:
            lines.append(cleaned)
    return lines


def generate_related_queries(
    seed_query: str,
    *,
    limit: int,
    model: str | None = None,
    context_samples: Sequence[str] | None = None,
    api_key: str | None = None,
) -> List[str]:
    """Use Gemini to generate a list of related search queries."""

    if limit <= 0:
        return []

    chosen_model = model or os.getenv("MINER_GEMINI_MODEL") or DEFAULT_MODEL

    try:
        _configure_client(api_key)
    except GeminiUnavailableError:
        return []

    prompt_sections: List[str] = [
        "당신은 검색 전략을 설계하는 전문가입니다.",
        "다음의 기준 검색어를 확장하여 서로 다른 각도로 접근할 수 있는 관련 검색어를 만들어 주세요.",
        "출력 형식은 번호 없이 한 줄당 하나의 검색어만 포함하도록 하세요.",
        f"기준 검색어: {seed_query.strip()}",
    ]

    if context_samples:
        formatted_context = "\n".join(context_samples[: 2 * limit])
        prompt_sections.append("참고 문맥:\n" + formatted_context)

    prompt_sections.append(f"최대 {limit}개의 검색어를 반환하세요.")

    prompt = "\n\n".join(prompt_sections)

    try:
        model_client = genai.GenerativeModel(chosen_model)
        response = model_client.generate_content(prompt)
    except Exception:  # pragma: no cover - external API call
        return []

    text = getattr(response, "text", "") or ""
    if not text and getattr(response, "candidates", None):  # pragma: no cover - fallback
        for candidate in response.candidates:
            for part in getattr(candidate.content, "parts", []):
                value = getattr(part, "text", None)
                if value:
                    text += value + "\n"

    candidates = _coerce_lines(text)

    normalized: List[str] = []
    seen: set[str] = set()
    base = seed_query.strip().lower()
    for candidate in candidates:
        lowered = candidate.lower()
        if lowered == base or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(candidate)
        if len(normalized) >= limit:
            break

    return normalized


__all__: Iterable[str] = ["generate_related_queries", "GeminiUnavailableError"]
