import asyncio
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import limits
from .batch import TEMPLATE_CSV, BatchError, RowError, parse_batch_zip
from .engine import ApplicationRecord, BeverageType, ReviewResult
from .extraction import AnthropicExtractor, ExtractionError, Extractor, LabelImage
from .extraction.base import ALLOWED_MEDIA_TYPES
from .jobs import BatchJob, JobRegistry, SSEEvent, run_batch
from .pipeline import review_label_set

_PACKAGE_DIR = Path(__file__).parent

app = FastAPI(title="TTB Label Reviewer")
# Vendored assets (D-10.3): htmx and CSS ship in the container; the only
# runtime outbound dependency is the model API.
app.mount("/static", StaticFiles(directory=_PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_PACKAGE_DIR / "templates")


@lru_cache
def _default_extractor() -> AnthropicExtractor:
    return AnthropicExtractor()


def get_extractor() -> Extractor:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Extraction is not configured: ANTHROPIC_API_KEY is not set.",
        )
    return _default_extractor()


def _is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def _error_fragment(request: Request, detail: str, status_code: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/error.html",
        {"detail": detail},
        status_code=status_code,
    )


@app.exception_handler(HTTPException)
async def _http_exception(request: Request, exc: HTTPException):
    """htmx requests get a visible error fragment swapped into the results
    area; API callers keep FastAPI's JSON error shape."""
    if _is_htmx(request):
        return _error_fragment(request, str(exc.detail), exc.status_code)
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation_exception(request: Request, exc: RequestValidationError):
    if _is_htmx(request):
        problems = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'][1:]) or 'request'}: {err['msg']}"
            for err in exc.errors()
        )
        return _error_fragment(request, f"Invalid input — {problems}.", 422)
    return await request_validation_exception_handler(request, exc)


def _read_label_images(images: list[UploadFile]) -> list[LabelImage]:
    if len(images) > limits.MAX_IMAGES_PER_SET:
        raise HTTPException(
            status_code=413,
            detail=f"Too many images ({len(images)}): a review accepts at "
            f"most {limits.MAX_IMAGES_PER_SET}.",
        )
    label_images: list[LabelImage] = []
    total_bytes = 0
    for upload in images:
        if upload.content_type not in ALLOWED_MEDIA_TYPES:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported image type {upload.content_type!r} for "
                f"{upload.filename!r}; use JPEG, PNG, WebP, or GIF.",
            )
        data = upload.file.read()
        if len(data) > limits.MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Image {upload.filename!r} exceeds the 5 MB limit.",
            )
        total_bytes += len(data)
        if total_bytes > limits.MAX_TOTAL_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Combined image size exceeds the 20 MB limit for one review.",
            )
        label_images.append(
            LabelImage(
                filename=upload.filename or "label",
                media_type=upload.content_type,
                data=data,
            )
        )
    return label_images


