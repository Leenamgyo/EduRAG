from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import re

import streamlit as st

from charts_workflow.config.settings import settings

REPORTS_DIR = settings.reports_dir


@st.cache_data(ttl=60)
def get_all_reports(directory: Path) -> List[dict]:
    """Return metadata for every markdown report in the directory."""
    if not directory.exists():
        return []

    report_files: List[dict] = []
    for filepath in sorted(directory.glob("*.md")):
        try:
            with filepath.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
                question = first_line.replace("# 질문", "").strip()
            mod_time = datetime.fromtimestamp(filepath.stat().st_mtime)
            report_files.append(
                {
                    "filename": filepath.name,
                    "question": question or "제목 없음",
                    "date": mod_time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - display failure in console
            print(f"보고서 로드 오류 ({filepath.name}): {exc}")
    return sorted(report_files, key=lambda item: item["date"], reverse=True)


@st.cache_data
def read_report_file(filename: str, directory: Path = REPORTS_DIR) -> Tuple[str, str]:
    """Load an individual report and split question/content."""
    filepath = directory / filename
    try:
        with filepath.open("r", encoding="utf-8") as handle:
            full_content = handle.read()
            parts = full_content.split("\n---\n", 1)
            if len(parts) == 2:
                question_part, content_part = parts
                question = question_part.replace("# 질문", "").strip()
                content = content_part.replace("# 분석 리포트", "").strip()
                return question, content
            return "질문 없음", full_content
    except FileNotFoundError:
        return "보고서를 찾을 수 없습니다.", ""
    except Exception as exc:  # noqa: BLE001 - surface full error to UI
        return f"보고서 로딩 오류: {exc}", ""


def process_latex(text: str) -> str:
    """Convert LaTeX delimiters to a Streamlit-friendly format."""
    return re.sub(r"\\\\\[(.*?)\\\\\]", r"$$\\1$$", text, flags=re.DOTALL)


st.set_page_config(page_title="분석 기획안 뷰어", layout="wide")
st.markdown(
    """
    <style>
    /* 사용자 정의 스타일을 여기에 추가하세요 */
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header("리포트 목록 열람")
reports = get_all_reports(REPORTS_DIR)

if not reports:
    st.sidebar.info("저장된 분석 기획안이 없습니다.")
else:
    report_options = {f"{item['question']} ({item['filename']})": item["filename"] for item in reports}
    selected_key = st.sidebar.selectbox("열람할 리포트를 선택하세요", list(report_options.keys()), index=0)
    selected_filename = report_options[selected_key]

    question, content = read_report_file(selected_filename)
    content = process_latex(content)
    selected_report_info = next((item for item in reports if item["filename"] == selected_filename), None)

    st.sidebar.markdown("---")
    st.sidebar.subheader("현재 열람 중인 리포트")
    if selected_report_info:
        st.sidebar.markdown(f"**{selected_report_info['question']}**")
        st.sidebar.markdown(f"**파일명** `{selected_report_info['filename']}`")
        st.sidebar.markdown(f"**작성일** {selected_report_info['date']}")

    st.markdown("<div class='title'>분석 기획안 뷰어</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown(
            f"""
            <div class='card'>
                <b>질문:</b> {question}<br/>
                <b>작성일:</b> {selected_report_info['date'] if selected_report_info else '알 수 없음'}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("상세 내용")

    with st.container():
        st.markdown(f"<div class='card'>{content}</div>", unsafe_allow_html=True)
