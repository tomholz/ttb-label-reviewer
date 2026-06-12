"""Deterministic rule engine: the AI extracts, this code decides (D-1)."""

from .engine import review
from .types import (
    ApplicationRecord,
    BeverageType,
    Counts,
    DiffSpan,
    EngineConfig,
    ExtractedField,
    ExtractedWarning,
    ExtractionResult,
    Finding,
    Outcome,
    Reason,
    ReviewResult,
    TriState,
)

__all__ = [
    "ApplicationRecord",
    "BeverageType",
    "Counts",
    "DiffSpan",
    "EngineConfig",
    "ExtractedField",
    "ExtractedWarning",
    "ExtractionResult",
    "Finding",
    "Outcome",
    "Reason",
    "ReviewResult",
    "TriState",
    "review",
]
