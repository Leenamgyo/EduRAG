from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List

import streamlit as st

from ai_search_web.elasticsearch_client import (
    ElasticsearchConfigurationError,
    get_client,
)
from ai_search_web.settings import settings


@st.cache_data(ttl=60)
def fetch_reports() -> List[Dict[str, str]]:
    """Retrieve saved reports from Elasticsearch."""
    client = get_client()
    response = client.search(
        index=settings.es_index,
        query={"match_all": {}},
        sort=[{"created_at": {"order": "desc"}}],
        size=200,
    )

    documents: List[Dict[str, str]] = []
    for hit in response.get("hits", {}).get("hits", []):
        source = hit.get("_source", {})
        documents.append(
            {
                "id": hit.get("_id", ""),
                "question": source.get("question", ""),
                "content": source.get("content", ""),
                "created_at": source.get("created_at", ""),
            }
        )
    return documents


def process_latex(text: str) -> str:
    """Convert LaTeX delimiters to a Streamlit-friendly format."""
    return re.sub(r"\\\\\[(.*?)\\\\\]", r"$$\\1$$", text, flags=re.DOTALL)


def format_timestamp(timestamp: str) -> str:
    """Convert an ISO timestamp into a readable string."""
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return timestamp
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def build_option_label(report: Dict[str, str], index: int) -> str:
    """Create a select box label that remains unique."""
    question = report.get("question") or f"보고서 {index + 1}"
    created_at = format_timestamp(report.get("created_at", ""))
    identifier = report.get("id", "")[:8]

    label = question
    if created_at:
        label = f"{label} ({created_at})"
    if identifier:
        label = f"{label} - {identifier}"
    return label


def render_sidebar(reports: List[Dict[str, str]]) -> Dict[str, str] | None:
    """Render the sidebar and return the currently selected report."""
    st.sidebar.header("보고서 목록")

    if not reports:
        st.sidebar.info("저장된 보고서가 없습니다.")
        return None

    option_labels = [build_option_label(report, idx) for idx, report in enumerate(reports)]
    selection = st.sidebar.selectbox("보고서를 선택하세요", option_labels, index=0)
    selected_index = option_labels.index(selection)
    selected_report = reports[selected_index]

    question = selected_report.get("question", "")
    created_at = format_timestamp(selected_report.get("created_at", ""))

    st.sidebar.markdown("---")
    st.sidebar.subheader("선택한 보고서")
    st.sidebar.markdown(f"**질문**: {question or '제목 없음'}")
    st.sidebar.markdown(f"**ID**: `{selected_report.get('id', '')}`")
    if created_at:
        st.sidebar.markdown(f"**작성일**: {created_at}")

    return selected_report


st.set_page_config(page_title="연구 보고서 뷰어", layout="wide")
st.markdown(
    """
    <style>
    /* 사용자 정의 스타일을 이 영역에 추가할 수 있습니다. */
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    reports = fetch_reports()
except ElasticsearchConfigurationError as exc:
    st.sidebar.error(str(exc))
    reports = []
except Exception as exc:  # noqa: BLE001 - surface the issue to the UI
    st.sidebar.error(f"보고서를 불러오는 중 오류가 발생했습니다: {exc}")
    reports = []

selected_report = render_sidebar(reports)

if selected_report:
    question = selected_report.get("question", "")
    content = process_latex(selected_report.get("content", ""))
    created_at = format_timestamp(selected_report.get("created_at", ""))

    st.markdown("<div class='title'>연구 보고서</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown(
            f"""
            <div class='card'>
                <b>질문:</b> {question}<br/>
                <b>작성일:</b> {created_at or '미상'}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("결과")

    with st.container():
        st.markdown(f"<div class='card'>{content}</div>", unsafe_allow_html=True)
else:
    st.title("연구 보고서")
    st.info("왼쪽에서 보고서를 선택하면 상세 내용을 확인할 수 있습니다.")
