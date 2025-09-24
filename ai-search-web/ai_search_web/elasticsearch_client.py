from __future__ import annotations

from functools import lru_cache
from typing import Optional

from elasticsearch import Elasticsearch

from ai_search_web.settings import settings


class ElasticsearchConfigurationError(RuntimeError):
    """Raised when the Elasticsearch connection has not been configured."""


def _build_endpoint(host: str, scheme: str) -> str:
    if host.startswith("http://") or host.startswith("https://"):
        return host

    sanitized = host.lstrip("/")
    return f"{scheme}://{sanitized}"


@lru_cache(maxsize=1)
def get_client() -> Elasticsearch:
    host = settings.es_host
    if not host:
        raise ElasticsearchConfigurationError(
            "Elasticsearch host is not configured. Set the ES_HOST environment variable."
        )

    endpoint = _build_endpoint(host, settings.es_scheme)

    username: Optional[str] = settings.es_username
    password: Optional[str] = settings.es_password

    if username and password:
        return Elasticsearch(hosts=[endpoint], basic_auth=(username, password))

    return Elasticsearch(hosts=[endpoint])
