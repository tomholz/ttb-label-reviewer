"""A no-network extractor (D-10.1), selected by EXTRACTOR_BACKEND=offline.

It performs no transcription and makes no API call: every field comes back
present but at zero confidence, so the rule engine routes the whole review
to needs_review (illegible) rather than fabricating a verdict it cannot
justify from an image it never read.

Its purpose is to prove the app boots and serves the full pipeline with
zero outbound dependency — the air-gapped case behind the federal
transition story — and to drive the UI without API cost. It is operator
configuration, never a user-facing review mode, and it ignores image
content entirely.
"""

from collections.abc import Sequence

from ..engine import ExtractedField, ExtractedWarning, ExtractionResult
from .base import LabelImage

_MARKER = "(offline mode: no extraction was performed)"


class OfflineExtractor:
    """Extractor-protocol implementation that calls no model and reaches
    no network. Returns a fixed zero-confidence result for any input."""

    def extract(self, images: Sequence[LabelImage]) -> ExtractionResult:
        placeholder = ExtractedField(raw=_MARKER, confidence=0.0)
        return ExtractionResult(
            brand_name=placeholder,
            class_type=placeholder,
            alcohol_content=placeholder,
            net_contents=placeholder,
            name_address=placeholder,
            government_warning=ExtractedWarning(raw_text=_MARKER, confidence=0.0),
        )
