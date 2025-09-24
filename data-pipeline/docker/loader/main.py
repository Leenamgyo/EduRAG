"""Loader container that persists embeddings into the warehouse."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List


def build_records(embeddings: Iterable[Dict[str, Any]], dataset: str) -> List[Dict[str, Any]]:
    """Normalize embedding payloads into warehouse-ready records."""

    records: List[Dict[str, Any]] = []
    for item in embeddings:
        records.append(
            {
                "dataset": dataset,
                "url": item.get("url", ""),
                "vector": item.get("embedding", []),
                "text": item.get("text", ""),
            }
        )
    return records


def persist_records(records: List[Dict[str, Any]], output_path: str | None) -> None:
    if not output_path:
        return

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    dataset = os.getenv("EMBEDDINGS_TABLE", "edurag_embeddings")
    raw = json.loads(os.getenv("PIPELINE_EMBEDDINGS", "{}") or "{}")
    embeddings = raw.get("embeddings", [])
    records = build_records(embeddings, dataset)
    persist_records(records, os.getenv("PIPELINE_OUTPUT_PATH"))
    print(json.dumps({"dataset": dataset, "rows": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
