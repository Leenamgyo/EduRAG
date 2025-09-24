from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

_LOCAL_IDENTIFIERS = ("localhost", "127.0.0.1", "0.0.0.0")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the ai-search web frontend."""

    es_host: Optional[str]
    es_scheme: str
    es_username: Optional[str]
    es_password: Optional[str]
    es_index: str
    api_base_url: Optional[str]
    page_size: int


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _normalize_host(raw_host: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not raw_host:
        return None, None

    candidate = raw_host.strip()
    if not candidate:
        return None, None

    parsed = urlparse(candidate)
    if parsed.scheme:
        host = parsed.netloc
        if parsed.path and parsed.path != "/":
            host = f"{host}{parsed.path}"
        return host, parsed.scheme

    return candidate, None


def _default_scheme(host: Optional[str]) -> str:
    if host and any(identifier in host for identifier in _LOCAL_IDENTIFIERS):
        return "http"
    return "https"


def load_settings() -> Settings:
    raw_host = os.getenv("ES_HOST")
    normalized_host, host_scheme = _normalize_host(raw_host)
    env_scheme = os.getenv("ES_SCHEME")
    scheme = (env_scheme or host_scheme or _default_scheme(normalized_host) or "https")
    scheme = scheme.lower()

    return Settings(
        es_host=normalized_host,
        es_scheme=scheme,
        es_username=os.getenv("ES_USERNAME", None),
        es_password=os.getenv("ES_PASSWORD", None),
        es_index=os.getenv("ES_INDEX", "ai-search-reports"),
        api_base_url=os.getenv("AI_SEARCH_API"),
        page_size=_env_int("ES_PAGE_SIZE", 200),
    )


settings = load_settings()
