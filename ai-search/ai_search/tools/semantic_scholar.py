import os
import re
import time
from typing import Iterable, List

import requests
from langchain_core.tools import tool

SEMANTIC_SCHOLAR_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = "title,year,authors,citationCount,url"

try:
    from deep_translator import GoogleTranslator
except Exception:  # optional dependency
    GoogleTranslator = None


def _format_authors(authors: List[dict]) -> str:
    if not authors:
        return "저자 정보 없음"
    names = [author.get("name", "익명") for author in authors[:3]]
    if len(authors) > 3:
        names.append("외")
    return ", ".join(names)


def _trim_query(text: str, max_terms: int = 8) -> str:
    terms = re.split(r"\s+", text.strip())
    if len(terms) <= max_terms:
        return text.strip()
    return " ".join(terms[:max_terms])


def _translate_query(text: str) -> str | None:
    if not GoogleTranslator:
        return None
    try:
        translated = GoogleTranslator(source="auto", target="en").translate(text)
    except Exception:
        return None
    return translated.strip() or None


def _candidate_queries(original: str) -> Iterable[str]:
    seen: set[str] = set()

    def _add(candidate: str | None):
        if not candidate:
            return
        value = candidate.strip()
        if not value or value in seen:
            return
        seen.add(value)
        yield value

    yield from _add(original)
    yield from _add(_trim_query(original))
    english = _translate_query(original)
    yield from _add(english)
    if english:
        yield from _add(_trim_query(english))


@tool
def semantic_scholar_search(query: str) -> str:
    """Semantic Scholar API를 활용해 학술 논문을 검색합니다."""
    headers = {}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    last_error: str | None = None

    for attempt, candidate in enumerate(_candidate_queries(query), start=1):
        params = {
            "query": candidate,
            "limit": 5,
            "fields": SEMANTIC_SCHOLAR_FIELDS,
        }
        try:
            response = requests.get(SEMANTIC_SCHOLAR_ENDPOINT, params=params, headers=headers, timeout=15)
        except Exception as exc:
            last_error = f"검색 실패: {exc}"
            continue

        if response.status_code == 429:
            last_error = "검색 실패: 요청이 너무 많습니다. 잠시 후 다시 시도하거나 API 키를 설정하세요."
            time.sleep(1)
            continue
        if response.status_code >= 400:
            last_error = f"검색 실패: {response.status_code} 응답. 요청 쿼리='{candidate}'"
            continue

        try:
            data = response.json()
        except ValueError:
            last_error = "검색 실패: API 응답을 해석할 수 없습니다."
            continue

        papers = data.get("data", [])
        if not papers:
            last_error = "검색 결과 없음"
            continue

        lines = []
        for paper in papers:
            title = paper.get("title") or "제목 없음"
            url = paper.get("url") or "URL 없음"
            year = paper.get("year")
            citation_count = paper.get("citationCount")
            authors = _format_authors(paper.get("authors"))
            meta = []
            if year:
                meta.append(f"연도: {year}")
            if citation_count is not None:
                meta.append(f"인용: {citation_count}")
            meta.append(f"저자: {authors}")
            meta_str = ", ".join(meta)
            lines.append(f"- **[{title}]({url})** ({meta_str})")

        return "\n".join(lines)

    return last_error or "검색 실패: 알 수 없는 오류"