def _run_single_review(
    brand_name: str,
    class_type: str,
    abv_percent: float,
    net_contents: str,
    imported: bool,
    images: list[UploadFile],
    extractor: Extractor,
) -> ReviewResult:
    """Shared body of the API and UI review endpoints: uploads ->
    application record -> pipeline (D-1). Raises HTTPException only."""
    label_images = _read_label_images(images)
    application = ApplicationRecord(
        # contracts.md §1: single review auto-generates the identifier.
        application_id=f"single-{uuid.uuid4().hex[:8]}",
        beverage_type=BeverageType.DISTILLED_SPIRITS,
        brand_name=brand_name,
        class_type=class_type,
        abv_percent=abv_percent,
        net_contents=net_contents,
        imported=imported,
        image_filenames=[image.filename for image in label_images],
    )
    try:
        return review_label_set(application, label_images, extractor)
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Browsers request this path by default; without it, every page
    view logs a 404. scripts/build_favicon.py draws the file."""
    return FileResponse(
        _PACKAGE_DIR / "static" / "favicon.ico", media_type="image/x-icon"
    )


@app.post("/api/review")
def api_review(
    brand_name: Annotated[str, Form(min_length=1)],
    class_type: Annotated[str, Form(min_length=1)],
    abv_percent: Annotated[float, Form()],
    net_contents: Annotated[str, Form(min_length=1)],
    images: Annotated[list[UploadFile], File()],
    extractor: Annotated[Extractor, Depends(get_extractor)],
    imported: Annotated[bool, Form()] = False,
) -> ReviewResult:
    """Single review: one application record + one-or-more label images
    (untagged, order-irrelevant) -> contracts.md §4 review result."""
    return _run_single_review(
        brand_name,
        class_type,
        abv_percent,
        net_contents,
        imported,
        images,
        extractor,
    )


@app.post("/review", response_class=HTMLResponse)
def ui_review(
    request: Request,
    brand_name: Annotated[str, Form(min_length=1)],
    class_type: Annotated[str, Form(min_length=1)],
    abv_percent: Annotated[float, Form()],
    net_contents: Annotated[str, Form(min_length=1)],
    images: Annotated[list[UploadFile], File()],
    extractor: Annotated[Extractor, Depends(get_extractor)],
    imported: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    """The single-review form target: same pipeline as /api/review, but
    the result renders as an HTML fragment htmx swaps into the page."""
    result = _run_single_review(
        brand_name,
        class_type,
        abv_percent,
        net_contents,
        imported,
        images,
        extractor,
    )
    return templates.TemplateResponse(
        request, "partials/results.html", {"result": result}
    )


class _BatchFragments:
    """jobs.BatchRenderer implementation: SSE event payloads rendered
    from the same Jinja templates as the rest of the UI. Rendered
    without a Request — these fragments travel over the event stream,
    not an HTTP response."""

    def review_row(self, result: ReviewResult) -> str:
        template = templates.env.get_template("partials/batch_row.html")
        return template.render(result=result)

    def error_row(self, error: RowError) -> str:
        template = templates.env.get_template("partials/batch_error_row.html")
        return template.render(error=error)

    def counts(self, job: BatchJob, done: bool) -> str:
        template = templates.env.get_template("partials/batch_counts.html")
        return template.render(job=job, done=done)

    def failure(self, job: BatchJob) -> str:
        template = templates.env.get_template("partials/batch_failed.html")
        return template.render(job=job)


_batch_fragments = _BatchFragments()
_batch_jobs = JobRegistry()

# SSE responses must reach the browser event by event: no caching, and
# no proxy buffering (X-Accel-Buffering is honored by Fly's proxy).
_SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


@app.get("/batch/template")
def batch_template() -> Response:
    """The downloadable manifest template (contracts.md §2), named
    manifest.csv because that is what the zip must contain."""
    return Response(
        TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="manifest.csv"'},
    )


@app.post("/batch", response_class=HTMLResponse)
async def ui_batch(
    request: Request,
    batch_zip: Annotated[UploadFile, File()],
    extractor: Annotated[Extractor, Depends(get_extractor)],
) -> HTMLResponse:
    """Accept the zip, fail fast on batch-level problems, then start the
    runner and return the results-table skeleton; rows arrive over SSE."""
    data = await batch_zip.read()
    if len(data) > limits.MAX_BATCH_ZIP_BYTES:
        raise HTTPException(
            status_code=413,
            detail="The zip exceeds the "
            f"{limits.MAX_BATCH_ZIP_BYTES // (1024 * 1024)} MB upload limit; "
            "split the batch into smaller zips.",
        )
    try:
        parsed = parse_batch_zip(data)
    except BatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = _batch_jobs.create(total=parsed.total)
    # The runner outlives this request on purpose: results stream to the
    # /batch/{job_id}/events connection the returned fragment opens.
    job.task = asyncio.create_task(run_batch(job, parsed, extractor, _batch_fragments))
    return templates.TemplateResponse(
        request, "partials/batch_running.html", {"job": job}
    )


@app.get("/batch/{job_id}/events")
async def batch_events(job_id: str, request: Request) -> StreamingResponse:
    job = _batch_jobs.get(job_id)
    if job is None:
        # A stale page reconnecting after the job was purged: answer with
        # a terminal stream instead of a 404, which EventSource would
        # retry forever.
        async def gone():
            yield SSEEvent(
                id=0,
                name="counts",
                data="This batch is no longer available; upload it again.",
            ).serialize()
            yield SSEEvent(id=1, name="done", data="done").serialize()

        return StreamingResponse(
            gone(), media_type="text/event-stream", headers=_SSE_HEADERS
        )

    start_index = 0
    last_event_id = request.headers.get("last-event-id", "")
    if last_event_id.isdigit():
        # Reconnect: replay only what the browser hasn't seen.
        start_index = int(last_event_id) + 1
    return StreamingResponse(
        job.stream(start_index), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@lru_cache
def _demo_data() -> dict:
    """Form values and what-to-expect copy for the sample-data card,
    generated from the golden set by golden/build_demo.py (committed,
    drift-tested) — never typed by hand."""
    return json.loads((_PACKAGE_DIR / "static" / "demo" / "demo.json").read_text())


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"demo": _demo_data()})
