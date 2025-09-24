"""PostgreSQL logging utilities for Miner runs."""

from __future__ import annotations

import os
import uuid
from typing import Mapping, Sequence, TYPE_CHECKING

import psycopg
from psycopg.types.json import Json

if TYPE_CHECKING:  # pragma: no cover - imported only for typing
    from minor_search import SearchChunk


_SCHEMA_PREPARED = False


def _resolve_dsn(override: str | None = None) -> str | None:
    """Return the PostgreSQL DSN if configured."""

    if override:
        return override
    return os.getenv("MINER_DATABASE_URL")


def _is_configured(dsn: str | None) -> bool:
    return bool(dsn)


def _prepare_schema(connection: psycopg.Connection) -> None:
    """Create the required tables when they do not exist yet."""

    global _SCHEMA_PREPARED
    if _SCHEMA_PREPARED:
        return

    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS miner_runs (
                id UUID PRIMARY KEY,
                mode TEXT NOT NULL,
                base_query TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                markdown TEXT,
                related_queries TEXT[] NOT NULL DEFAULT '{}',
                failures TEXT[] NOT NULL DEFAULT '{}',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                stored_chunks INTEGER,
                collection TEXT,
                embedding_models JSONB
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS miner_crawled_chunks (
                id UUID PRIMARY KEY,
                run_id UUID NOT NULL REFERENCES miner_runs(id) ON DELETE CASCADE,
                query TEXT NOT NULL,
                source_label TEXT,
                url TEXT,
                title TEXT,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                content_length INTEGER NOT NULL
            )
            """
        )

    _SCHEMA_PREPARED = True


def _log_chunks(
    connection: psycopg.Connection,
    run_id: uuid.UUID,
    chunks: Sequence["SearchChunk"],
) -> None:
    if not chunks:
        return

    with connection.cursor() as cursor:
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO miner_crawled_chunks (
                    id, run_id, query, source_label, url, title, chunk_index, content, content_length
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid.uuid4(),
                    run_id,
                    chunk.query,
                    getattr(chunk, "source_label", None),
                    chunk.url,
                    chunk.title,
                    chunk.chunk_index,
                    chunk.content,
                    len(chunk.content),
                ),
            )


def log_search_run(
    *,
    base_query: str,
    markdown: str,
    related_queries: Sequence[str],
    chunks: Sequence["SearchChunk"],
    failures: Sequence[str],
    dsn: str | None = None,
) -> uuid.UUID | None:
    """Persist the outcome of a search mode execution."""

    resolved = _resolve_dsn(dsn)
    if not _is_configured(resolved):
        return None

    connection = psycopg.connect(resolved)
    try:
        _prepare_schema(connection)
        run_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO miner_runs (
                    id, mode, base_query, markdown, related_queries, failures, chunk_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    "search",
                    base_query,
                    markdown,
                    list(related_queries),
                    list(failures),
                    len(chunks),
                ),
            )

        _log_chunks(connection, run_id, chunks)
        connection.commit()
        return run_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def log_agent_run(
    *,
    base_query: str,
    summary_markdown: str,
    related_queries: Sequence[str],
    failures: Sequence[str],
    chunks: Sequence["SearchChunk"],
    stored_chunks: int,
    collection: str,
    embedding_models: Mapping[str, str],
    dsn: str | None = None,
) -> uuid.UUID | None:
    """Persist the outcome of an agent mode execution."""

    resolved = _resolve_dsn(dsn)
    if not _is_configured(resolved):
        return None

    connection = psycopg.connect(resolved)
    try:
        _prepare_schema(connection)
        run_id = uuid.uuid4()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO miner_runs (
                    id, mode, base_query, markdown, related_queries, failures,
                    chunk_count, stored_chunks, collection, embedding_models
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    "agent",
                    base_query,
                    summary_markdown,
                    list(related_queries),
                    list(failures),
                    len(chunks),
                    stored_chunks,
                    collection,
                    Json(dict(embedding_models)),
                ),
            )

        _log_chunks(connection, run_id, chunks)
        connection.commit()
        return run_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


__all__ = ["log_search_run", "log_agent_run"]

