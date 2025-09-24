from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import re

import streamlit as st

from ai_search.config.settings import settings

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
                question = first_line.replace("# ����", "").strip()
            mod_time = datetime.fromtimestamp(filepath.stat().st_mtime)
            report_files.append(
                {
                    "filename": filepath.name,
                    "question": question or "���� ����",
                    "date": mod_time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - display failure in console
            print(f"���� �ε� ���� ({filepath.name}): {exc}")
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
                question = question_part.replace("# ����", "").strip()
                content = content_part.replace("# �м� ����Ʈ", "").strip()
                return question, content
            return "���� ����", full_content
    except FileNotFoundError:
        return "������ ã�� �� �����ϴ�.", ""
    except Exception as exc:  # noqa: BLE001 - surface full error to UI
        return f"���� �ε� ����: {exc}", ""


def process_latex(text: str) -> str:
    """Convert LaTeX delimiters to a Streamlit-friendly format."""
    return re.sub(r"\\\\\[(.*?)\\\\\]", r"$$\\1$$", text, flags=re.DOTALL)


st.set_page_config(page_title="�м� ��ȹ�� ���", layout="wide")
st.markdown(
    """
    <style>
    /* ����� ���� ��Ÿ���� ���⿡ �߰��ϼ��� */
    </style>
    """,
    unsafe_allow_html=True,
)

st.sidebar.header("����Ʈ ��� ����")
reports = get_all_reports(REPORTS_DIR)

if not reports:
    st.sidebar.info("����� �м� ��ȹ���� �����ϴ�.")
else:
    report_options = {f"{item['question']} ({item['filename']})": item["filename"] for item in reports}
    selected_key = st.sidebar.selectbox("������ ����Ʈ�� �����ϼ���", list(report_options.keys()), index=0)
    selected_filename = report_options[selected_key]

    question, content = read_report_file(selected_filename)
    content = process_latex(content)
    selected_report_info = next((item for item in reports if item["filename"] == selected_filename), None)

    st.sidebar.markdown("---")
    st.sidebar.subheader("���� ���� ���� ����Ʈ")
    if selected_report_info:
        st.sidebar.markdown(f"**{selected_report_info['question']}**")
        st.sidebar.markdown(f"**���ϸ�** `{selected_report_info['filename']}`")
        st.sidebar.markdown(f"**�ۼ���** {selected_report_info['date']}")

    st.markdown("<div class='title'>�м� ��ȹ�� ���</div>", unsafe_allow_html=True)

    with st.container():
        st.markdown(
            f"""
            <div class='card'>
                <b>����:</b> {question}<br/>
                <b>�ۼ���:</b> {selected_report_info['date'] if selected_report_info else '�� �� ����'}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.subheader("�� ����")

    with st.container():
        st.markdown(f"<div class='card'>{content}</div>", unsafe_allow_html=True)
