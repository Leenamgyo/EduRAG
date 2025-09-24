"""Utilities for persisting Minor Search results to MinIO."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable

from minio import Minio
from minio.error import S3Error

from ..search import AgentChunkResult


@dataclass(slots=True)
class MinioSettings:
    """Configuration required to connect to a MinIO object store."""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str = "minor-search"
    secure: bool = False
    region: str | None = None

    @classmethod
    def from_environment(cls) -> "MinioSettings":
        """Build a settings object by reading MINOR_SEARCH_MINIO_* variables."""

        endpoint = os.getenv("MINOR_SEARCH_MINIO_ENDPOINT", "localhost:9000")
        access_key = os.getenv("MINOR_SEARCH_MINIO_ACCESS_KEY", "minioadmin")
        secret_key = os.getenv("MINOR_SEARCH_MINIO_SECRET_KEY", "minioadmin")
        bucket = os.getenv("MINOR_SEARCH_MINIO_BUCKET", "minor-search")
        secure = os.getenv("MINOR_SEARCH_MINIO_SECURE", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        region = os.getenv("MINOR_SEARCH_MINIO_REGION") or None
        return cls(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            bucket=bucket,
            secure=secure,
            region=region,
        )


def create_client(settings: MinioSettings) -> Minio:
    """Create a MinIO client from the provided settings."""

    return Minio(
        settings.endpoint,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        secure=settings.secure,
        region=settings.region,
    )


def ensure_bucket(client: Minio, settings: MinioSettings) -> None:
    """Ensure that the configured bucket exists."""

    try:
        exists = client.bucket_exists(settings.bucket)
    except S3Error as exc:  # pragma: no cover - depends on external service
        raise RuntimeError(f"Failed to verify bucket '{settings.bucket}': {exc}") from exc

    if exists:
        return

    try:
        client.make_bucket(settings.bucket, location=settings.region)
    except S3Error as exc:  # pragma: no cover - depends on external service
        raise RuntimeError(f"Failed to create bucket '{settings.bucket}': {exc}") from exc


def _serialize_chunk_result(result: AgentChunkResult) -> bytes:
    payload = json.dumps(result.to_dict(), ensure_ascii=False).encode("utf-8")
    return payload


def store_agent_chunks(
    client: Minio,
    settings: MinioSettings,
    result: AgentChunkResult,
    *,
    object_name: str | None = None,
) -> str:
    """Persist an :class:`AgentChunkResult` and return the object name used."""

    ensure_bucket(client, settings)

    payload = _serialize_chunk_result(result)
    data = BytesIO(payload)
    length = len(payload)

    object_key = object_name or result.default_object_name()

    client.put_object(
        settings.bucket,
        object_key,
        data,
        length,
        content_type="application/json",
    )
    return object_key


def load_agent_chunks(
    client: Minio,
    settings: MinioSettings,
    object_name: str,
) -> AgentChunkResult:
    """Download an :class:`AgentChunkResult` stored in MinIO."""

    try:
        response = client.get_object(settings.bucket, object_name)
    except S3Error as exc:  # pragma: no cover - depends on external service
        raise RuntimeError(
            f"Failed to download object '{object_name}' from bucket '{settings.bucket}': {exc}"
        ) from exc

    try:
        data = response.read()
    finally:
        response.close()
        response.release_conn()

    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - malformed payloads
        raise RuntimeError(
            f"Object '{object_name}' does not contain valid JSON search results: {exc}"
        ) from exc

    return AgentChunkResult.from_dict(payload)


__all__: Iterable[str] = [
    "MinioSettings",
    "create_client",
    "ensure_bucket",
    "store_agent_chunks",
    "load_agent_chunks",
]
