from __future__ import annotations

import re
from typing import List

SEARCH_SECTION_HEADER = "검색 쿼리 후보"
STEP_PATTERN = re.compile(r"^\s*(?:[-*]|\d+[.)])\s*(단계\s*\d+\s*:.+)$")
STOP_HEADERS = ("확인할 사항", SEARCH_SECTION_HEADER)

def extract_search_queries(plan: str) -> List[str]:
    """Extract candidate search queries from the planner output."""
    queries: List[str] = []
    capture = False

    for raw_line in plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if capture:
            if line.startswith("-") or line.startswith("*"):
                query = line[1:].strip()
                if query:
                    queries.append(query)
                continue
            break

        if line.casefold().startswith(SEARCH_SECTION_HEADER.casefold()):
            capture = True

    return queries


def extract_plan_steps(plan: str) -> List[str]:
    """Parse step-level instructions from the planner output."""
    steps: List[str] = []

    for raw_line in plan.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalised = line.casefold()
        if any(normalised.startswith(header.casefold()) for header in STOP_HEADERS):
            break

        match = STEP_PATTERN.match(line)
        if match:
            steps.append(match.group(1).strip())

    return steps
