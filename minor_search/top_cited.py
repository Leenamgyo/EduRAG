"""Fetch top cited academic papers for a given keyword.

This module implements the workflow described in the user instructions:

1. Query the OpenAlex API to retrieve the most cited works whose titles match
   the user supplied keyword.
2. Optionally cross-check the citation counts with the Semantic Scholar API.
3. Return the results in a clean Markdown table so that downstream agents can
   render or forward the information easily.

The module exposes both a callable :func:`fetch_top_cited_papers` function and
an executable CLI entry point.  The CLI mirrors the behaviour outlined in the
instructions and prints the Markdown table to standard output.
"""

from __future__ import annotations

import argparse
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Mapping

import requests

LOGGER = logging.getLogger(__name__)

OPENALEX_ENDPOINT = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_ENDPOINT = (
    "https://api.semanticscholar.org/graph/v1/paper/search"
)


@dataclass(slots=True)
class Paper:
    """Container for a single paper entry."""

    title: str
    year: str
    citations: str
    doi_or_url: str


def _normalise_title(title: str) -> str:
    """Return a lowercase, whitespace-normalised title string."""

    collapsed = re.sub(r"\s+", " ", title).strip()
    return collapsed.lower()


def _prepare_doi_or_url(work: Mapping[str, object]) -> str:
    """Extract a DOI or URL string from an OpenAlex work object."""

    doi_raw = work.get("doi")
    if isinstance(doi_raw, str) and doi_raw:
        doi = doi_raw.strip()
        if doi.startswith("http://") or doi.startswith("https://"):
            return doi
        return f"https://doi.org/{doi}"

    # Fall back to landing page / PDF URLs when DOI is not available.
    primary_location = work.get("primary_location")
    if isinstance(primary_location, Mapping):
        landing_page = primary_location.get("landing_page_url")
        if isinstance(landing_page, str) and landing_page:
            return landing_page
        pdf_url = primary_location.get("pdf_url")
        if isinstance(pdf_url, str) and pdf_url:
            return pdf_url

    # Finally use the canonical OpenAlex identifier.
    work_id = work.get("id")
    if isinstance(work_id, str) and work_id:
        return work_id

    return ""


