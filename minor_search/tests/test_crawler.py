from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import importlib
import sys
from pathlib import Path
from types import ModuleType
from uuid import uuid4

PACKAGE_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

stub_package = ModuleType("minor_search")
stub_package.__path__ = [str(PACKAGE_DIR)]
sys.modules.setdefault("minor_search", stub_package)

minor_stub = ModuleType("minor")
minor_stub.__path__ = []
sys.modules.setdefault("minor", minor_stub)

logbook_stub = ModuleType("minor.logbook")
logbook_stub.log_search_run = lambda **_: uuid4()
sys.modules.setdefault("minor.logbook", logbook_stub)
minor_stub.logbook = logbook_stub

langchain_core_tools = ModuleType("langchain_core.tools")


def _tool(func: Callable | None = None, **_: object):
    if func is None:
        def decorator(inner: Callable) -> Callable:
            return inner
        return decorator
    return func


langchain_core_tools.tool = _tool
langchain_core_module = ModuleType("langchain_core")
langchain_core_module.tools = langchain_core_tools
sys.modules.setdefault("langchain_core", langchain_core_module)
sys.modules.setdefault("langchain_core.tools", langchain_core_tools)

crawler_module = importlib.import_module("minor_search.crawler")
search_module = importlib.import_module("minor_search.search")

CrawlJob = crawler_module.CrawlJob
CrawlState = crawler_module.CrawlState
InMemoryJobQueue = crawler_module.InMemoryJobQueue
Master = crawler_module.Master
Scheduler = crawler_module.Scheduler
Worker = crawler_module.Worker
SearchChunk = search_module.SearchChunk
SearchRunResult = search_module.SearchRunResult


@dataclass
class FakeResult:
    """Utility container to configure fake search responses."""

    related_queries: list[str]

    def to_run_result(self) -> SearchRunResult:
        chunk = SearchChunk(
            query="seed",
            source_label="TEST",
            url="https://example.com",
            title="Example",
            chunk_index=1,
            content="Example content",
        )
        return SearchRunResult(
            base_query="seed",
            sections=["section"],
            markdown="md",
            related_queries=self.related_queries,
            chunks=[chunk],
            failures=[],
        )


def test_scheduler_enqueues_unique_jobs() -> None:
    queue = InMemoryJobQueue()
    state = CrawlState()
    scheduler = Scheduler(queue, state)

    seeds = [" 질의 ", CrawlJob(query="질의"), "다른 질의"]
    count = scheduler.schedule(seeds)

    assert count == 2
    assert queue.size() == 2
    first = queue.dequeue()
    second = queue.dequeue()
    assert first is not None and first.query.strip() == "질의"
    assert second is not None and second.query == "다른 질의"


def test_worker_processes_job_and_enqueues_related() -> None:
    queue = InMemoryJobQueue()
    state = CrawlState()
    scheduler = Scheduler(queue, state)

    handled = []

    def fake_search(query: str, **_: object) -> SearchRunResult:
        if query == "seed":
            return FakeResult(["follow up", "seed"]).to_run_result()
        return FakeResult([]).to_run_result()

    def result_handler(job: CrawlJob, result: SearchRunResult, object_name: str | None) -> None:
        handled.append((job.query, len(result.chunks), object_name))

    scheduler.schedule(["seed"])
    worker = Worker(
        queue,
        state=state,
        search=fake_search,
        default_search_kwargs={"crawl_limit": 1},
        result_handler=result_handler,
    )

    assert worker.step(timeout=0.01)
    assert handled and handled[0][0] == "seed"

    # ``seed`` should not be enqueued again because of deduplication, but the
    # new "follow up" query should appear.
    next_job = queue.dequeue(timeout=0.01)
    assert next_job is not None
    assert next_job.query == "follow up"


def test_master_drains_queue_with_multiple_workers() -> None:
    queue = InMemoryJobQueue()
    state = CrawlState()
    scheduler = Scheduler(queue, state)

    results = {
        "seed-1": FakeResult(["seed-3"]).to_run_result(),
        "seed-2": FakeResult([]).to_run_result(),
        "seed-3": FakeResult([]).to_run_result(),
    }

    def fake_search(query: str, **_: object) -> SearchRunResult:
        return results[query]

    scheduler.schedule(["seed-1", "seed-2"])

    workers = [
        Worker(queue, state=state, search=fake_search, name="w1"),
        Worker(queue, state=state, search=fake_search, name="w2"),
    ]

    master = Master(queue, workers, idle_sleep=0.01, max_idle_cycles=5)
    processed = master.run()

    # Three jobs should be processed (seed-1, seed-2, seed-3).
    assert processed == 3
    assert queue.size() == 0

