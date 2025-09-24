from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from elasticsearch import Elasticsearch

from ai_search.config.settings import settings
from ai_search.storage.elasticsearch_client import (
    ElasticsearchConfigurationError,
    get_client,
)

_INDEX_INITIALISED = False


def _ensure_index(client: Elasticsearch) -> None:
    """Create the target index if it does not already exist."""
    global _INDEX_INITIALISED
    if _INDEX_INITIALISED:
        return

    index_name = settings.es_index
    try:
        if not client.indices.exists(index=index_name):
            client.indices.create(
                index=index_name,
                mappings={
                    "properties": {
                        "question": {"type": "text"},
                        "content": {"type": "text"},
                        "created_at": {"type": "date"},
                    }
                },
            )
        _INDEX_INITIALISED = True
    except Exception as exc:  # noqa: BLE001 - surface full error for CLI visibility
        raise RuntimeError(
            f"Failed to ensure Elasticsearch index '{index_name}' exists: {exc}"
        ) from exc


def save_report(
    question: str,
    content: str,
    directory: Optional[str] = None,
    report_format: str = "md",
) -> Optional[str]:
    """Persist an analysis report to Elasticsearch and return the document id."""

    del directory, report_format  # Unused with Elasticsearch storage

    try:
        client = get_client()
        _ensure_index(client)
    except ElasticsearchConfigurationError as exc:
        print(f"[  ] {exc}")
        return None
    except Exception as exc:  # noqa: BLE001 - surface full error for CLI visibility
        print(f"[  ] {exc}")
        return None

    document = {
        "question": question,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = client.index(index=settings.es_index, document=document)
        document_id = response.get("_id")
        print(
            "[  Ϸ] Stored report in Elasticsearch "
            f"(index={settings.es_index}, id={document_id})"
        )
        return document_id
    except Exception as exc:  # noqa: BLE001 - surface full error for CLI visibility
        print(f"[  ] Failed to store report in Elasticsearch: {exc}")
        return None
