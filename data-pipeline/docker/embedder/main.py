"""Embedder container that simulates Gemini vector generation."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Iterable, List


EMBEDDING_DIMENSIONS = 16


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> List[float]:
    """Create a deterministic pseudo-embedding from text."""

    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector = [round(byte / 255.0, 6) for byte in digest[:dimensions]]
    if len(vector) < dimensions:
        vector.extend([0.0] * (dimensions - len(vector)))
    return vector


def embed_documents(documents: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for document in documents:
        text = document.get("text", "")
        embedding = embed_text(text)
        payload.append({"url": document.get("url", ""), "embedding": embedding, "text": text})
    return payload


def main() -> None:
    raw = json.loads(os.getenv("PIPELINE_PARSED", "{}") or "{}")
    documents = raw.get("parsed", [])
    embeddings = embed_documents(documents)
    print(json.dumps({"embeddings": embeddings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