def _call_openalex(keyword: str, limit: int, timeout: float) -> List[Mapping[str, object]]:
    """Invoke the OpenAlex API and return the raw work objects."""

    params = {
        "filter": f"title.search:{keyword}",
        "sort": "cited_by_count:desc",
        "per_page": limit,
    }
    LOGGER.debug("Requesting OpenAlex works", extra={"params": params})

    response = requests.get(OPENALEX_ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results", [])

    if not isinstance(results, list):
        raise ValueError("Unexpected OpenAlex response: 'results' must be a list")

    return [work for work in results if isinstance(work, Mapping)]


def _call_semantic_scholar(
    keyword: str,
    limit: int,
    timeout: float,
) -> Mapping[str, int]:
    """Return a mapping of normalised titles to citation counts."""

    params = {
        "query": keyword,
        "fields": "title,year,citationCount",
        "limit": limit,
    }
    LOGGER.debug("Requesting Semantic Scholar papers", extra={"params": params})

    response = requests.get(SEMANTIC_SCHOLAR_ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data", [])
    if not isinstance(data, list):
        LOGGER.warning("Unexpected Semantic Scholar response: 'data' is not a list")
        return {}

    mapping: dict[str, int] = {}
    for item in data:
        if not isinstance(item, Mapping):
            continue
        title = item.get("title")
        citations = item.get("citationCount")
        if not isinstance(title, str) or not title:
            continue
        if isinstance(citations, int):
            mapping[_normalise_title(title)] = citations

    return mapping


def fetch_top_cited_papers(
    keyword: str,
    *,
    limit: int = 5,
    verify_with_semantic_scholar: bool = True,
    timeout: float = 15.0,
) -> List[Paper]:
    """Return the top cited papers for ``keyword``.

    Parameters
    ----------
    keyword:
        User supplied search keyword used in both API calls.
    limit:
        Maximum number of papers to include in the result set.
    verify_with_semantic_scholar:
        When ``True`` the function will call the Semantic Scholar API and use
        the returned citation counts when the titles match.
    timeout:
        Timeout in seconds applied to both HTTP requests.
    """

    if limit <= 0:
        raise ValueError("limit must be a positive integer")

    works = _call_openalex(keyword, limit, timeout)

    semantic_citations: Mapping[str, int] = {}
    if verify_with_semantic_scholar:
        try:
            semantic_citations = _call_semantic_scholar(keyword, limit, timeout)
        except requests.HTTPError as exc:  # pragma: no cover - network failure
            LOGGER.warning("Semantic Scholar request failed", exc_info=exc)
        except requests.RequestException as exc:  # pragma: no cover
            LOGGER.warning("Semantic Scholar request error", exc_info=exc)

    papers: List[Paper] = []
    for work in works:
        title = str(work.get("display_name") or "Untitled")
        year_value = work.get("publication_year")
        if isinstance(year_value, int):
            year = str(year_value)
        else:
            year = "-"

        citations_value = work.get("cited_by_count")
        if isinstance(citations_value, int):
            citations = citations_value
        else:
            citations = None

        normalised_title = _normalise_title(title)
        if normalised_title in semantic_citations:
            citations_display = str(semantic_citations[normalised_title])
        elif citations is not None:
            citations_display = str(citations)
        else:
            citations_display = "-"

        papers.append(
            Paper(
                title=title,
                year=year,
                citations=citations_display,
                doi_or_url=_prepare_doi_or_url(work),
            )
        )

    return papers


def _format_table_rows(papers: Iterable[Paper]) -> list[list[str]]:
    return [[paper.title, paper.year, paper.citations, paper.doi_or_url] for paper in papers]


def format_papers_table(papers: Iterable[Paper]) -> str:
    """Format papers as a Markdown table."""

    rows = _format_table_rows(papers)

    headers = ["Title", "Year", "Citations", "DOI/URL"]
    if not rows:
        return (
            "| "
            + " | ".join(headers)
            + " |\n| "
            + " | ".join(["---"] * len(headers))
            + " |\n| No results | - | - | - |"
        )

    column_widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            column_widths[idx] = max(column_widths[idx], len(cell))

    def _format_row(row: List[str]) -> str:
        padded = [
            row[0].ljust(column_widths[0]),
            row[1].rjust(column_widths[1]),
            row[2].rjust(column_widths[2]),
            row[3].ljust(column_widths[3]),
        ]
        return "| " + " | ".join(padded) + " |"

    header_row = _format_row(headers)
    separator_cells = []
    for idx, width in enumerate(column_widths):
        if idx in {1, 2}:
            separator_cells.append("-" * (width - 1) + ":")
        else:
            separator_cells.append(":" + "-" * (width - 1))
    separator_row = "| " + " | ".join(separator_cells) + " |"

    body_rows = [_format_row(row) for row in rows]
    return "\n".join([header_row, separator_row, *body_rows])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the most cited academic papers using OpenAlex with optional "
            "Semantic Scholar verification."
        )
    )
    parser.add_argument("query", help="Search keyword used for the title lookup.")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of papers to include (default: 5).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds for each HTTP request (default: 15).",
    )
    parser.add_argument(
        "--no-verify",
        dest="verify",
        action="store_false",
        default=True,
        help="Skip Semantic Scholar verification.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for HTTP requests.",
    )
    return parser


def main(args: Iterable[str] | None = None) -> None:
    parser = build_parser()
    parsed = parser.parse_args(args=args)

    if parsed.limit <= 0:
        parser.error("--limit must be greater than zero")
    if parsed.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    logging.basicConfig(
        level=logging.DEBUG if parsed.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        papers = fetch_top_cited_papers(
            parsed.query,
            limit=parsed.limit,
            verify_with_semantic_scholar=parsed.verify,
            timeout=parsed.timeout,
        )
    except requests.HTTPError as exc:
        parser.error(f"API request failed: {exc}")
    except requests.RequestException as exc:
        parser.error(f"Network error: {exc}")
    except ValueError as exc:
        parser.error(str(exc))

    table = format_papers_table(papers)
    print(table)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

