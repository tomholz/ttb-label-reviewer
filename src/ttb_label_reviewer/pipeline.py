"""The pipeline (D-1): images -> extraction -> rule engine -> ReviewResult.

Single review and batch rows both go through this one function; the only
difference upstream is how the application record and images arrive.
"""

from collections.abc import Sequence

from .engine import ApplicationRecord, EngineConfig, ReviewResult, review
from .extraction.base import Extractor, LabelImage


def review_label_set(
    application: ApplicationRecord,
    images: Sequence[LabelImage],
    extractor: Extractor,
    config: EngineConfig | None = None,
) -> ReviewResult:
    """Run one application's label set through extraction and every rule.

    Raises ExtractionError (from the extractor) on any extraction
    failure; the caller surfaces it as a visible error.
    """
    extraction = extractor.extract(images)
    return review(application, extraction, config)
