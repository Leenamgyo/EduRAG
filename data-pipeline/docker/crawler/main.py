"""Crawler container that simulates document fetching."""

from __future__ import annotations

import json
import os
from typing import Dict, Iterable, List
from urllib.parse import quote_plus


BASE_SEARCH_URL = "https://www.google.com/search?q="


def build_search_urls(queries: Iterable[str], base_url: str = BASE_SEARCH_URL) -> List[str]:
    """Build URL list for the configured search provider."""

    return [f"{base_url}{quote_plus(query)}" for query in queries]


def simulate_crawl(urls: Iterable[str]) -> List[Dict[str, str]]:
    """Return deterministic payloads representing crawled HTML documents."""

    return [
        {
            "url": url,
            "html": f"<html><body><h1>{idx}</h1><p>Content for {url}</p></body></html>",
        }
        for idx, url in enumerate(urls)
    ]


def main() -> None:
    queries = [query.strip() for query in os.getenv("PIPELINE_QUERIES", "").split("||") if query.strip()]
    urls = build_search_urls(queries)
    documents = simulate_crawl(urls)
    print(json.dumps({"documents": documents}, ensure_ascii=False))


if __name__ == "__main__":
    main()
