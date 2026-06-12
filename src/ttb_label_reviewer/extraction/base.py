"""Extraction interface (D-10.1): the seam between the pipeline and
whichever vision API backs it."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

from ..engine import ExtractionResult

# The image formats the Anthropic vision API accepts; enforced at the
# upload boundary so a bad file is a row-level error, not an API failure.
MediaType = Literal["image/jpeg", "image/png", "image/webp", "image/gif"]

ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
    ["image/jpeg", "image/png", "image/webp", "image/gif"]
)


class LabelImage(BaseModel):
    """One label image as uploaded: front, back, side, or neck — untagged,
    order-irrelevant (contracts.md §1)."""

    filename: str
    media_type: MediaType
    data: bytes


class ExtractionError(Exception):
    """Extraction failed in a way the caller must surface as a visible
    error (row-level error in batch, error state in single review) —
    never a crash, never a silent retry loop. The message is written to
    be shown to the user."""


class Extractor(Protocol):
    def extract(self, images: Sequence[LabelImage]) -> ExtractionResult:
        """Read one application's label set into the §3 extraction result.

        Raises ExtractionError on any failure (API error, refusal,
        malformed model output)."""
        ...
