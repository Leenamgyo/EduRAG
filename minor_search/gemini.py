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

DEFAULT_RELATED_QUERY_PROMPT = """
당신은 교육 및 학습 도메인에서 활용할 RAG 데이터베이스를 구축하는 정보 검색 전략가입니다.
기준 검색어를 다양한 관점에서 확장하여 수집할 가치가 높은 관련 검색어 후보를 제안하세요.
각 검색어는 실질적인 조사 주제가 되도록 12자 이상 48자 이하의 구체적인 표현으로 작성합니다.
검색어는 번호나 불릿 없이 한 줄에 하나씩만 작성하며, 한국어와 영어를 혼합해도 괜찮습니다.
기준 검색어: {seed_query}
{context_block}
최대 {limit}개의 검색어만 반환하세요.
"""


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


def _build_related_prompt(
    seed_query: str,
    *,
    limit: int,
    context_samples: Sequence[str] | None,
    prompt_template: str | None,
) -> str:
    template = (
        prompt_template
        or os.getenv("MINOR_SEARCH_RELATED_PROMPT")
        or os.getenv("MINER_GEMINI_RELATED_PROMPT")
        or DEFAULT_RELATED_QUERY_PROMPT
    )

    context_block = ""
    if context_samples:
        formatted = "\n".join(context_samples[: 2 * limit])
        if formatted:
            context_block = "\n참고 문맥:\n" + formatted

    return template.format(
        seed_query=seed_query.strip(),
        limit=limit,
        context_block=context_block,
    )


def generate_related_queries(
    seed_query: str,
    *,
    limit: int,
    model: str | None = None,
    context_samples: Sequence[str] | None = None,
    api_key: str | None = None,
    prompt_template: str | None = None,
) -> List[str]:
    """Use Gemini to generate a list of related search queries."""

    if limit <= 0:
        return []

    chosen_model = (
        model
        or os.getenv("MINOR_SEARCH_GEMINI_MODEL")
        or os.getenv("MINER_GEMINI_MODEL")
        or DEFAULT_MODEL
    )

    try:
        _configure_client(api_key)
    except GeminiUnavailableError:
        return []

    prompt = _build_related_prompt(
        seed_query,
        limit=limit,
        context_samples=context_samples,
        prompt_template=prompt_template,
    )

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
