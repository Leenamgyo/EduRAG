"""Simple file-based logging utilities for Minor runs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence, TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from minor_search import SearchChunk
else:  # pragma: no cover - runtime only needs duck typing
    SearchChunk = object

DEFAULT_LOG_PATH = Path(
    os.getenv("MINOR_LOG_PATH", "~/.minor/runs.jsonl")
).expanduser()


def _resolve_path(override: os.PathLike[str] | str | None) -> Path:
    if override:
        return Path(override).expanduser()
    return DEFAULT_LOG_PATH


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize_chunks(chunks: Sequence[SearchChunk]) -> list[dict[str, object]]:
    return [
        {
            "query": chunk.query,
            "source_label": getattr(chunk, "source_label", None),
            "url": chunk.url,
            "title": chunk.title,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
        }
        for chunk in chunks
    ]


def _write_entry(path: Path, payload: Mapping[str, object]) -> UUID:
    run_id = uuid4()
    record = {"id": str(run_id), "created_at": datetime.now(timezone.utc).isoformat()}
    record.update(payload)
    _ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return run_id


def log_search_run(
    *,
    base_query: str,
    markdown: str,
    related_queries: Sequence[str],
    chunks: Sequence[SearchChunk],
    failures: Sequence[str],
    dsn: os.PathLike[str] | str | None = None,
) -> UUID:
    """Persist the outcome of a search mode execution to a JSONL file."""

    path = _resolve_path(dsn)
    payload = {
        "mode": "search",
        "base_query": base_query,
        "markdown": markdown,
        "related_queries": list(related_queries),
        "failures": list(failures),
        "chunk_count": len(chunks),
        "chunks": _serialize_chunks(chunks),
    }
    return _write_entry(path, payload)


def log_agent_run(
    *,
    base_query: str,
    summary_markdown: str,
    related_queries: Sequence[str],
    failures: Sequence[str],
    chunks: Sequence[SearchChunk],
    stored_chunks: int,
    collection: str,
    embedding_models: Mapping[str, str],
    dsn: os.PathLike[str] | str | None = None,
) -> UUID:
    """Persist the outcome of an agent mode execution to a JSONL file."""

    path = _resolve_path(dsn)
    payload = {
        "mode": "agent",
        "base_query": base_query,
        "markdown": summary_markdown,
        "related_queries": list(related_queries),
        "failures": list(failures),
        "chunk_count": len(chunks),
        "stored_chunks": stored_chunks,
        "collection": collection,
        "embedding_models": dict(embedding_models),
        "chunks": _serialize_chunks(chunks),
    }
    return _write_entry(path, payload)


__all__ = ["log_search_run", "log_agent_run"]
