"""Queue-based crawling orchestration primitives.

This module implements the Scheduler → Job Queue → Master → Worker pattern that the
Minor Search documentation describes.  It provides in-memory defaults so the
components can be exercised in unit tests or simple scripts without requiring an
external Redis/SQS deployment, while still exposing extension points for
production usage.

The key pieces are:

``CrawlProject``
    Logical grouping of seeds that share metadata and default configuration.

``CrawlJob``
    Container describing a single unit of crawling work (query string plus
    optional overrides and metadata).

``InMemoryJobQueue``
    Thread-safe FIFO queue used for tests and local experimentation.  The queue
    implements the minimal operations required by the rest of the orchestrator
    so that alternate backends (e.g. Redis) can be dropped in by providing a
    compatible implementation.

``Scheduler``
    Responsible for seeding the queue with initial jobs.  It uses the shared
    ``CrawlState`` to deduplicate queries so that the same task is not scheduled
    repeatedly.

``Worker``
    Pops jobs from the queue, executes the search via the injected ``search``
    callable, and pushes any newly discovered related queries back onto the
    queue.  Results can be forwarded to custom handlers for persistence.

``Master``
    Coordinates a pool of workers and drains the queue until no more work
    remains or the optional job limit is reached.

These utilities do not perform any network operations themselves; instead they
delegate to the existing :func:`minor_search.search.run_search` helper (or any
compatible callable).  This keeps the components easy to test and allows the
production deployment to reuse the same crawling/search implementation already
used by the CLI entry point.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
import logging
import threading
import time
from itertools import cycle
from typing import Any, Callable, Deque, Iterable, Optional, Protocol, Sequence

from .search import SearchRunResult

logger = logging.getLogger(__name__)


class JobQueue(Protocol):
    """Minimal interface required for a job queue implementation."""

    def enqueue(self, job: "CrawlJob") -> None:
        """Add a job to the back of the queue."""

    def requeue(self, job: "CrawlJob") -> None:
        """Reinsert a job at the front of the queue (used for retries)."""

    def dequeue(self, timeout: float | None = None) -> "CrawlJob | None":
        """Pop a job from the front of the queue, waiting up to ``timeout`` seconds."""

    def size(self) -> int:
        """Return the number of jobs currently waiting in the queue."""


@dataclass(slots=True)
class CrawlJob:
    """Description of a single crawling task pulled from the queue."""

    query: str
    project: str | None = None
    search_kwargs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0

    def normalized_query(self) -> str:
        """Return a canonical representation used for deduplication."""

        return " ".join(self.query.split())


@dataclass(slots=True)
class CrawlProject:
    """Group of related crawl jobs executed together."""

    name: str
    seeds: Sequence[str | CrawlJob]
    search_kwargs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class CrawlState:
    """Shared mutable state used to coordinate deduplication across workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen_queries: set[str] = set()

    def mark_seen(self, query: str) -> bool:
        """Return ``True`` if the query was not previously scheduled."""

        normalized = " ".join(query.split())
        if not normalized:
            return False
        with self._lock:
            if normalized in self._seen_queries:
                return False
            self._seen_queries.add(normalized)
            return True


class InMemoryJobQueue(JobQueue):
    """Simple FIFO job queue backed by :class:`collections.deque`."""

    def __init__(self) -> None:
        self._queue: Deque[CrawlJob] = deque()
        self._condition = threading.Condition()

    def enqueue(self, job: CrawlJob) -> None:
        with self._condition:
            self._queue.append(job)
            self._condition.notify()

    def requeue(self, job: CrawlJob) -> None:
        with self._condition:
            self._queue.appendleft(job)
            self._condition.notify()

    def dequeue(self, timeout: float | None = None) -> CrawlJob | None:
        with self._condition:
            if timeout is None:
                while not self._queue:
                    self._condition.wait()
            else:
                deadline = time.monotonic() + timeout
                while not self._queue:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._condition.wait(remaining)
            return self._queue.popleft()

    def size(self) -> int:
        with self._condition:
            return len(self._queue)


