import os
import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .engine import ApplicationRecord, BeverageType, ReviewResult
from .extraction import AnthropicExtractor, ExtractionError, Extractor, LabelImage
from .extraction.base import ALLOWED_MEDIA_TYPES
from .pipeline import review_label_set

app = FastAPI(title="TTB Label Reviewer")

# Anthropic per-image API limit; enforced here so an oversized upload is
# a clear 413, not an opaque vision-API failure.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


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
    label_images: list[LabelImage] = []
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
        label_images.append(
            LabelImage(
                filename=upload.filename or "label",
                media_type=upload.content_type,
                data=data,
            )
        )

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


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TTB Label Reviewer</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem;
           margin: 4rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.5rem; }
    code { background: #f3f3f3; padding: 0.1rem 0.3rem; border-radius: 3px; }
  </style>
</head>
<body>
  <h1>TTB Label Reviewer</h1>
  <p>AI-powered alcohol label verification &mdash; the AI extracts,
     the code decides.</p>
  <p>Prototype (milestone 3). Single review is available as an API:
     <code>POST /api/review</code> with the application fields and one or
     more label images. The web UI lands in milestone 4.</p>
</body>
</html>
"""
