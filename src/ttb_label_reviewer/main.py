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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .engine import ApplicationRecord, BeverageType, ReviewResult
from .extraction import AnthropicExtractor, ExtractionError, Extractor, LabelImage
from .extraction.base import ALLOWED_MEDIA_TYPES
from .pipeline import review_label_set

_PACKAGE_DIR = Path(__file__).parent

app = FastAPI(title="TTB Label Reviewer")
# Vendored assets (D-10.3): htmx and CSS ship in the container; the only
# runtime outbound dependency is the model API.
app.mount("/static", StaticFiles(directory=_PACKAGE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=_PACKAGE_DIR / "templates")

# Upload caps, enforced here so an oversized upload is a clear 413, never
# an opaque vision-API failure. Derivation: the Anthropic API accepts a
# 32 MB request body and base64 inflates image bytes by 4/3, so 20 MB of
# raw images encodes to ~27 MB — under the limit with headroom for prompt
# and JSON. 8 images is double the realistic maximum for an untagged label
# set (front, back, side, neck). 5 MB/image is our own cap (the direct API
# allows ~10 MB base64-encoded per image); it bounds upload time and keeps
# any single image well clear of the request limit.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_MAX_IMAGES_PER_SET = 8
_MAX_TOTAL_IMAGE_BYTES = 20 * 1024 * 1024


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
    if len(images) > _MAX_IMAGES_PER_SET:
        raise HTTPException(
            status_code=413,
            detail=f"Too many images ({len(images)}): a review accepts at "
            f"most {_MAX_IMAGES_PER_SET}.",
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
        if len(data) > _MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Image {upload.filename!r} exceeds the 5 MB limit.",
            )
        total_bytes += len(data)
        if total_bytes > _MAX_TOTAL_IMAGE_BYTES:
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


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