class Scheduler:
    """Seed the job queue with initial queries."""

    def __init__(self, queue: JobQueue, state: CrawlState | None = None) -> None:
        self.queue = queue
        self.state = state or CrawlState()

    def schedule(self, seeds: Iterable[str | CrawlJob | CrawlProject]) -> int:
        """Add the provided seeds or projects to the queue, skipping duplicates."""

        count = 0
        for item in seeds:
            if isinstance(item, CrawlProject):
                count += self.schedule_project(item)
                continue

            job = item if isinstance(item, CrawlJob) else CrawlJob(query=str(item))
            if not job.query.strip():
                continue
            if not self.state.mark_seen(job.query):
                continue
            self.queue.enqueue(job)
            count += 1
        return count

    def schedule_project(self, project: CrawlProject) -> int:
        """Enqueue all seeds defined within a project."""

        count = 0
        for seed in project.seeds:
            base_job = seed if isinstance(seed, CrawlJob) else CrawlJob(query=str(seed))
            job = replace(
                base_job,
                project=project.name,
                search_kwargs={**project.search_kwargs, **base_job.search_kwargs},
                metadata={**project.metadata, **base_job.metadata},
            )
            if not job.query.strip():
                continue
            if not self.state.mark_seen(job.query):
                continue
            self.queue.enqueue(job)
            count += 1
        return count


ResultHandler = Callable[[CrawlJob, SearchRunResult], None]


class Worker:
    """Process crawl jobs pulled from the queue."""

    def __init__(
        self,
        queue: JobQueue,
        *,
        state: CrawlState | None = None,
        search: Callable[..., SearchRunResult],
        default_search_kwargs: Optional[dict[str, Any]] = None,
        result_handler: ResultHandler | None = None,
        enqueue_related: bool = True,
        max_retries: int = 2,
        name: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.queue = queue
        self.state = state or CrawlState()
        self.search = search
        self.default_search_kwargs = default_search_kwargs or {}
        self.result_handler = result_handler
        self.enqueue_related = enqueue_related
        self.max_retries = max(0, max_retries)
        self.name = name or "worker"
        self.logger = logger or logging.getLogger(f"{__name__}.{self.name}")

    def step(self, *, timeout: float | None = 1.0) -> bool:
        """Attempt to process a single job from the queue."""

        job = self.queue.dequeue(timeout=timeout)
        if job is None:
            return False
        success = self._execute_job(job)
        if not success and job.attempts < self.max_retries:
            job.attempts += 1
            self.queue.requeue(job)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _execute_job(self, job: CrawlJob) -> bool:
        try:
            kwargs = dict(self.default_search_kwargs)
            kwargs.update(job.search_kwargs)
            result = self.search(job.query, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive logging branch.
            self.logger.exception("%s failed: %s", job.normalized_query(), exc)
            return False

        if self.result_handler:
            self.result_handler(job, result)

        if self.enqueue_related and result.related_queries:
            for related in result.related_queries:
                if not related or not related.strip():
                    continue
                if not self.state.mark_seen(related):
                    continue
                child_job = CrawlJob(
                    query=related,
                    project=job.project,
                    search_kwargs=dict(job.search_kwargs),
                    metadata={**job.metadata, "parent_query": job.query},
                )
                self.queue.enqueue(child_job)

        return True


class Master:
    """Coordinate a pool of workers to drain the job queue."""

    def __init__(
        self,
        queue: JobQueue,
        workers: Iterable[Worker],
        *,
        idle_sleep: float = 0.1,
        max_idle_cycles: int = 10,
        logger: logging.Logger | None = None,
    ) -> None:
        self.queue = queue
        self.workers = list(workers)
        if not self.workers:
            raise ValueError("At least one worker is required")
        self.idle_sleep = idle_sleep
        self.max_idle_cycles = max(1, max_idle_cycles)
        self.logger = logger or logging.getLogger(f"{__name__}.master")

    def run(self, *, max_jobs: int | None = None) -> int:
        """Drain the queue using the managed workers."""

        processed = 0
        idle_cycles = 0
        worker_cycle = cycle(self.workers)

        while max_jobs is None or processed < max_jobs:
            worker = next(worker_cycle)
            if worker.step(timeout=self.idle_sleep):
                processed += 1
                idle_cycles = 0
                continue

            idle_cycles += 1
            if idle_cycles >= self.max_idle_cycles * len(self.workers):
                if self.queue.size() == 0:
                    break
                idle_cycles = 0

        self.logger.debug("Master run complete – processed jobs: %d", processed)
        return processed


__all__ = [
    "CrawlJob",
    "CrawlState",
    "InMemoryJobQueue",
    "JobQueue",
    "Master",
    "CrawlProject",
    "Scheduler",
    "Worker",
]

