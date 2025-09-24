from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from ai_search.config.settings import settings

SUPPORTED_FORMATS = {"md", "txt"}
DEFAULT_ENCODING = "utf-8"


def _normalise_directory(directory: Optional[str]) -> Path:
    if directory:
        return Path(directory).resolve()
    return settings.reports_dir


def save_report(question: str, content: str, directory: Optional[str] = None, report_format: str = "md") -> Optional[str]:
    """Persist an analysis report and return the absolute path."""
    report_format = report_format.lower()
    if report_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported report format: {report_format}")

    target_dir = _normalise_directory(directory)
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = ".md" if report_format == "md" else ".txt"
    file_path = target_dir / f"{uuid.uuid1()}{suffix}"

    if report_format == "md":
        file_contents = f"# 질문\n\n{question}\n\n---\n\n# 분석 리포트\n\n{content}"
    else:
        file_contents = (
            "[질문]\n"
            f"{question}\n\n"
            "[분석 리포트]\n"
            f"{content}"
        )

    try:
        file_path.write_text(file_contents, encoding=DEFAULT_ENCODING)
        print(f"[보고서 저장 완료] {file_path}")
        return str(file_path)
    except Exception as exc:  # noqa: BLE001 - surface full error for CLI visibility
        print(f"[보고서 저장 실패] {exc}")
        return None
