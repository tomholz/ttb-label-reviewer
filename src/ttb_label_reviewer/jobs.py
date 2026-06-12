"""In-process batch jobs: bounded-parallel review with an SSE event log.

A batch begins streaming per-label results immediately (D-3) — rows are
reviewed concurrently and each result is appended to the job's event log
the moment it lands. The log (not a transient queue) is what the SSE
endpoint streams, so a dropped connection replays from `Last-Event-ID`
instead of losing rows. Jobs live in process memory only: uploads exist
for the duration of a review and nothing is retained (D-10.4), which
also means a redeploy mid-batch loses the job — acceptable for a
prototype, stated in the README.

Rendering is injected (the `render` callable protocol) so this module
stays UI-agnostic and the templates stay owned by main.py.
"""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Protocol

from .batch import BatchRow, ParsedBatch, RowError
from .extraction.base import ExtractionError, Extractor
from .pipeline import review_label_set

logger = logging.getLogger(__name__)

# Rows reviewed concurrently per batch. Each review is one vision-API
# call a few seconds long; 4 keeps a 300-row batch under ~7 minutes
# while staying well inside API rate limits.
EXTRACTION_CONCURRENCY = 4

# Jobs are purged this long after creation. Generous: a full batch takes
# minutes, and the event log a reconnecting page would replay is small.
JOB_TTL_SECONDS = 3600


@dataclass
class SSEEvent:
    id: int
    name: str
    data: str

    def serialize(self) -> str:
        lines = [f"id: {self.id}", f"event: {self.name}"]
        lines.extend(f"data: {line}" for line in self.data.splitlines() or [""])
        return "\n".join(lines) + "\n\n"


class BatchRenderer(Protocol):
    """What the runner needs from the UI layer: HTML for each event."""

    def review_row(self, result) -> str: ...
    def error_row(self, error: RowError) -> str: ...
    def counts(self, job: "BatchJob", done: bool) -> str: ...


class BatchJob:
    """One running (or finished) batch: counts plus an append-only event
    log that SSE consumers stream from any starting index."""

    def __init__(self, job_id: str, total: int):
        self.job_id = job_id
        self.total = total
        self.created_at = time.monotonic()
        self.counts = {"fail": 0, "needs_review": 0, "pass": 0, "error": 0}
        self.events: list[SSEEvent] = []
        self.task: asyncio.Task | None = None  # keeps the runner referenced
        self._changed = asyncio.Condition()

    @property
    def processed(self) -> int:
        return sum(self.counts.values())

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > JOB_TTL_SECONDS

    async def emit(self, name: str, data: str) -> None:
        async with self._changed:
            self.events.append(SSEEvent(id=len(self.events), name=name, data=data))
            self._changed.notify_all()

    async def stream(self, start_index: int = 0):
        """Yield serialized events from start_index until the terminal
        "done" event has been sent; blocks while the runner is ahead."""
        index = start_index
        while True:
            while index < len(self.events):
                event = self.events[index]
                index += 1
                yield event.serialize()
                if event.name == "done":
                    return
            async with self._changed:
                if index >= len(self.events):
                    await self._changed.wait()


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, BatchJob] = {}

    def create(self, total: int) -> BatchJob:
        self._jobs = {k: v for k, v in self._jobs.items() if not v.expired}
        job = BatchJob(job_id=secrets.token_urlsafe(8), total=total)
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> BatchJob | None:
        job = self._jobs.get(job_id)
        if job is None or job.expired:
            return None
        return job


async def run_batch(
    job: BatchJob,
    parsed: ParsedBatch,
    extractor: Extractor,
    render: BatchRenderer,
) -> None:
    """Review every parsed row and emit one event per outcome.

    Row order in the stream is completion order; the UI's grouped table
    (fail > needs_review > pass, errors on top) does the sorting, so
    nothing here waits on anything else.
    """

    async def emit_error(error: RowError) -> None:
        job.counts["error"] += 1
        await job.emit("row-error", render.error_row(error))
        await job.emit("counts", render.counts(job, done=False))

    # Manifest-level row errors are known before any extraction starts;
    # surfacing them first gets fixable rows back to the user immediately.
    for error in parsed.errors:
        await emit_error(error)

    semaphore = asyncio.Semaphore(EXTRACTION_CONCURRENCY)

    async def review_one(row: BatchRow) -> None:
        async with semaphore:
            try:
                # The extractor is synchronous (one blocking API call);
                # a thread per in-flight row keeps the event loop free
                # to stream results while reviews run.
                result = await asyncio.to_thread(
                    review_label_set, row.application, row.images, extractor
                )
            except ExtractionError as exc:
                await emit_error(
                    RowError(row.row_number, row.application.application_id, str(exc))
                )
                return
            except Exception:
                # A bug must cost one row, never the batch (contracts.md §2).
                logger.exception(
                    "unexpected error reviewing batch row %s", row.row_number
                )
                await emit_error(
                    RowError(
                        row.row_number,
                        row.application.application_id,
                        "Internal error while reviewing this row.",
                    )
                )
                return
        job.counts[result.verdict.value] += 1
        await job.emit(f"row-{result.verdict.value}", render.review_row(result))
        await job.emit("counts", render.counts(job, done=False))

    await asyncio.gather(*(review_one(row) for row in parsed.rows))
    await job.emit("counts", render.counts(job, done=True))
    # Terminal event: closes every open stream, and sse-close="done"
    # stops the browser's EventSource from reconnecting.
    await job.emit("done", "done")
