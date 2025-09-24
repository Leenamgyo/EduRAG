import requests
from typing import List

from langchain_core.tools import tool

OPENALEX_ENDPOINT = "https://api.openalex.org/works"


def _format_concepts(concepts: List[dict]) -> str:
    if not concepts:
        return "주요 토픽 없음"
    sorted_concepts = sorted(concepts, key=lambda c: c.get('score', 0), reverse=True)
    labels = [c.get('display_name', '토픽') for c in sorted_concepts[:3]]
    return ", ".join(labels)


@tool
def openalex_search(query: str) -> str:
    """OpenAlex API로 학술 네트워크 및 인용 정보를 검색합니다."""
    params = {
        "search": query,
        "per-page": 5,
        "sort": "relevance_score:desc",
    }

    try:
        response = requests.get(OPENALEX_ENDPOINT, params=params, timeout=15)
        response.raise_for_status()
    except Exception as exc:
        return f"검색 실패: {exc}"

    results = response.json().get("results", [])
    if not results:
        return "검색 결과 없음"

    lines = []
    for work in results:
        title = work.get("display_name") or "제목 없음"
        primary_location = work.get("primary_location", {})
        url = primary_location.get("source", {}).get("homepage_url") or work.get("doi")
        if url:
            if url.startswith("http"):
                link = url
            else:
                link = f"https://doi.org/{url}"
        else:
            link = work.get("id", "URL 없음")
        year = work.get("publication_year")
        cite_count = work.get("cited_by_count")
        oa_status = work.get("open_access", {}).get("status", "unknown")
        concepts = _format_concepts(work.get("concepts"))
        meta_parts = []
        if year:
            meta_parts.append(f"연도: {year}")
        if cite_count is not None:
            meta_parts.append(f"인용: {cite_count}")
        meta_parts.append(f"OA: {oa_status}")
        meta_parts.append(f"토픽: {concepts}")
        metadata = ", ".join(meta_parts)
        lines.append(f"- **[{title}]({link})** ({metadata})")

    return "\n".join(lines)
