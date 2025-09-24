import os
from typing import List, Tuple

from tavily import TavilyClient
from langchain_core.tools import tool

try:
    from deep_translator import GoogleTranslator
except Exception:  # Optional dependency; continue without translation
    GoogleTranslator = None


@tool
def tavily_web_search(query: str) -> str:
    """교육·학술 주제 전반에 대한 다국어 웹 검색을 수행하고 출처별로 정리합니다."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY environment variable is not set.")

    client = TavilyClient(api_key=api_key)

    search_plan: List[Tuple[str, str, dict]] = []
    search_plan.append((
        "KO",
        query,
        {
            "language": "ko",
            "include_domains": ["moe.go.kr", "kedi.re.kr", "ac.kr", "go.kr"],
        },
    ))

    english_query = query
    if GoogleTranslator is not None:
        try:
            translated = GoogleTranslator(source="auto", target="en").translate(query)
            if isinstance(translated, str) and translated.strip():
                english_query = translated.strip()
        except Exception:
            pass

    search_plan.append((
        "EN",
        english_query,
        {
            "language": "en",
            "include_domains": [
                "oecd.org",
                "unesco.org",
                "worldbank.org",
                "eric.ed.gov",
                "ed.gov",
                "brookings.edu",
            ],
        },
    ))

    search_plan.append((
        "GLOBAL",
        english_query,
        {
            "language": "en",
            "search_depth": "advanced",
        },
    ))

    aggregated_sections: List[str] = []
    seen_urls = set()

    for label, q, options in search_plan:
        try:
            response = client.search(query=q, **options)
            items = response.get("results", [])
        except Exception as exc:
            aggregated_sections.append(f"### [{label}] 검색 실패\n- 오류: {exc}")
            continue

        if not items:
            aggregated_sections.append(f"### [{label}] 검색 결과 없음\n- 사용 쿼리: {q}")
            continue

        lines: List[str] = []
        for item in items:
            title = item.get("title") or "제목 없음"
            url = item.get("url") or "URL 없음"
            snippet = item.get("content") or item.get("snippet") or "요약 없음"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            lines.append(
                f"- **{title}**\n  - URL: {url}\n  - 요약: {snippet}"
            )

        section_body = "\n".join(lines) if lines else "- 신규 정보 없음"
        aggregated_sections.append(
            f"### [{label}] 검색 결과\n- 사용 쿼리: {q}\n{section_body}"
        )

    return "\n\n".join(aggregated_sections)
