from __future__ import annotations

from functools import lru_cache
from typing import Optional

from elasticsearch import Elasticsearch

from ai_search_web.settings import settings


class ElasticsearchConfigurationError(RuntimeError):
    """Raised when the Elasticsearch connection is not configured."""


@lru_cache(maxsize=1)
def get_client() -> Elasticsearch:
    host = settings.es_host
    if not host:
        raise ElasticsearchConfigurationError(
            "Elasticsearch host is not configured. Set the ES_HOST environment variable."
        )

    username: Optional[str] = settings.es_username
    password: Optional[str] = settings.es_password

    if username and password:
        return Elasticsearch(hosts=[host], basic_auth=(username, password))
    return Elasticsearch(hosts=[host])
