"""Canned application records and extraction results (contracts.md §1, §3)
for rule-engine tests. The defaults describe a fully compliant OLD TOM
DISTILLERY label set."""

from ttb_label_reviewer.engine import (
    ApplicationRecord,
    ExtractedField,
    ExtractedWarning,
    ExtractionResult,
    Finding,
    ReviewResult,
)

# The canonical warning as it would sit on a printed label: line breaks
# included. Tests mutate this string to build deviant labels.
WARNING_ON_LABEL = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women\n"
    "should not drink alcoholic beverages during pregnancy because of\n"
    "the risk of birth defects. (2) Consumption of alcoholic beverages\n"
    "impairs your ability to drive a car or operate machinery, and may\n"
    "cause health problems."
)


def field(raw: str, confidence: float = 0.97) -> ExtractedField:
    return ExtractedField(raw=raw, confidence=confidence)


def warning(
    raw_text: str = WARNING_ON_LABEL,
    lead_in_bold: str = "yes",
    remainder_bold: str = "no",
    separate_and_apart: str = "yes",
    confidence: float = 0.93,
) -> ExtractedWarning:
    return ExtractedWarning(
        raw_text=raw_text,
        lead_in_bold=lead_in_bold,
        remainder_bold=remainder_bold,
        separate_and_apart=separate_and_apart,
        confidence=confidence,
    )


def make_application(**overrides) -> ApplicationRecord:
    base = {
        "application_id": "app-001",
        "beverage_type": "distilled_spirits",
        "brand_name": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": 45.0,
        "net_contents": "750 mL",
        "imported": False,
        "image_filenames": ["front.png", "back.png"],
    }
    base.update(overrides)
    return ApplicationRecord(**base)


def make_extraction(**overrides) -> ExtractionResult:
    base = {
        "brand_name": field("OLD TOM DISTILLERY"),
        "class_type": field("Kentucky Straight Bourbon Whiskey"),
        "alcohol_content": field("45% Alc./Vol."),
        "proof": field("90 Proof"),
        "net_contents": field("750 mL"),
        "name_address": field("Bottled by Old Tom Distillery, Bardstown, KY"),
        "country_of_origin": None,
        "government_warning": warning(),
    }
    base.update(overrides)
    return ExtractionResult(**base)


def finding(result: ReviewResult, rule_id: str) -> Finding:
    return next(f for f in result.findings if f.rule_id == rule_id)
