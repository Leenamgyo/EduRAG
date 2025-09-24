"""Parser container that extracts clean text from HTML documents."""

from __future__ import annotations

import json
import os
from html.parser import HTMLParser
from typing import Dict, Iterable, List


class TextExtractor(HTMLParser):
    """Simple HTML parser to extract text content."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self._chunks)


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def parse_documents(documents: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    parsed: List[Dict[str, str]] = []
    for document in documents:
        text = extract_text(document.get("html", ""))
        parsed.append({"url": document.get("url", ""), "text": text})
    return parsed


def main() -> None:
    payload = os.getenv("PIPELINE_DOCUMENTS", "{}")
    raw = json.loads(payload or "{}")
    documents = raw.get("documents", [])
    parsed = parse_documents(documents)
    print(json.dumps({"parsed": parsed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
