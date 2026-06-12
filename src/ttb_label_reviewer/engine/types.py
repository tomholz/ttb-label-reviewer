"""Engine data types, mirroring docs/contracts.md §1 (application record),
§3 (extraction result), and §4 (review result). Changing a shape here is a
contract change — deliberate, not incidental."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BeverageType(StrEnum):
    DISTILLED_SPIRITS = "distilled_spirits"
    # wine / malt_beverage reserved (stubs in docs/ttb-requirements.md)


class ApplicationRecord(BaseModel):
    """contracts.md §1 — the subset of COLA application fields the rules
    consume."""

    application_id: str
    beverage_type: BeverageType
    brand_name: str
    class_type: str
    abv_percent: float
    net_contents: str
    imported: bool = False
    image_filenames: list[str] = Field(min_length=1)


class TriState(StrEnum):
    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


class ExtractedField(BaseModel):
    raw: str
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractedWarning(BaseModel):
    raw_text: str
    # Default UNCERTAIN: a malformed observation can only degrade toward
    # needs_review, never toward pass.
    lead_in_bold: TriState = TriState.UNCERTAIN
    remainder_bold: TriState = TriState.UNCERTAIN
    separate_and_apart: TriState = TriState.UNCERTAIN
    confidence: float = Field(ge=0.0, le=1.0)


class ExtractionResult(BaseModel):
    """contracts.md §3 — raw strings only, no parsing, no judgment.
    None means "not found on any provided image" (distinct from found
    but low-confidence)."""

    brand_name: ExtractedField | None = None
    class_type: ExtractedField | None = None
    alcohol_content: ExtractedField | None = None
    proof: ExtractedField | None = None
    net_contents: ExtractedField | None = None
    name_address: ExtractedField | None = None
    country_of_origin: ExtractedField | None = None
    government_warning: ExtractedWarning | None = None


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVIEW = "needs_review"
    NOT_APPLICABLE = "not_applicable"


class Reason(StrEnum):
    MISMATCH = "mismatch"
    MISSING = "missing"
    ILLEGIBLE = "illegible"
    FORMAT = "format"


class DiffSpan(BaseModel):
    op: Literal["equal", "replace", "delete", "insert"]
    expected: str
    actual: str


class Finding(BaseModel):
    rule_id: str
    rule_name: str
    outcome: Outcome
    reason: Reason | None = None
    expected: str | None = None
    actual: str | None = None
    citation: str
    explanation: str
    diff: list[DiffSpan] | None = None


class Counts(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    fail: int = 0
    needs_review: int = 0
    pass_: int = Field(0, alias="pass")
    not_applicable: int = 0


class ReviewResult(BaseModel):
    """contracts.md §4 — rule engine → UI / API response."""

    application_id: str
    verdict: Outcome
    counts: Counts
    findings: list[Finding]


class EngineConfig(BaseModel):
    """Engine configuration — deliberately not part of the extraction
    contract (contracts.md §3)."""

    # Below this self-reported confidence a field routes to needs_review /
    # illegible — never fail, never a silent pass. Tuned against the golden
    # set in milestone 5.
    illegibility_threshold: float = 0.5
