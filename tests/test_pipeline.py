"""Pipeline tests with a fake extractor — API-free (D-5)."""

import pytest
from helpers import field, make_application, make_extraction

from ttb_label_reviewer.extraction import ExtractionError, LabelImage
from ttb_label_reviewer.pipeline import review_label_set

IMAGES = [LabelImage(filename="front.png", media_type="image/png", data=b"x")]


class FakeExtractor:
    def __init__(self, extraction):
        self.extraction = extraction
        self.seen_images = None

    def extract(self, images):
        self.seen_images = list(images)
        return self.extraction


class FailingExtractor:
    def extract(self, images):
        raise ExtractionError("boom")


def test_clean_label_set_passes():
    extractor = FakeExtractor(make_extraction())
    result = review_label_set(make_application(), IMAGES, extractor)
    assert result.verdict == "pass"
    assert result.counts.fail == 0
    assert extractor.seen_images == IMAGES


def test_extraction_findings_flow_through_to_verdict():
    extraction = make_extraction(brand_name=field("WRONG BRAND ENTIRELY"))
    result = review_label_set(make_application(), IMAGES, FakeExtractor(extraction))
    assert result.verdict == "fail"
    ds1 = next(f for f in result.findings if f.rule_id == "DS-1")
    assert ds1.outcome == "fail"
    assert ds1.actual == "WRONG BRAND ENTIRELY"


def test_extraction_error_propagates_to_caller():
    with pytest.raises(ExtractionError, match="boom"):
        review_label_set(make_application(), IMAGES, FailingExtractor())
