from __future__ import annotations

import os
import re
import time
from typing import Iterable, List

import requests
from langchain_core.tools import tool

CROSSREF_ENDPOINT = "https://api.crossref.org/works"

try:
    from deep_translator import GoogleTranslator
except Exception:  # optional dependency
    GoogleTranslator = None


def _extract_authors(people: List[dict]) -> str:
    if not people:
        return "저자 정보 없음"
    names = []
    for person in people[:3]:
        given = person.get("given", "")
        family = person.get("family", "")
        name = " ".join(part for part in [given, family] if part)
        names.append(name or "익명")
    if len(people) > 3:
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


def _build_headers() -> tuple[dict[str, str], str | None]:
    contact = os.getenv("CROSSREF_MAILTO") or os.getenv("CONTACT_EMAIL")
    user_agent = "charts-workflow-cli/1.0"
    if contact:
        user_agent = f"{user_agent} (mailto:{contact})"
    return {"User-Agent": user_agent}, contact


@tool
def crossref_search(query: str) -> str:
    """CrossRef API를 사용해 DOI 메타데이터를 검색합니다."""
    headers, contact = _build_headers()
    last_error: str | None = None

    for candidate in _candidate_queries(query):
        params = {
            "query.bibliographic": candidate,
            "rows": 5,
            "sort": "relevance",
            "select": "DOI,title,author,container-title,issued,type,url",
        }
        if contact:
            params["mailto"] = contact

        try:
            response = requests.get(CROSSREF_ENDPOINT, params=params, headers=headers, timeout=15)
        except Exception as exc:
            last_error = f"검색 실패: {exc}"
            continue

        if response.status_code == 429:
            last_error = "검색 실패: CrossRef 요청이 너무 많습니다. 잠시 후 다시 시도하세요."
            time.sleep(1)
            continue
        if response.status_code >= 400:
            last_error = f"검색 실패: {response.status_code} 응답. 요청 쿼리='{candidate}'"
            continue

        try:
            items = response.json().get("message", {}).get("items", [])
        except ValueError:
            last_error = "검색 실패: API 응답을 해석할 수 없습니다."
            continue

        if not items:
            last_error = "검색 결과 없음"
            continue

        lines = []
        for item in items:
            titles = item.get("title") or ["제목 없음"]
            title = titles[0]
            doi = item.get("DOI", "DOI 없음")
            url = item.get("URL") or (f"https://doi.org/{doi}" if doi != "DOI 없음" else "URL 없음")
            journal = (item.get("container-title") or ["저널 미상"])[0]
            authors = _extract_authors(item.get("author"))
            year = None
            issued = item.get("issued", {}).get("date-parts")
            if issued and issued[0]:
                year = issued[0][0]
            parts = [f"저널: {journal}", f"DOI: {doi}", f"저자: {authors}"]
            if year:
                parts.insert(0, f"연도: {year}")
            metadata = ", ".join(parts)
            lines.append(f"- **[{title}]({url})** ({metadata})")

        return "\n".join(lines)

    return last_error or "검색 실패: 알 수 없는 오류"

