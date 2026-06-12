"""Contract constraints enforced at the type boundary (contracts.md §1, §3):
image_filenames is one-or-more; confidence is a 0–1 self-report."""

import pytest
from helpers import make_application, warning
from pydantic import ValidationError

from ttb_label_reviewer.engine import ExtractedField


def test_image_filenames_must_be_nonempty():
    with pytest.raises(ValidationError):
        make_application(image_filenames=[])


def test_image_filenames_accepts_one():
    assert make_application(image_filenames=["front.png"]).image_filenames == [
        "front.png"
    ]


@pytest.mark.parametrize("confidence", [-0.1, 1.1, 3.0])
def test_field_confidence_out_of_range_rejected(confidence):
    with pytest.raises(ValidationError):
        ExtractedField(raw="OLD TOM", confidence=confidence)


@pytest.mark.parametrize("confidence", [0.0, 0.5, 1.0])
def test_field_confidence_in_range_accepted(confidence):
    assert ExtractedField(raw="OLD TOM", confidence=confidence)


def test_warning_confidence_out_of_range_rejected():
    with pytest.raises(ValidationError):
        warning(confidence=3.0)
